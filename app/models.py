import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Numeric, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from app.db import Base

def utcnow():
    return datetime.now(timezone.utc)

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String(30), unique=True, index=True, nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    full_name = Column(String(150), nullable=True)
    dob = Column(String(20), nullable=True)  # YYYY-MM-DD
    role = Column(String(20), default="USER", nullable=False)  # USER, ADMIN

    # Activation & Status
    account_status = Column(String(20), default="INACTIVE", nullable=False)  # INACTIVE, ACTIVE, PAUSED, FROZEN
    activation_step = Column(Integer, default=1, nullable=False)
    # 1: Splash/Welcome, 2: Login/OTP, 3: Profile, 4: Device, 5: App PIN, 6: KYC, 7: Funding, 8: Activate, 9: Completed

    # Security
    pin_hash = Column(String(255), nullable=True)
    pin_failed_attempts = Column(Integer, default=0, nullable=False)
    pin_locked_until = Column(DateTime, nullable=True)
    biometric_enabled = Column(Boolean, default=False, nullable=False)
    biometric_credential_id = Column(String(255), nullable=True)
    biometric_public_key = Column(Text, nullable=True)

    # Wallet & Financials (Decimals)
    wallet_balance_inr = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    travel_countries = Column(JSON, default=list, nullable=False)  # e.g. ["TH", "ID", "SG"]
    travel_purpose = Column(String(50), nullable=True)  # TOURISM, BUSINESS, EDUCATION, MEDICAL
    lrs_annual_spent_usd = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    custom_daily_limit_inr = Column(Numeric(12, 2), default=Decimal("50000.00"), nullable=False)
    custom_txn_limit_inr = Column(Numeric(12, 2), default=Decimal("25000.00"), nullable=False)

    # Declarations
    fema_declaration_accepted = Column(Boolean, default=False, nullable=False)
    terms_accepted = Column(Boolean, default=False, nullable=False)
    language = Column(String(10), default="en", nullable=False)  # en, hi, ta

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    kyc_record = relationship("KYCRecord", back_populates="user", uselist=False, cascade="all, delete-orphan")
    quotes = relationship("PaymentQuote", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("InAppNotification", back_populates="user", cascade="all, delete-orphan")

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String(100), index=True, nullable=False)
    device_name = Column(String(150), default="Mobile Device", nullable=False)
    user_agent = Column(Text, nullable=False)
    ip_address = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_active_at = Column(DateTime, default=utcnow, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="devices")

class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(100), index=True, nullable=False)  # phone or email
    otp_code = Column(String(10), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_sent_at = Column(DateTime, default=utcnow, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    purpose = Column(String(50), default="LOGIN", nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

class KYCRecord(Base):
    __tablename__ = "kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    pan_number_encrypted = Column(Text, nullable=False)
    pan_number_masked = Column(String(20), nullable=False)
    full_name_on_pan = Column(String(150), nullable=False)
    address = Column(Text, nullable=False)
    passport_number = Column(String(50), nullable=True)
    selfie_file_path = Column(String(255), nullable=True)
    document_file_path = Column(String(255), nullable=True)
    status = Column(String(30), default="NOT_STARTED", nullable=False)  # NOT_STARTED, SUBMITTED, VERIFIED, REJECTED
    rejection_reason = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="kyc_record")

class PaymentQuote(Base):
    __tablename__ = "payment_quotes"

    id = Column(String(40), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    merchant_name = Column(String(150), nullable=False)
    merchant_city = Column(String(100), nullable=True)
    merchant_country = Column(String(10), nullable=True)
    foreign_currency = Column(String(10), nullable=False)
    foreign_amount = Column(Numeric(12, 4), nullable=False)
    exchange_rate = Column(Numeric(14, 6), nullable=False)  # rate from INR to foreign currency
    inr_base_amount = Column(Numeric(12, 2), nullable=False)
    markup_percent = Column(Numeric(5, 2), nullable=False)
    markup_inr = Column(Numeric(12, 2), nullable=False)
    gst_percent = Column(Numeric(5, 2), nullable=False)
    gst_inr = Column(Numeric(12, 2), nullable=False)
    total_inr = Column(Numeric(12, 2), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="quotes")
    transaction = relationship("Transaction", back_populates="quote", uselist=False)

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(40), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    quote_id = Column(String(40), ForeignKey("payment_quotes.id"), nullable=True)
    txn_type = Column(String(30), nullable=False)  # WALLET_TOPUP, MERCHANT_PAYMENT, REFUND
    status = Column(String(30), default="QUOTED", nullable=False)
    # QUOTED -> PAYMENT_PENDING -> PAID -> SETTLING -> SETTLED, or FAILED, REFUNDED, UNDER_REVIEW

    merchant_name = Column(String(150), nullable=True)
    merchant_city = Column(String(100), nullable=True)
    merchant_country = Column(String(10), nullable=True)
    foreign_currency = Column(String(10), nullable=True)
    foreign_amount = Column(Numeric(12, 4), nullable=True)

    inr_amount = Column(Numeric(12, 2), nullable=False)
    wallet_deduction_inr = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    # Razorpay Gateway
    gateway_order_id = Column(String(100), nullable=True)
    gateway_payment_id = Column(String(100), nullable=True)

    # Settlement Provider
    settlement_id = Column(String(100), nullable=True)
    settlement_provider = Column(String(50), nullable=True)
    settlement_status = Column(String(50), nullable=True)

    failure_reason = Column(Text, nullable=True)
    refund_reason = Column(Text, nullable=True)
    idempotency_key = Column(String(100), unique=True, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")
    quote = relationship("PaymentQuote", back_populates="transaction")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

class InAppNotification(Base):
    __tablename__ = "in_app_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    category = Column(String(50), default="INFO", nullable=False)  # OTP, ACTIVATION, PAYMENT, KYC, SECURITY
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="notifications")

class ExchangeRateCache(Base):
    __tablename__ = "exchange_rate_caches"

    id = Column(Integer, primary_key=True, index=True)
    base_currency = Column(String(10), default="INR", nullable=False)
    rates_json = Column(Text, nullable=False)
    fetched_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    provider = Column(String(50), default="open.er-api.com", nullable=False)

