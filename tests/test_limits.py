import pytest
from decimal import Decimal
from fastapi import HTTPException
from app.services.activation import ActivationService
from app.config import settings
from app.models import Transaction, utcnow

def test_per_transaction_limit(db, active_user):
    active_user.custom_txn_limit_inr = Decimal("5000.00")
    db.commit()

    # Allowed: 4,000 INR
    assert ActivationService.check_can_pay(db, active_user, inr_amount=Decimal("4000.00")) is True

    # Blocked: 6,000 INR
    with pytest.raises(HTTPException) as exc_info:
        ActivationService.check_can_pay(db, active_user, inr_amount=Decimal("6000.00"))
    assert exc_info.value.status_code == 400
    assert "per-transaction limit" in exc_info.value.detail.lower()

def test_daily_spending_limit(db, active_user):
    active_user.custom_txn_limit_inr = Decimal("50000.00")
    active_user.custom_daily_limit_inr = Decimal("10000.00")
    db.commit()

    # Add transaction of 8,000 INR already spent today
    txn = Transaction(
        id="LIMIT-TEST-01",
        user_id=active_user.id,
        txn_type="MERCHANT_PAYMENT",
        status="SETTLED",
        inr_amount=Decimal("8000.00"),
        created_at=utcnow()
    )
    db.add(txn)
    db.commit()

    # Attempting 3,000 INR would bring daily total to 11,000 > 10,000 limit -> Must fail!
    with pytest.raises(HTTPException) as exc_info:
        ActivationService.check_can_pay(db, active_user, inr_amount=Decimal("3000.00"))
    assert exc_info.value.status_code == 400
    assert "daily spending limit" in exc_info.value.detail.lower()

def test_lrs_annual_limit(db, active_user):
    # Set annual spent close to USD 250,000
    active_user.lrs_annual_spent_usd = Decimal("249900.00")
    db.commit()

    # Payment of 200 USD brings annual total to 250,100 > 250,000 -> Must fail!
    with pytest.raises(HTTPException) as exc_info:
        ActivationService.check_can_pay(
            db, active_user, inr_amount=Decimal("17000.00"), foreign_amount_usd=Decimal("200.00")
        )
    assert exc_info.value.status_code == 400
    assert "lrs limit" in exc_info.value.detail.lower()

