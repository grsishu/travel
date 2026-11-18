from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, KYCRecord, Transaction, AuditLog, InAppNotification, utcnow
from app.deps import get_current_admin
from app.services.kyc import KycService

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])

class KYCActionRequest(BaseModel):
    action: str  # APPROVE, REJECT
    reason: Optional[str] = "Admin review rejection"

class FreezeUserRequest(BaseModel):
    freeze: bool
    reason: Optional[str] = "Administrative review"

class ManualRefundRequest(BaseModel):
    reason: str

class UpdateFeeConfigRequest(BaseModel):
    markup_percent: Decimal
    gst_percent: Decimal

@router.get("/users")
def list_all_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.desc()).all()
    out = []
    for u in users:
        kyc = u.kyc_record.status if u.kyc_record else "NOT_STARTED"
        out.append({
            "id": u.id,
            "mobile": u.mobile,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "account_status": u.account_status,
            "activation_step": u.activation_step,
            "kyc_status": kyc,
            "wallet_balance_inr": float(u.wallet_balance_inr),
            "created_at": u.created_at.isoformat()
        })
    return out

@router.get("/kyc/pending")
def list_pending_kyc(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    records = db.query(KYCRecord).filter(KYCRecord.status.in_(["SUBMITTED", "NOT_STARTED"])).all()
    out = []
    for r in records:
        out.append({
            "id": r.id,
            "user_id": r.user_id,
            "full_name": r.full_name_on_pan,
            "pan_masked": r.pan_number_masked,
            "address": r.address,
            "passport_number": r.passport_number,
            "status": r.status,
            "created_at": r.created_at.isoformat()
        })
    return out

@router.post("/kyc/{kyc_id}/action")
def act_on_kyc(
    kyc_id: int,
    payload: KYCActionRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if payload.action.upper() == "APPROVE":
        rec = KycService.approve_kyc(db, kyc_id, approved_by=f"ADMIN:{admin.email or admin.id}")
        return {"success": True, "status": rec.status, "message": "KYC Approved"}
    elif payload.action.upper() == "REJECT":
        rec = KycService.reject_kyc(db, kyc_id, reason=payload.reason, rejected_by=f"ADMIN:{admin.email or admin.id}")
        return {"success": True, "status": rec.status, "message": "KYC Rejected"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Must be APPROVE or REJECT.")

@router.post("/users/{user_id}/freeze")
def toggle_user_freeze(
    user_id: int,
    payload: FreezeUserRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.freeze:
        user.account_status = "FROZEN"
        action = "USER_FROZEN_BY_ADMIN"
    else:
        user.account_status = "ACTIVE" if (user.kyc_record and user.kyc_record.status == "VERIFIED") else "INACTIVE"
        action = "USER_UNFROZEN_BY_ADMIN"

    db.add(AuditLog(user_id=user.id, action=action, details=f"Admin {admin.email}: {payload.reason}"))
    db.commit()
    return {"success": True, "account_status": user.account_status}

@router.get("/transactions")
def list_all_transactions(
    status_filter: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Transaction)
    if status_filter:
        query = query.filter(Transaction.status == status_filter)
    txns = query.order_by(Transaction.created_at.desc()).limit(100).all()
    return [
        {
            "id": t.id,
            "user_id": t.user_id,
            "txn_type": t.txn_type,
            "status": t.status,
            "merchant_name": t.merchant_name,
            "foreign_amount": float(t.foreign_amount) if t.foreign_amount else None,
            "foreign_currency": t.foreign_currency,
            "inr_amount": float(t.inr_amount),
            "settlement_id": t.settlement_id,
            "settlement_provider": t.settlement_provider,
            "failure_reason": t.failure_reason,
            "created_at": t.created_at.isoformat()
        } for t in txns
    ]

@router.get("/fraud-queue")
def list_fraud_review_queue(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    txns = db.query(Transaction).filter(Transaction.status == "UNDER_REVIEW").all()
    return [
        {
            "id": t.id,
            "user_id": t.user_id,
            "merchant_name": t.merchant_name,
            "inr_amount": float(t.inr_amount),
            "created_at": t.created_at.isoformat()
        } for t in txns
    ]

@router.post("/transactions/{txn_id}/manual-refund")
def manual_refund(
    txn_id: str,
    payload: ManualRefundRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if txn.status == "REFUNDED":
        raise HTTPException(status_code=400, detail="Transaction has already been refunded.")

    user = txn.user
    user.wallet_balance_inr += txn.inr_amount
    txn.status = "REFUNDED"
    txn.refund_reason = f"Manual refund by Admin: {payload.reason}"

    db.add(AuditLog(
        user_id=user.id,
        action="MANUAL_REFUND_ADMIN",
        details=f"Txn: {txn.id}, Amount: ₹{txn.inr_amount}, Admin: {admin.email}"
    ))

    db.add(InAppNotification(
        user_id=user.id,
        title="Payment Refunded",
        message=f"₹{txn.inr_amount:,.2f} refunded to your wallet by support.",
        category="PAYMENT"
    ))

    db.commit()
    return {"success": True, "message": f"Refund of ₹{txn.inr_amount} processed."}

@router.get("/fee-config")
def get_fee_config(admin: User = Depends(get_current_admin)):
    return {
        "markup_percent": float(settings.MARKUP_PERCENT),
        "gst_percent": float(settings.GST_PERCENT)
    }

@router.post("/fee-config")
def update_fee_config(payload: UpdateFeeConfigRequest, admin: User = Depends(get_current_admin)):
    settings.MARKUP_PERCENT = payload.markup_percent
    settings.GST_PERCENT = payload.gst_percent
    return {
        "success": True,
        "markup_percent": float(settings.MARKUP_PERCENT),
        "gst_percent": float(settings.GST_PERCENT)
    }

