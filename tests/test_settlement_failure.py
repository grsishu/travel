import pytest
from decimal import Decimal
from app.services.quotes import QuoteService
from app.services.payments import PaymentService
from app.models import Transaction, User

def test_settlement_success(db, active_user):
    initial_balance = active_user.wallet_balance_inr
    quote = QuoteService.create_quote(
        db=db,
        user=active_user,
        merchant_name="Bangkok Night Market",
        currency="THB",
        foreign_amount=Decimal("100.00")
    )
    total_charged = quote.total_inr

    txn = PaymentService.execute_payment(
        db=db,
        user=active_user,
        quote=quote,
        pin="123456"
    )

    assert txn.status == "SETTLED"
    assert txn.settlement_status == "SETTLED"
    db.refresh(active_user)
    assert active_user.wallet_balance_inr == initial_balance - total_charged

def test_settlement_failure_auto_refund(db, active_user):
    initial_balance = active_user.wallet_balance_inr
    # Merchant name containing "FAIL" triggers simulated settlement failure in Sandbox
    quote = QuoteService.create_quote(
        db=db,
        user=active_user,
        merchant_name="Merchant FAIL Bank Error",
        currency="THB",
        foreign_amount=Decimal("150.00")
    )
    total_charged = quote.total_inr

    txn = PaymentService.execute_payment(
        db=db,
        user=active_user,
        quote=quote,
        pin="123456"
    )

    # Primary payment status is FAILED
    assert txn.status == "FAILED"
    assert "rejected" in txn.failure_reason.lower() or "failed" in txn.failure_reason.lower()

    # User's wallet balance MUST be automatically refunded back to initial balance
    db.refresh(active_user)
    assert active_user.wallet_balance_inr == initial_balance

    # Verify refund transaction record exists in DB
    refund_txns = db.query(Transaction).filter(
        Transaction.user_id == active_user.id,
        Transaction.txn_type == "REFUND"
    ).all()
    assert len(refund_txns) >= 1
    latest_refund = refund_txns[-1]
    assert latest_refund.status == "SETTLED"
    assert latest_refund.inr_amount == total_charged

