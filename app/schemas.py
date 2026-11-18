from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, EmailStr, Field, field_validator
import re

class PhoneLoginRequest(BaseModel):
    mobile: str = Field(..., description="Mobile number with country code, e.g. +919876543210")

    @field_validator("mobile")
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not re.match(r"^\+[1-9]\d{7,14}$", clean):
            raise ValueError("Invalid phone number. Must include '+' and country code (e.g. +919876543210)")
        return clean

class VerifyOtpRequest(BaseModel):
    identifier: str
    otp: str = Field(..., min_length=6, max_length=6)
    device_id: str
    device_name: Optional[str] = "Web / Mobile PWA"
    user_agent: Optional[str] = "Unknown Agent"

class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_id: str
    device_name: Optional[str] = "Web / Mobile PWA"
    user_agent: Optional[str] = "Unknown Agent"

class ProfileSetupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    dob: str = Field(..., description="YYYY-MM-DD")

    @field_validator("dob")
    def validate_age(cls, v: str) -> str:
        try:
            born = datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("DOB must be in YYYY-MM-DD format")
        today = datetime.now().date()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if age < 18:
            raise ValueError("You must be at least 18 years old to use TravelPay")
        return v

class SetPinRequest(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6)

    @field_validator("pin")
    def validate_pin(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("PIN must be exactly 6 digits")
        return v

class VerifyPinRequest(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6)

class BiometricRegisterRequest(BaseModel):
    credential_id: str
    public_key: str

class KYCSubmitRequest(BaseModel):
    pan_number: str = Field(..., description="Indian PAN number, e.g. ABCDE1234F")
    full_name_on_pan: str = Field(..., min_length=2, max_length=150)
    address: str = Field(..., min_length=5)
    passport_number: Optional[str] = None

    @field_validator("pan_number")
    def validate_pan(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", cleaned):
            raise ValueError("Invalid PAN format. Must be 5 uppercase letters, 4 digits, 1 uppercase letter (e.g. ABCDE1234F)")
        return cleaned

class ActivateInternationalRequest(BaseModel):
    countries: List[str] = Field(..., min_length=1, description="List of 2-letter country/currency codes")
    travel_purpose: str = Field("TOURISM", description="TOURISM, BUSINESS, EDUCATION, MEDICAL")
    custom_daily_limit_inr: Decimal = Field(Decimal("50000.00"), ge=1000, le=500000)
    custom_txn_limit_inr: Decimal = Field(Decimal("25000.00"), ge=500, le=200000)
    terms_accepted: bool = Field(..., description="Must accept Terms and Conditions")
    fema_declaration_accepted: bool = Field(..., description="Must accept FEMA / LRS Declaration")

    @field_validator("terms_accepted", "fema_declaration_accepted")
    def must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the terms and FEMA declarations to activate")
        return v

class UserOut(BaseModel):
    id: int
    mobile: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    dob: Optional[str] = None
    role: str
    account_status: str
    activation_step: int
    kyc_status: str
    wallet_balance_inr: Decimal
    travel_countries: List[str]
    travel_purpose: Optional[str] = None
    biometric_enabled: bool
    language: str
    custom_daily_limit_inr: Decimal
    custom_txn_limit_inr: Decimal
    lrs_annual_spent_usd: Decimal

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut

class DeviceOut(BaseModel):
    id: int
    device_id: str
    device_name: str
    user_agent: str
    ip_address: Optional[str] = None
    is_active: bool
    last_active_at: datetime
    is_current: bool = False

class KYCOut(BaseModel):
    id: int
    status: str
    full_name_on_pan: str
    pan_masked: str
    address: str
    passport_number: Optional[str] = None
    selfie_file_path: Optional[str] = None
    document_file_path: Optional[str] = None
    rejection_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None

class ChecklistStep(BaseModel):
    step_number: int
    key: str
    title: str
    description: str
    completed: bool
    is_current: bool

class ActivationStatusResponse(BaseModel):
    account_status: str
    kyc_status: str
    current_step: int
    total_steps: int = 8
    is_active: bool
    checklist: List[ChecklistStep]

class WalletTopupRequest(BaseModel):
    amount_inr: Decimal = Field(..., ge=10, le=200000)

class WalletTopupOrderResponse(BaseModel):
    order_id: str
    amount_inr: Decimal
    amount_subunits: int
    currency: str = "INR"
    razorpay_key_id: str

class WalletBalanceResponse(BaseModel):
    balance_inr: Decimal
    currency: str = "INR"

class ParseQRRequest(BaseModel):
    qr_data: str

class ParsedQRResponse(BaseModel):
    raw: str
    format: str  # EMVCo, JSON, TEXT
    merchant_name: str
    merchant_city: Optional[str] = None
    merchant_country: Optional[str] = None
    currency: str
    currency_numeric: Optional[str] = None
    amount: Optional[Decimal] = None
    tip_amount: Optional[Decimal] = None
    reference_id: Optional[str] = None
    valid_crc: bool

class CreateQuoteRequest(BaseModel):
    merchant_name: str
    merchant_city: Optional[str] = None
    merchant_country: Optional[str] = None
    currency: str
    amount: Decimal = Field(..., gt=0)

class QuoteResponse(BaseModel):
    quote_id: str
    merchant_name: str
    merchant_city: Optional[str] = None
    merchant_country: Optional[str] = None
    foreign_currency: str
    foreign_amount: Decimal
    exchange_rate: Decimal
    inr_base_amount: Decimal
    markup_percent: Decimal
    markup_inr: Decimal
    gst_percent: Decimal
    gst_inr: Decimal
    total_inr: Decimal
    expires_at: datetime
    remaining_seconds: int

class ConfirmPaymentRequest(BaseModel):
    quote_id: str
    pin: Optional[str] = None
    use_biometric: bool = False
    payment_method: str = "WALLET"  # WALLET, RAZORPAY_SHORTFALL
    shortfall_payment_id: Optional[str] = None  # if topped up via Razorpay
    idempotency_key: Optional[str] = None

class TransactionOut(BaseModel):
    id: str
    txn_type: str
    status: str
    merchant_name: Optional[str] = None
    merchant_city: Optional[str] = None
    merchant_country: Optional[str] = None
    foreign_currency: Optional[str] = None
    foreign_amount: Optional[Decimal] = None
    inr_amount: Decimal
    wallet_deduction_inr: Decimal
    settlement_id: Optional[str] = None
    settlement_provider: Optional[str] = None
    settlement_status: Optional[str] = None
    failure_reason: Optional[str] = None
    refund_reason: Optional[str] = None
    created_at: datetime

class ConvertRequest(BaseModel):
    from_currency: str
    to_currency: str
    amount: Decimal

class ConvertResponse(BaseModel):
    from_currency: str
    to_currency: str
    amount: Decimal
    rate: Decimal
    converted_amount: Decimal
    markup_inr: Optional[Decimal] = None
    gst_inr: Optional[Decimal] = None
    total_inr: Optional[Decimal] = None

