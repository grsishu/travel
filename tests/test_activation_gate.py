import pytest
from decimal import Decimal
import bcrypt
from app.models import User, KYCRecord, utcnow
from app.deps import create_access_token
from app.services.kyc import encrypt_pan, mask_pan

def test_activation_gate_enforcement_at_every_step(client, db):
    # Step 1: Inactive user (no profile, no PIN, no KYC)
    user = User(
        mobile="+919876543001",
        account_status="INACTIVE",
        activation_step=2,
        wallet_balance_inr=Decimal("1000.00")
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, "USER")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "merchant_name": "Test Cafe Bangkok",
        "currency": "THB",
        "amount": 100.0
    }

    # Rejection 1: Account INACTIVE / Profile missing
    r1 = client.post("/api/payments/quote", json=payload, headers=headers)
    assert r1.status_code == 403
    assert "ACTIVE" in r1.json()["detail"]

    # Step 2: Profile added, but PIN missing
    user.full_name = "Incomplete User"
    user.email = "inc@example.com"
    user.dob = "1992-04-10"
    user.activation_step = 4
    db.commit()

    r2 = client.post("/api/payments/quote", json=payload, headers=headers)
    assert r2.status_code == 403
    assert "ACTIVE" in r2.json()["detail"]

    # Step 3: PIN set, but KYC missing
    user.pin_hash = bcrypt.hashpw("654321".encode(), bcrypt.gensalt()).decode()
    user.activation_step = 6
    db.commit()

    r3 = client.post("/api/payments/quote", json=payload, headers=headers)
    assert r3.status_code == 403
    assert "ACTIVE" in r3.json()["detail"]

    # Step 4: KYC SUBMITTED (not VERIFIED)
    kyc = KYCRecord(
        user_id=user.id,
        pan_number_encrypted=encrypt_pan("ABCDE1234F"),
        pan_number_masked=mask_pan("ABCDE1234F"),
        full_name_on_pan="Incomplete User",
        address="Test Road",
        status="SUBMITTED"
    )
    db.add(kyc)
    db.commit()

    r4 = client.post("/api/payments/quote", json=payload, headers=headers)
    assert r4.status_code == 403

    # Step 5: KYC VERIFIED, but international not yet activated
    kyc.status = "VERIFIED"
    kyc.verified_at = utcnow()
    user.activation_step = 8
    db.commit()

    r5 = client.post("/api/payments/quote", json=payload, headers=headers)
    assert r5.status_code == 403
    assert "ACTIVE" in r5.json()["detail"]

    # Step 6: Fully Activated
    user.account_status = "ACTIVE"
    user.activation_step = 9
    user.travel_countries = ["TH"]
    user.terms_accepted = True
    user.fema_declaration_accepted = True
    db.commit()

    r6 = client.post("/api/payments/quote", json=payload, headers=headers)
    assert r6.status_code == 200
    data = r6.json()
    assert "quote_id" in data
    assert data["foreign_currency"] == "THB"
    assert float(data["total_inr"]) > 0
