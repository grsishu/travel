from datetime import datetime, timezone
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User, Device, AuditLog, utcnow
from app.schemas import (
    PhoneLoginRequest, VerifyOtpRequest, EmailLoginRequest, SetPinRequest,
    VerifyPinRequest, BiometricRegisterRequest, TokenResponse, UserOut
)
from app.deps import create_access_token, create_refresh_token, decode_token, get_current_user
from app.services.otp import OtpService
from app.services.activation import ActivationService

router = APIRouter(prefix="/api/auth", tags=["Authentication & Security"])

def user_to_out(user: User) -> UserOut:
    kyc_status = user.kyc_record.status if user.kyc_record else "NOT_STARTED"
    return UserOut(
        id=user.id,
        mobile=user.mobile,
        email=user.email,
        full_name=user.full_name,
        dob=user.dob,
        role=user.role,
        account_status=user.account_status,
        activation_step=user.activation_step,
        kyc_status=kyc_status,
        wallet_balance_inr=user.wallet_balance_inr,
        travel_countries=user.travel_countries or [],
        travel_purpose=user.travel_purpose,
        biometric_enabled=user.biometric_enabled,
        language=user.language,
        custom_daily_limit_inr=user.custom_daily_limit_inr,
        custom_txn_limit_inr=user.custom_txn_limit_inr,
        lrs_annual_spent_usd=user.lrs_annual_spent_usd
    )

@router.post("/phone/otp")
def request_phone_otp(payload: PhoneLoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    success, message, dev_code = OtpService.generate_and_send_otp(
        db=db,
        identifier=payload.mobile,
        purpose="LOGIN",
        ip_address=ip
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    resp = {"success": True, "message": message}
    if dev_code:
        resp["dev_otp"] = dev_code  # Helpful for test mode & automated UI testing
    return resp

@router.post("/phone/verify", response_model=TokenResponse)
def verify_phone_otp(payload: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    is_valid, msg = OtpService.verify_otp(db, payload.identifier, payload.otp, ip_address=ip)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Find or create user
    user = db.query(User).filter(User.mobile == payload.identifier).first()
    is_new = False
    if not user:
        is_new = True
        user = User(
            mobile=payload.identifier,
            account_status="INACTIVE",
            activation_step=3,  # Proceed to profile setup
            created_at=utcnow(),
            updated_at=utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Device binding check
    device = db.query(Device).filter(Device.user_id == user.id, Device.device_id == payload.device_id).first()
    if not device:
        # Register new device
        device = Device(
            user_id=user.id,
            device_id=payload.device_id,
            device_name=payload.device_name or "Mobile Browser",
            user_agent=payload.user_agent or request.headers.get("user-agent", "Unknown"),
            ip_address=ip,
            is_active=True,
            last_active_at=utcnow(),
            created_at=utcnow()
        )
        db.add(device)
        db.add(AuditLog(
            user_id=user.id,
            action="DEVICE_REGISTERED",
            details=f"Device: {payload.device_id}, Name: {payload.device_name}",
            ip_address=ip
        ))
    else:
        device.last_active_at = utcnow()
        device.is_active = True

    db.commit()
    db.refresh(user)

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_to_out(user)
    )

@router.post("/email/login", response_model=TokenResponse)
def email_login(payload: EmailLoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not bcrypt.checkpw(payload.password.encode("utf-8"), user.password_hash.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    # Device binding
    device = db.query(Device).filter(Device.user_id == user.id, Device.device_id == payload.device_id).first()
    if not device:
        device = Device(
            user_id=user.id,
            device_id=payload.device_id,
            device_name=payload.device_name or "Browser",
            user_agent=payload.user_agent or request.headers.get("user-agent", "Unknown"),
            ip_address=ip,
            is_active=True,
            last_active_at=utcnow(),
            created_at=utcnow()
        )
        db.add(device)

    db.add(AuditLog(user_id=user.id, action="USER_LOGIN_EMAIL", details=f"Email: {user.email}", ip_address=ip))
    db.commit()

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_to_out(user)
    )

@router.post("/pin/set")
def set_pin(payload: SetPinRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    salt = bcrypt.gensalt()
    pin_hash = bcrypt.hashpw(payload.pin.encode("utf-8"), salt).decode("utf-8")
    user.pin_hash = pin_hash
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    if user.activation_step < 6:
        user.activation_step = 6
    db.add(AuditLog(user_id=user.id, action="PIN_SET", details="6-digit App PIN created/updated."))
    db.commit()
    return {"success": True, "message": "App PIN created successfully."}

@router.post("/pin/verify")
def verify_pin(payload: VerifyPinRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.payments import PaymentService
    PaymentService.verify_user_pin(db, user, payload.pin)
    return {"success": True, "message": "PIN verified successfully."}

@router.post("/biometric/register")
def register_biometric(
    payload: BiometricRegisterRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user.biometric_credential_id = payload.credential_id
    user.biometric_public_key = payload.public_key
    user.biometric_enabled = True
    db.add(AuditLog(user_id=user.id, action="BIOMETRIC_REGISTERED", details=f"Cred: {payload.credential_id}"))
    db.commit()
    return {"success": True, "message": "Biometric unlock registered successfully."}

@router.post("/biometric/toggle")
def toggle_biometric(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user.biometric_enabled = not user.biometric_enabled
    db.add(AuditLog(user_id=user.id, action="BIOMETRIC_TOGGLED", details=f"Enabled: {user.biometric_enabled}"))
    db.commit()
    return {"success": True, "biometric_enabled": user.biometric_enabled}

@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user_to_out(user)

