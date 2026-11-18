from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Device, AuditLog, InAppNotification, utcnow
from app.schemas import (
    ProfileSetupRequest, ActivateInternationalRequest, ActivationStatusResponse,
    DeviceOut, UserOut
)
from app.deps import get_current_user
from app.services.activation import ActivationService
from app.routers.auth import user_to_out

router = APIRouter(prefix="/api/onboarding", tags=["Onboarding & Activation Flow"])

@router.get("/status", response_model=ActivationStatusResponse)
def get_activation_status(user: User = Depends(get_current_user)):
    checklist = ActivationService.get_activation_checklist(user)
    kyc_status = user.kyc_record.status if user.kyc_record else "NOT_STARTED"
    return ActivationStatusResponse(
        account_status=user.account_status,
        kyc_status=kyc_status,
        current_step=user.activation_step,
        total_steps=8,
        is_active=(user.account_status == "ACTIVE"),
        checklist=checklist
    )

@router.post("/profile", response_model=UserOut)
def setup_profile(payload: ProfileSetupRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Check if email is already taken by another user
    existing = db.query(User).filter(User.email == payload.email, User.id != user.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is already associated with another account."
        )

    user.full_name = payload.full_name
    user.email = payload.email
    user.dob = payload.dob
    if user.activation_step < 4:
        user.activation_step = 4

    db.add(AuditLog(
        user_id=user.id,
        action="PROFILE_COMPLETED",
        details=f"Name: {payload.full_name}, Email: {payload.email}, DOB: {payload.dob}"
    ))
    db.commit()
    db.refresh(user)
    return user_to_out(user)

@router.get("/devices", response_model=List[DeviceOut])
def get_devices(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_device_id = request.headers.get("X-Device-Id")
    devices = db.query(Device).filter(Device.user_id == user.id, Device.is_active == True).all()
    out = []
    for d in devices:
        out.append(DeviceOut(
            id=d.id,
            device_id=d.device_id,
            device_name=d.device_name,
            user_agent=d.user_agent,
            ip_address=d.ip_address,
            is_active=d.is_active,
            last_active_at=d.last_active_at,
            is_current=(d.device_id == current_device_id)
        ))
    return out

@router.delete("/devices/{device_id}")
def revoke_device(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.user_id == user.id, Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
    device.is_active = False
    db.add(AuditLog(user_id=user.id, action="DEVICE_REVOKED", details=f"Revoked Device: {device_id}"))
    db.commit()
    return {"success": True, "message": f"Device '{device.device_name}' revoked successfully."}

@router.post("/activate-international", response_model=UserOut)
def activate_international(
    payload: ActivateInternationalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Ensure KYC is VERIFIED
    if not user.kyc_record or user.kyc_record.status != "VERIFIED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity verification (KYC) must be VERIFIED before activating international payments."
        )

    # Ensure PIN is set
    if not user.pin_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set your 6-digit App PIN before activating."
        )

    user.travel_countries = payload.countries
    user.travel_purpose = payload.travel_purpose
    user.custom_daily_limit_inr = payload.custom_daily_limit_inr
    user.custom_txn_limit_inr = payload.custom_txn_limit_inr
    user.terms_accepted = payload.terms_accepted
    user.fema_declaration_accepted = payload.fema_declaration_accepted
    user.account_status = "ACTIVE"
    user.activation_step = 9  # Full completion

    db.add(AuditLog(
        user_id=user.id,
        action="ACCOUNT_ACTIVATED",
        details=f"Countries: {','.join(payload.countries)}, Purpose: {payload.travel_purpose}, Daily Limit: ₹{payload.custom_daily_limit_inr}"
    ))

    db.add(InAppNotification(
        user_id=user.id,
        title="International Payments Activated! 🌏",
        message="Your TravelPay account is now fully active. You can now scan and pay foreign merchant QRs.",
        category="ACTIVATION"
    ))

    db.commit()
    db.refresh(user)
    return user_to_out(user)

@router.post("/pause-international")
def pause_international(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.account_status == "FROZEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is frozen.")
    user.account_status = "PAUSED"
    db.add(AuditLog(user_id=user.id, action="PAYMENTS_PAUSED", details="User paused international payments."))
    db.commit()
    return {"success": True, "account_status": "PAUSED"}

@router.post("/resume-international")
def resume_international(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.account_status == "FROZEN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is frozen.")
    user.account_status = "ACTIVE"
    db.add(AuditLog(user_id=user.id, action="PAYMENTS_RESUMED", details="User resumed international payments."))
    db.commit()
    return {"success": True, "account_status": "ACTIVE"}

