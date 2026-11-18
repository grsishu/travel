import os
from decimal import Decimal
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from cryptography.fernet import Fernet

# Generate default Fernet key for local dev if not present
_DEFAULT_FERNET_KEY = Fernet.generate_key().decode()

class Settings(BaseSettings):
    APP_NAME: str = "TravelPay"
    APP_ENV: str = "development"
    TEST_MODE: bool = True
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./travelpay.db"

    # Security & Tokens
    SECRET_KEY: str = "travelpay-ultra-secure-jwt-secret-key-32chars-min!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PAN_ENCRYPTION_KEY: str = _DEFAULT_FERNET_KEY

    # Payment Gateway (Razorpay Test Keys)
    RAZORPAY_KEY_ID: str = "rzp_test_TravelPayKey01"
    RAZORPAY_KEY_SECRET: str = "rzp_test_TravelPaySecret01"
    RAZORPAY_WEBHOOK_SECRET: str = "rzp_webhook_secret_travelpay_test"

    # Fees & Compliance
    MARKUP_PERCENT: Decimal = Decimal("2.0")  # 2% standard markup
    GST_PERCENT: Decimal = Decimal("18.0")     # 18% GST on markup fee
    LRS_ANNUAL_LIMIT_USD: Decimal = Decimal("250000.00")
    DEFAULT_PER_TXN_LIMIT_INR: Decimal = Decimal("200000.00")
    DEFAULT_DAILY_LIMIT_INR: Decimal = Decimal("500000.00")

    # Timeouts & Locks
    QUOTE_TTL_SECONDS: int = 120
    RATE_CACHE_TTL_SECONDS: int = 300
    MAX_PIN_ATTEMPTS: int = 3
    PIN_LOCKOUT_MINUTES: int = 30
    APP_INACTIVITY_LOCK_SECONDS: int = 60
    OTP_EXPIRY_SECONDS: int = 300
    OTP_RESEND_COOLDOWN_SECONDS: int = 30
    OTP_MAX_ATTEMPTS: int = 3

    # Providers
    OTP_PROVIDER: str = "console"  # "console", "twilio", "msg91"
    SETTLEMENT_PROVIDER: str = "sandbox"  # "sandbox", "wise", "airwallex"
    KYC_PROVIDER: str = "sandbox"  # "sandbox", "hyperverge", "idfy"

    # File uploads
    UPLOAD_DIR: str = os.path.join(os.path.dirname(__file__), "uploads")

    # Wise / Airwallex skeletons
    WISE_API_KEY: Optional[str] = None
    WISE_PROFILE_ID: Optional[str] = None
    AIRWALLEX_API_KEY: Optional[str] = None
    AIRWALLEX_CLIENT_ID: Optional[str] = None

    # Twilio / MSG91 skeletons
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None
    MSG91_AUTH_KEY: Optional[str] = None
    MSG91_SENDER_ID: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
