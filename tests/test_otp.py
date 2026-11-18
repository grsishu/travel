import pytest
from datetime import datetime, timezone, timedelta
from app.services.otp import OtpService
from app.models import OTPVerification, utcnow

def test_otp_generation_and_verification(db):
    phone = "+919123456780"
    success, msg, code = OtpService.generate_and_send_otp(db, phone, purpose="LOGIN")
    assert success is True
    assert code is not None
    assert len(code) == 6

    # Verify correct code
    is_valid, v_msg = OtpService.verify_otp(db, phone, code)
    assert is_valid is True
    assert "successfully" in v_msg

def test_otp_resend_cooldown(db):
    phone = "+919123456781"
    success1, _, _ = OtpService.generate_and_send_otp(db, phone)
    assert success1 is True

    # Immediate second request should fail due to 30s cooldown
    success2, msg2, _ = OtpService.generate_and_send_otp(db, phone)
    assert success2 is False
    assert "wait" in msg2.lower()

def test_otp_max_attempts(db):
    phone = "+919123456782"
    success, _, real_code = OtpService.generate_and_send_otp(db, phone)
    assert success is True

    # Wrong attempt 1
    v1, _ = OtpService.verify_otp(db, phone, "000000")
    assert v1 is False

    # Wrong attempt 2
    v2, _ = OtpService.verify_otp(db, phone, "000001")
    assert v2 is False

    # Wrong attempt 3 (Max reached)
    v3, msg3 = OtpService.verify_otp(db, phone, "000002")
    assert v3 is False
    assert "Maximum attempts exceeded" in msg3

    # Subsequent attempt with even the REAL code should now fail!
    v4, msg4 = OtpService.verify_otp(db, phone, real_code)
    assert v4 is False
    assert "Maximum OTP attempts exceeded" in msg4

def test_otp_expiry(db):
    phone = "+919123456783"
    success, _, code = OtpService.generate_and_send_otp(db, phone)
    assert success is True

    # Artificially expire the OTP record
    otp_rec = db.query(OTPVerification).filter(OTPVerification.identifier == phone).first()
    otp_rec.expires_at = utcnow() - timedelta(minutes=10)
    db.commit()

    is_valid, msg = OtpService.verify_otp(db, phone, code)
    assert is_valid is False
    assert "expired" in msg.lower()

