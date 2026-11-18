import hmac
import hashlib
import json
import pytest
from decimal import Decimal
from app.config import settings
from app.models import Transaction, User

def test_razorpay_webhook_signature_and_idempotency(client, db, active_user):
    initial_balance = active_user.wallet_balance_inr
    payment_id = "pay_test_webhook_unique_99"

    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 500000,  # 5,000.00 INR (500000 subunits)
                    "currency": "INR",
                    "status": "captured",
                    "order_id": "order_test_99",
                    "notes": {"user_id": str(active_user.id)}
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode("utf-8")
    secret = settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8")
    valid_sig = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": valid_sig
    }

    # 1. First webhook delivery
    res1 = client.post("/api/webhooks/razorpay", content=raw_body, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"

    db.refresh(active_user)
    assert active_user.wallet_balance_inr == initial_balance + Decimal("5000.00")

    # 2. Second (duplicate / retry) webhook delivery - Idempotency test
    res2 = client.post("/api/webhooks/razorpay", content=raw_body, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["message"] == "Already processed"

    # Wallet balance must NOT increase again!
    db.refresh(active_user)
    assert active_user.wallet_balance_inr == initial_balance + Decimal("5000.00")

