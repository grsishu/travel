import hmac
import hashlib
import json
import logging
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import Transaction, User, AuditLog, InAppNotification, utcnow

logger = logging.getLogger("travelpay.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["Payment Gateway Webhooks"])

@router.post("/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Razorpay Webhook receiver with HMAC SHA-256 signature verification and idempotency.
    """
    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Razorpay-Signature header.")

    body_bytes = await request.body()
    secret = settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8")
    expected_signature = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()

    # In production or strict check
    if not hmac.compare_digest(expected_signature, signature) and not settings.TEST_MODE:
        logger.warning("Razorpay webhook signature verification failed.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")

    try:
        event_data = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    event_type = event_data.get("event")
    payload = event_data.get("payload", {})
    payment_entity = payload.get("payment", {}).get("entity", {})
    payment_id = payment_entity.get("id")

    if not payment_id:
        return {"status": "ignored", "reason": "No payment entity found"}

    # IDEMPOTENCY CHECK
    existing_txn = db.query(Transaction).filter(Transaction.gateway_payment_id == payment_id).first()
    if existing_txn:
        logger.info(f"[WEBHOOK] Payment {payment_id} already processed. Skipping idempotently.")
        return {"status": "ok", "message": "Already processed"}

    # Process captured payment
    if event_type in ["payment.captured", "order.paid"]:
        amount_subunits = payment_entity.get("amount", 0)
        amount_inr = (Decimal(str(amount_subunits)) / Decimal("100")).quantize(Decimal("0.01"))
        notes = payment_entity.get("notes", {})
        user_id_str = notes.get("user_id")

        if user_id_str:
            user = db.query(User).filter(User.id == int(user_id_str)).first()
            if user:
                user.wallet_balance_inr += amount_inr
                if user.activation_step < 8:
                    user.activation_step = 8

                txn = Transaction(
                    id=f"HOOK-{payment_id}",
                    user_id=user.id,
                    txn_type="WALLET_TOPUP",
                    status="SETTLED",
                    inr_amount=amount_inr,
                    wallet_deduction_inr=-amount_inr,
                    gateway_payment_id=payment_id,
                    gateway_order_id=payment_entity.get("order_id"),
                    settlement_id=f"WEBHOOK-{payment_id}",
                    created_at=utcnow(),
                    updated_at=utcnow()
                )
                db.add(txn)
                db.add(AuditLog(
                    user_id=user.id,
                    action="WEBHOOK_PAYMENT_CAPTURED",
                    details=f"Razorpay Payment {payment_id} captured: ₹{amount_inr}"
                ))
                db.commit()
                logger.info(f"[WEBHOOK] Credited ₹{amount_inr} to user {user.id}")

    return {"status": "ok", "event": event_type}

