import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.config import settings
from app.models import User, PaymentQuote, Transaction, AuditLog, InAppNotification, utcnow
from app.services.activation import ActivationService
from app.services.fraud import FraudDetectionService
from app.services.settlement import get_settlement_provider

logger = logging.getLogger("travelpay.payments")

class PaymentService:
    @staticmethod
    def verify_user_pin(db: Session, user: User, pin: str):
        now = utcnow()
        # Check active lockout
        if user.pin_locked_until:
            lock_until = user.pin_locked_until.replace(tzinfo=timezone.utc)
            if now < lock_until:
                diff_mins = int((lock_until - now).total_seconds() / 60) + 1
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Security PIN locked due to 3 failed attempts. Please wait {diff_mins} minute(s)."
                )
            else:
                user.pin_failed_attempts = 0
                user.pin_locked_until = None
                db.commit()

        if not user.pin_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="App PIN has not been set."
            )

        is_valid = bcrypt.checkpw(pin.encode("utf-8"), user.pin_hash.encode("utf-8"))
        if not is_valid:
            user.pin_failed_attempts += 1
            if user.pin_failed_attempts >= settings.MAX_PIN_ATTEMPTS:
                user.pin_locked_until = now + timedelta(minutes=settings.PIN_LOCKOUT_MINUTES)
                db.commit()
                db.add(AuditLog(
                    user_id=user.id,
                    action="PIN_LOCKOUT_TRIGGERED",
                    details=f"Locked for {settings.PIN_LOCKOUT_MINUTES} minutes after 3 failures."
                ))
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Wrong PIN entered 3 times. Payments locked for {settings.PIN_LOCKOUT_MINUTES} minutes."
                )
            remaining = settings.MAX_PIN_ATTEMPTS - user.pin_failed_attempts
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Incorrect PIN. {remaining} attempt(s) remaining."
            )

        # Successful PIN check resets failures
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        db.commit()

    @staticmethod
    def execute_payment(
        db: Session,
        user: User,
        quote: PaymentQuote,
        pin: str = None,
        use_biometric: bool = False,
        device_id: str = "default_device",
        idempotency_key: str = None
    ) -> Transaction:
        """
        Executes payment state machine:
        QUOTED -> PAYMENT_PENDING -> PAID -> SETTLING -> SETTLED (or FAILED & REFUNDED)
        """
        # 1. Idempotency check
        if idempotency_key:
            existing_txn = db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).first()
            if existing_txn:
                logger.info(f"Returning idempotent transaction {existing_txn.id}")
                return existing_txn

        # 2. Strict Activation & Compliance Gate
        ActivationService.check_can_pay(db, user, quote.total_inr)

        # 3. Authentication (PIN or Biometric)
        if use_biometric:
            if not user.biometric_enabled:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Biometric authentication is not enabled on your account."
                )
        else:
            if not pin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Please enter your 6-digit App PIN to confirm payment."
                )
            PaymentService.verify_user_pin(db, user, pin)

        # 4. Fraud risk assessment
        needs_review, fraud_flags = FraudDetectionService.assess_risk(db, user, device_id, quote.total_inr)

        # 5. Check wallet balance
        if user.wallet_balance_inr < quote.total_inr:
            shortfall = quote.total_inr - user.wallet_balance_inr
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient wallet balance. Balance: ₹{user.wallet_balance_inr:.2f}, Required: ₹{quote.total_inr:.2f}. Shortfall: ₹{shortfall:.2f}. Top up wallet or use gateway checkout."
            )

        now = utcnow()
        txn_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        # Initialize transaction record
        initial_status = "UNDER_REVIEW" if needs_review else "PAID"
        txn = Transaction(
            id=txn_id,
            user_id=user.id,
            quote_id=quote.id,
            txn_type="MERCHANT_PAYMENT",
            status=initial_status,
            merchant_name=quote.merchant_name,
            merchant_city=quote.merchant_city,
            merchant_country=quote.merchant_country,
            foreign_currency=quote.foreign_currency,
            foreign_amount=quote.foreign_amount,
            inr_amount=quote.total_inr,
            wallet_deduction_inr=quote.total_inr,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now
        )

        # Deduct wallet balance
        user.wallet_balance_inr -= quote.total_inr
        quote.is_used = True
        db.add(txn)
        db.commit()
        db.refresh(txn)

        if needs_review:
            db.add(InAppNotification(
                user_id=user.id,
                title="Payment Under Security Review",
                message=f"Your payment of ₹{quote.total_inr:.2f} to {quote.merchant_name} is being reviewed.",
                category="SECURITY"
            ))
            db.commit()
            return txn

        # 6. Settle merchant via SettlementProvider
        settlement_provider = get_settlement_provider()
        txn.status = "SETTLING"
        txn.settlement_provider = settings.SETTLEMENT_PROVIDER
        db.commit()

        settlement_id = f"STL-{uuid.uuid4().hex[:10].upper()}"
        success, status_msg, details = settlement_provider.pay_merchant(
            settlement_id=settlement_id,
            merchant_name=quote.merchant_name,
            currency=quote.foreign_currency,
            amount=quote.foreign_amount,
            city=quote.merchant_city,
            country=quote.merchant_country,
            metadata={"transaction_id": txn.id, "user_id": user.id}
        )

        txn.settlement_id = settlement_id
        txn.settlement_status = status_msg

        if success:
            txn.status = "SETTLED"
            # Update LRS spending (approximate USD equivalent)
            usd_approx = (quote.inr_base_amount / Decimal("86.0")).quantize(Decimal("0.01"))
            user.lrs_annual_spent_usd += usd_approx

            db.add(AuditLog(
                user_id=user.id,
                action="PAYMENT_SETTLED",
                details=f"Txn: {txn.id}, Foreign: {quote.foreign_amount} {quote.foreign_currency}, Total INR: {quote.total_inr}"
            ))
            db.add(InAppNotification(
                user_id=user.id,
                title="Payment Successful",
                message=f"Paid {quote.foreign_amount} {quote.foreign_currency} (₹{quote.total_inr:.2f}) to {quote.merchant_name}.",
                category="PAYMENT"
            ))
        else:
            # AUTOMATIC REFUND ON SETTLEMENT FAILURE
            logger.error(f"Settlement failed for txn {txn.id}: {details}")
            txn.status = "FAILED"
            txn.failure_reason = details.get("error", "Settlement rail failure")

            # Refund wallet
            user.wallet_balance_inr += quote.total_inr
            refund_id = f"REF-{uuid.uuid4().hex[:10].upper()}"
            refund_txn = Transaction(
                id=refund_id,
                user_id=user.id,
                quote_id=quote.id,
                txn_type="REFUND",
                status="SETTLED",
                inr_amount=quote.total_inr,
                wallet_deduction_inr=-quote.total_inr,
                refund_reason=f"Auto-refund due to settlement failure: {txn.failure_reason}",
                created_at=utcnow(),
                updated_at=utcnow()
            )
            db.add(refund_txn)

            db.add(AuditLog(
                user_id=user.id,
                action="AUTO_REFUND_PROCESSED",
                details=f"Refunded ₹{quote.total_inr} to wallet for failed txn {txn.id}"
            ))
            db.add(InAppNotification(
                user_id=user.id,
                title="Payment Failed & Refunded",
                message=f"Settlement to {quote.merchant_name} failed. ₹{quote.total_inr:.2f} refunded back to your wallet.",
                category="PAYMENT"
            ))

        db.commit()
        db.refresh(txn)
        return txn
