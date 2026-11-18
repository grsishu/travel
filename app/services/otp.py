import abc
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.config import settings
from app.models import OTPVerification, AuditLog, utcnow

logger = logging.getLogger("travelpay.otp")

class OtpProvider(abc.ABC):
    @abc.abstractmethod
    def send_otp(self, identifier: str, code: str, purpose: str) -> bool:
        pass

class ConsoleOtpProvider(OtpProvider):
    def send_otp(self, identifier: str, code: str, purpose: str) -> bool:
        logger.info(f"[DEV OTP] Purpose={purpose} Identifier={identifier} OTP={code}")
        print(f"\n==========================================")
        print(f" [TravelPay DEV OTP] To: {identifier}")
        print(f" Code: >>> {code} <<< (Valid 5 mins)")
        print(f"==========================================\n")
        return True

class TwilioOtpProvider(OtpProvider):
    """Production Twilio SMS Provider Skeleton"""
    def send_otp(self, identifier: str, code: str, purpose: str) -> bool:
        if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER):
            logger.warning("Twilio credentials not configured; falling back to console.")
            return ConsoleOtpProvider().send_otp(identifier, code, purpose)
        try:
            # SKELETON: Real production implementation calls Twilio REST API
            # import httpx
            # response = httpx.post(...)
            logger.info(f"Twilio SMS dispatched to {identifier} with code {code}")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch Twilio OTP: {e}")
            return False

class Msg91OtpProvider(OtpProvider):
    """Production MSG91 Indian SMS Provider Skeleton"""
    def send_otp(self, identifier: str, code: str, purpose: str) -> bool:
        if not (settings.MSG91_AUTH_KEY and settings.MSG91_SENDER_ID):
            logger.warning("MSG91 credentials not configured; falling back to console.")
            return ConsoleOtpProvider().send_otp(identifier, code, purpose)
        try:
            # SKELETON: Real production implementation calls MSG91 OTP API
            logger.info(f"MSG91 SMS dispatched to {identifier}")
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch MSG91 OTP: {e}")
            return False

def get_otp_provider() -> OtpProvider:
    if settings.OTP_PROVIDER.lower() == "twilio":
        return TwilioOtpProvider()
    elif settings.OTP_PROVIDER.lower() == "msg91":
        return Msg91OtpProvider()
    return ConsoleOtpProvider()

class OtpService:
    @staticmethod
    def generate_and_send_otp(
        db: Session,
        identifier: str,
        purpose: str = "LOGIN",
        ip_address: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Generates 6-digit OTP, checks 30s cooldown and rate-limits, dispatches OTP.
        Returns: (success: bool, message: str, dev_otp_code: Optional[str])
        """
        now = utcnow()

        # Check existing active OTP for cooldown
        latest = (
            db.query(OTPVerification)
            .filter(OTPVerification.identifier == identifier)
            .order_by(OTPVerification.id.desc())
            .first()
        )

        if latest and not latest.is_verified:
            # Check 30s cooldown
            diff = (now - latest.last_sent_at.replace(tzinfo=timezone.utc)).total_seconds()
            if diff < settings.OTP_RESEND_COOLDOWN_SECONDS:
                wait_left = int(settings.OTP_RESEND_COOLDOWN_SECONDS - diff)
                return False, f"Please wait {wait_left}s before requesting a new OTP.", None

        # Check rate-limit: max 5 requests per hour
        one_hour_ago = now - timedelta(hours=1)
        recent_count = (
            db.query(OTPVerification)
            .filter(
                OTPVerification.identifier == identifier,
                OTPVerification.created_at >= one_hour_ago
            )
            .count()
        )
        if recent_count >= 5:
            return False, "Too many OTP requests. Please try again after an hour.", None

        # Generate 6-digit numeric code
        otp_code = f"{secrets.randbelow(900000) + 100000:06d}"
        expires_at = now + timedelta(seconds=settings.OTP_EXPIRY_SECONDS)

        record = OTPVerification(
            identifier=identifier,
            otp_code=otp_code,
            attempts=0,
            max_attempts=settings.OTP_MAX_ATTEMPTS,
            expires_at=expires_at,
            last_sent_at=now,
            is_verified=False,
            purpose=purpose,
            created_at=now
        )
        db.add(record)

        audit = AuditLog(
            user_id=None,
            action="OTP_REQUESTED",
            details=f"Purpose: {purpose}, Identifier: {identifier}",
            ip_address=ip_address
        )
        db.add(audit)
        db.commit()
        db.refresh(record)

        provider = get_otp_provider()
        provider.send_otp(identifier, otp_code, purpose)

        # In test mode or console provider, return code to ease dev & test
        dev_code = otp_code if settings.TEST_MODE else None
        return True, "OTP sent successfully to your mobile.", dev_code

    @staticmethod
    def verify_otp(
        db: Session,
        identifier: str,
        code: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Verifies 6-digit OTP, increments attempt count, checks expiry and max attempts.
        """
        now = utcnow()
        record = (
            db.query(OTPVerification)
            .filter(
                OTPVerification.identifier == identifier,
                OTPVerification.is_verified == False
            )
            .order_by(OTPVerification.id.desc())
            .first()
        )

        if not record:
            return False, "No active OTP request found. Please request a new one."

        # Check attempts
        if record.attempts >= record.max_attempts:
            return False, "Maximum OTP attempts exceeded. Please request a new OTP."

        # Check expiry
        exp = record.expires_at.replace(tzinfo=timezone.utc)
        if now > exp:
            return False, "OTP has expired. Please request a new OTP."

        record.attempts += 1
        db.commit()

        if record.otp_code != code:
            remaining = record.max_attempts - record.attempts
            if remaining <= 0:
                return False, "Incorrect OTP. Maximum attempts exceeded. Please request a new OTP."
            return False, f"Incorrect OTP. {remaining} attempt(s) remaining."

        # Mark verified
        record.is_verified = True
        audit = AuditLog(
            user_id=None,
            action="OTP_VERIFIED",
            details=f"Identifier: {identifier}, Purpose: {record.purpose}",
            ip_address=ip_address
        )
        db.add(audit)
        db.commit()
        return True, "OTP verified successfully."

