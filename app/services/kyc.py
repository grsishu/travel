import os
import re
import uuid
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from app.config import settings
from app.models import KYCRecord, User, AuditLog, InAppNotification, utcnow

def get_fernet_cipher() -> Fernet:
    key = settings.PAN_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)

def encrypt_pan(pan: str) -> str:
    cipher = get_fernet_cipher()
    return cipher.encrypt(pan.strip().upper().encode()).decode()

def decrypt_pan(encrypted_pan: str) -> str:
    cipher = get_fernet_cipher()
    return cipher.decrypt(encrypted_pan.encode()).decode()

def mask_pan(pan: str) -> str:
    cleaned = pan.strip().upper()
    if len(cleaned) == 10:
        return f"{cleaned[:5]}****{cleaned[-1]}"
    return cleaned

class SandboxKycProvider:
    """
    Test Mode KYC verification provider.
    Auto-validates PAN format and auto-approves or approves on click.
    """
    @staticmethod
    def verify(pan: str, name: str) -> Tuple[bool, str]:
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan):
            return False, "Invalid PAN format."
        return True, "Instant verification successful (Sandbox Mode)"

class KycService:
    @staticmethod
    def submit_kyc(
        db: Session,
        user: User,
        pan_number: str,
        full_name_on_pan: str,
        address: str,
        passport_number: Optional[str] = None,
        selfie_filename: Optional[str] = None,
        doc_filename: Optional[str] = None,
        auto_approve_in_sandbox: bool = True
    ) -> KYCRecord:
        cleaned_pan = pan_number.strip().upper()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", cleaned_pan):
            raise ValueError("Invalid PAN format. Must be 5 uppercase letters, 4 digits, 1 uppercase letter.")

        encrypted = encrypt_pan(cleaned_pan)
        masked = mask_pan(cleaned_pan)

        record = db.query(KYCRecord).filter(KYCRecord.user_id == user.id).first()
        now = utcnow()

        if not record:
            record = KYCRecord(
                user_id=user.id,
                pan_number_encrypted=encrypted,
                pan_number_masked=masked,
                full_name_on_pan=full_name_on_pan,
                address=address,
                passport_number=passport_number,
                selfie_file_path=selfie_filename,
                document_file_path=doc_filename,
                status="SUBMITTED",
                created_at=now,
                updated_at=now
            )
            db.add(record)
        else:
            record.pan_number_encrypted = encrypted
            record.pan_number_masked = masked
            record.full_name_on_pan = full_name_on_pan
            record.address = address
            record.passport_number = passport_number
            if selfie_filename:
                record.selfie_file_path = selfie_filename
            if doc_filename:
                record.document_file_path = doc_filename
            record.status = "SUBMITTED"
            record.rejection_reason = None
            record.updated_at = now

        # Update user activation step if advancing
        if user.activation_step < 6:
            user.activation_step = 6

        db.commit()
        db.refresh(record)

        # Audit log
        db.add(AuditLog(
            user_id=user.id,
            action="KYC_SUBMITTED",
            details=f"PAN Masked: {masked}, Name: {full_name_on_pan}"
        ))
        db.commit()

        # If in test mode and auto-approval requested
        if settings.TEST_MODE and auto_approve_in_sandbox and settings.KYC_PROVIDER == "sandbox":
            KycService.approve_kyc(db, record.id, approved_by="SandboxKycProvider (Auto)")

        db.refresh(record)
        return record

    @staticmethod
    def approve_kyc(db: Session, kyc_id: int, approved_by: str = "ADMIN") -> KYCRecord:
        record = db.query(KYCRecord).filter(KYCRecord.id == kyc_id).first()
        if not record:
            raise ValueError("KYC Record not found")

        record.status = "VERIFIED"
        record.verified_at = utcnow()
        record.verified_by = approved_by
        record.rejection_reason = None

        user = record.user
        if user.activation_step < 7:
            user.activation_step = 7

        db.add(AuditLog(
            user_id=user.id,
            action="KYC_VERIFIED",
            details=f"Approved by: {approved_by}"
        ))

        db.add(InAppNotification(
            user_id=user.id,
            title="KYC Verified Successfully",
            message="Your Identity and PAN verification is complete. You can now add funds.",
            category="KYC"
        ))

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def reject_kyc(db: Session, kyc_id: int, reason: str, rejected_by: str = "ADMIN") -> KYCRecord:
        record = db.query(KYCRecord).filter(KYCRecord.id == kyc_id).first()
        if not record:
            raise ValueError("KYC Record not found")

        record.status = "REJECTED"
        record.rejection_reason = reason
        record.verified_by = rejected_by

        user = record.user
        db.add(AuditLog(
            user_id=user.id,
            action="KYC_REJECTED",
            details=f"Rejected by: {rejected_by}, Reason: {reason}"
        ))

        db.add(InAppNotification(
            user_id=user.id,
            title="KYC Verification Update",
            message=f"Your KYC submission was rejected: {reason}. Please re-submit valid documents.",
            category="KYC"
        ))

        db.commit()
        db.refresh(record)
        return record

