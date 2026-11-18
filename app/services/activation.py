from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Tuple
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.config import settings
from app.models import User, KYCRecord, Transaction, utcnow
from app.schemas import ChecklistStep

class ActivationService:
    @staticmethod
    def get_activation_checklist(user: User) -> List[ChecklistStep]:
        kyc_status = user.kyc_record.status if user.kyc_record else "NOT_STARTED"
        has_profile = bool(user.full_name and user.email and user.dob)
        has_device = len(user.devices) > 0
        has_pin = user.pin_hash is not None
        has_kyc_verified = (kyc_status == "VERIFIED")
        has_funded = (user.wallet_balance_inr > Decimal("0.00")) or (
            any(t.txn_type == "WALLET_TOPUP" and t.status == "SETTLED" for t in user.transactions)
        )
        is_international_active = (user.account_status == "ACTIVE")

        steps = [
            ChecklistStep(
                step_number=1,
                key="welcome",
                title="Get Started",
                description="Welcome to TravelPay for seamless international QR payments.",
                completed=True,
                is_current=False
            ),
            ChecklistStep(
                step_number=2,
                key="login",
                title="Mobile & OTP Verification",
                description="Phone number verified with high-security 6-digit OTP.",
                completed=bool(user.mobile or user.email),
                is_current=False
            ),
            ChecklistStep(
                step_number=3,
                key="profile",
                title="Profile Setup",
                description="Full Name, Email & Date of Birth (18+ requirement).",
                completed=has_profile,
                is_current=not has_profile
            ),
            ChecklistStep(
                step_number=4,
                key="device",
                title="Device Binding",
                description="Hardware fingerprint & trusted device registration.",
                completed=has_device,
                is_current=has_profile and not has_device
            ),
            ChecklistStep(
                step_number=5,
                key="pin",
                title="App PIN & Biometrics",
                description="Set 6-digit PIN and optional WebAuthn passkey unlock.",
                completed=has_pin,
                is_current=has_profile and has_device and not has_pin
            ),
            ChecklistStep(
                step_number=6,
                key="kyc",
                title="PAN Identity Verification (KYC)",
                description="PAN validation, address & document verification.",
                completed=has_kyc_verified,
                is_current=has_pin and not has_kyc_verified
            ),
            ChecklistStep(
                step_number=7,
                key="funding",
                title="Add INR Wallet Funds",
                description="Add initial travel balance in INR via Razorpay gateway.",
                completed=has_funded,
                is_current=has_kyc_verified and not has_funded
            ),
            ChecklistStep(
                step_number=8,
                key="activate",
                title="Activate International Payments",
                description="Destination countries, FEMA/LRS declaration & spending limit.",
                completed=is_international_active,
                is_current=has_kyc_verified and has_funded and not is_international_active
            )
        ]
        return steps

    @classmethod
    def check_can_pay(cls, db: Session, user: User, inr_amount: Decimal, foreign_amount_usd: Decimal = None):
        """
        STRICT ENFORCEMENT GATE:
        Must be ACTIVE, KYC VERIFIED, PIN set, not frozen, within daily and LRS limits.
        Raises HTTPException if any condition fails.
        """
        # 1. Account freeze check
        if user.account_status == "FROZEN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your TravelPay account is currently frozen by administration. Contact support."
            )

        if user.account_status == "PAUSED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="International payments are currently paused. Resume from Settings -> Security."
            )

        # 2. Account active check
        if user.account_status != "ACTIVE":
            checklist = cls.get_activation_checklist(user)
            next_step = next((s for s in checklist if not s.completed), None)
            step_msg = f"Step '{next_step.title}' is pending." if next_step else "Account not active."
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account must be ACTIVE to pay. {step_msg}"
            )

        # 3. KYC Verified check
        if not user.kyc_record or user.kyc_record.status != "VERIFIED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="KYC verification is required before making foreign merchant payments."
            )

        # 4. PIN check
        if not user.pin_hash:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security App PIN is not set. Please set a 6-digit PIN."
            )

        # 5. PIN lockout check
        if user.pin_locked_until:
            now = utcnow()
            lock_until = user.pin_locked_until.replace(tzinfo=timezone.utc)
            if now < lock_until:
                diff_mins = int((lock_until - now).total_seconds() / 60) + 1
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"PIN temporarily locked due to repeated failed attempts. Try again in {diff_mins} minutes."
                )
            else:
                # Expired lockout, reset counter
                user.pin_failed_attempts = 0
                user.pin_locked_until = None
                db.commit()

        # 6. Per-transaction limit check
        txn_limit = user.custom_txn_limit_inr or settings.DEFAULT_PER_TXN_LIMIT_INR
        if inr_amount > txn_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Amount ₹{inr_amount:.2f} exceeds your per-transaction limit of ₹{txn_limit:.2f}. Adjust in Settings."
            )

        # 7. Daily limit check
        now = utcnow()
        start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        daily_spent = (
            db.query(func.coalesce(func.sum(Transaction.inr_amount), Decimal("0.00")))
            .filter(
                Transaction.user_id == user.id,
                Transaction.txn_type == "MERCHANT_PAYMENT",
                Transaction.status.in_(["PAID", "SETTLING", "SETTLED"]),
                Transaction.created_at >= start_of_day
            )
            .scalar()
        )
        daily_limit = user.custom_daily_limit_inr or settings.DEFAULT_DAILY_LIMIT_INR
        if (daily_spent + inr_amount) > daily_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment would exceed your daily spending limit of ₹{daily_limit:.2f} (Already spent today: ₹{daily_spent:.2f})."
            )

        # 8. LRS USD 250,000 Annual limit check
        if foreign_amount_usd is not None:
            annual_limit_usd = settings.LRS_ANNUAL_LIMIT_USD
            if (user.lrs_annual_spent_usd + foreign_amount_usd) > annual_limit_usd:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Payment would exceed the annual RBI LRS limit of USD {annual_limit_usd:,.2f}."
                )

        return True

