import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from fastapi import HTTPException
from app.services.quotes import QuoteService
from app.models import PaymentQuote, utcnow

def test_quote_creation_and_120s_validity(db, active_user):
    quote = QuoteService.create_quote(
        db=db,
        user=active_user,
        merchant_name="Bangkok Street Food",
        currency="THB",
        foreign_amount=Decimal("200.00"),
        merchant_city="Bangkok",
        merchant_country="TH"
    )

    assert quote.id is not None
    assert quote.is_used is False
    now = utcnow()
    exp = quote.expires_at.replace(tzinfo=timezone.utc)
    # Check that quote expires in approximately 120 seconds
    diff_sec = (exp - now).total_seconds()
    assert 115 <= diff_sec <= 125

    # Valid quote retrieval within TTL
    valid = QuoteService.get_valid_quote(db, quote.id, active_user.id)
    assert valid.id == quote.id

def test_quote_expired_rejected(db, active_user):
    quote = QuoteService.create_quote(
        db=db,
        user=active_user,
        merchant_name="Bangkok Street Food",
        currency="THB",
        foreign_amount=Decimal("150.00")
    )

    # Force expiration (backdate expires_at)
    quote.expires_at = utcnow() - timedelta(seconds=10)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        QuoteService.get_valid_quote(db, quote.id, active_user.id)
    assert exc_info.value.status_code == 410
    assert "expired" in exc_info.value.detail.lower()

def test_quote_reused_rejected(db, active_user):
    quote = QuoteService.create_quote(
        db=db,
        user=active_user,
        merchant_name="Bangkok Street Food",
        currency="THB",
        foreign_amount=Decimal("150.00")
    )
    quote.is_used = True
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        QuoteService.get_valid_quote(db, quote.id, active_user.id)
    assert exc_info.value.status_code == 400
    assert "already been used" in exc_info.value.detail.lower()

