import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import User, KYCRecord, Device, utcnow
from app.deps import create_access_token
from app.services.kyc import encrypt_pan, mask_pan
from app.services.rates import RatesService, FALLBACK_INR_RATES

# In-memory SQLite with StaticPool so all threads/sessions share the same DB
engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def mock_rates_fetch(monkeypatch):
    monkeypatch.setattr(RatesService, "fetch_live_rates", lambda: {k: Decimal(v) for k, v in FALLBACK_INR_RATES.items()})

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)

@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def active_user(db):
    user = User(
        mobile="+919876543299",
        email="active.test@travelpay.internal",
        full_name="Active Test User",
        dob="1990-01-01",
        role="USER",
        account_status="ACTIVE",
        activation_step=9,
        pin_hash=bcrypt.hashpw("123456".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        biometric_enabled=True,
        wallet_balance_inr=Decimal("50000.00"),
        travel_countries=["TH", "ID", "SG"],
        custom_daily_limit_inr=Decimal("100000.00"),
        custom_txn_limit_inr=Decimal("50000.00"),
        terms_accepted=True,
        fema_declaration_accepted=True,
        created_at=utcnow(),
        updated_at=utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add verified KYC
    kyc = KYCRecord(
        user_id=user.id,
        pan_number_encrypted=encrypt_pan("ABCDE1234F"),
        pan_number_masked=mask_pan("ABCDE1234F"),
        full_name_on_pan="Active Test User",
        address="Test Address, Bengaluru",
        status="VERIFIED",
        verified_at=utcnow(),
        verified_by="SandboxKycProvider"
    )
    db.add(kyc)
    db.commit()
    db.refresh(user)
    return user

@pytest.fixture
def active_user_token(active_user):
    return create_access_token(active_user.id, active_user.role)

@pytest.fixture
def admin_user(db):
    admin = User(
        email="admin.test@travelpay.internal",
        role="ADMIN",
        account_status="ACTIVE",
        activation_step=9,
        password_hash=bcrypt.hashpw("Admin@123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        created_at=utcnow(),
        updated_at=utcnow()
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin

@pytest.fixture
def admin_token(admin_user):
    return create_access_token(admin_user.id, admin_user.role)
