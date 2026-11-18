import uuid
from decimal import Decimal
from typing import List, Optional
import hmac
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, Transaction, AuditLog, InAppNotification, utcnow
from app.schemas import (
    WalletBalanceResponse, WalletTopupRequest, WalletTopupOrderResponse, TransactionOut
)
from app.deps import get_current_user

router = APIRouter(prefix="/api/wallet", tags=["Wallet & Funds"])

class VerifyTopupPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    amount_inr: Decimal

@router.get("/balance", response_model=WalletBalanceResponse)
def get_balance(user: User = Depends(get_current_user)):
    return WalletBalanceResponse(balance_inr=user.wallet_balance_inr)

@router.post("/topup/order", response_model=WalletTopupOrderResponse)
def create_topup_order(payload: WalletTopupRequest, user: User = Depends(get_current_user)):
    subunits = int(payload.amount_inr * Decimal("100"))
    receipt_id = f"rcpt_topup_{user.id}_{uuid.uuid4().hex[:6]}"

    # Try creating order with Razorpay client if configured
    order_id = f"order_{uuid.uuid4().hex[:14]}"
    try:
        import razorpay
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        rp_order = client.order.create({
            "amount": subunits,
            "currency": "INR",
            "receipt": receipt_id,
            "notes": {"user_id": str(user.id), "purpose": "TravelPay Wallet Topup"}
        })
        order_id = rp_order["id"]
    except Exception:
        # In test mode or offline mock
        pass

    return WalletTopupOrderResponse(
        order_id=order_id,
        amount_inr=payload.amount_inr,
        amount_subunits=subunits,
        currency="INR",
        razorpay_key_id=settings.RAZORPAY_KEY_ID
    )

@router.post("/topup/verify")
def verify_topup_payment(
    payload: VerifyTopupPaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify HMAC signature in production or valid check
    secret = settings.RAZORPAY_KEY_SECRET.encode("utf-8")
    data_to_sign = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}".encode("utf-8")
    expected_sig = hmac.new(secret, data_to_sign, hashlib.sha256).hexdigest()

    # In test mode, allow simulated signatures or verified match
    sig_valid = (expected_sig == payload.razorpay_signature)
    if not sig_valid and not settings.TEST_MODE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature from payment gateway."
        )

    # Credit wallet
    user.wallet_balance_inr += payload.amount_inr
    if user.activation_step < 8:
        user.activation_step = 8

    txn = Transaction(
        id=f"TOPUP-{uuid.uuid4().hex[:10].upper()}",
        user_id=user.id,
        txn_type="WALLET_TOPUP",
        status="SETTLED",
        inr_amount=payload.amount_inr,
        wallet_deduction_inr=-payload.amount_inr,
        gateway_order_id=payload.razorpay_order_id,
        gateway_payment_id=payload.razorpay_payment_id,
        settlement_id=f"GATEWAY-{payload.razorpay_payment_id}",
        created_at=utcnow(),
        updated_at=utcnow()
    )
    db.add(txn)

    db.add(AuditLog(
        user_id=user.id,
        action="WALLET_TOPUP_SUCCESS",
        details=f"Amount: ₹{payload.amount_inr:.2f}, PaymentID: {payload.razorpay_payment_id}"
    ))

    db.add(InAppNotification(
        user_id=user.id,
        title="Funds Added Successfully",
        message=f"₹{payload.amount_inr:,.2f} added to your TravelPay wallet.",
        category="PAYMENT"
    ))

    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": f"Successfully added ₹{payload.amount_inr:,.2f} to wallet.",
        "new_balance": float(user.wallet_balance_inr)
    }

@router.get("/transactions", response_model=List[TransactionOut])
def list_transactions(
    status_filter: Optional[str] = None,
    txn_type: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Transaction).filter(Transaction.user_id == user.id)
    if status_filter:
        query = query.filter(Transaction.status == status_filter)
    if txn_type:
        query = query.filter(Transaction.txn_type == txn_type)
    txns = query.order_by(Transaction.created_at.desc()).limit(50).all()

    return [
        TransactionOut(
            id=t.id,
            txn_type=t.txn_type,
            status=t.status,
            merchant_name=t.merchant_name,
            merchant_city=t.merchant_city,
            merchant_country=t.merchant_country,
            foreign_currency=t.foreign_currency,
            foreign_amount=t.foreign_amount,
            inr_amount=t.inr_amount,
            wallet_deduction_inr=t.wallet_deduction_inr,
            settlement_id=t.settlement_id,
            settlement_provider=t.settlement_provider,
            settlement_status=t.settlement_status,
            failure_reason=t.failure_reason,
            refund_reason=t.refund_reason,
            created_at=t.created_at
        ) for t in txns
    ]

