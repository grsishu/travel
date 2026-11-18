import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from fastapi import HTTPException
from app.models import User, utcnow
from app.services.payments import PaymentService
from app.deps import create_access_token

def test_pin_verification_and_30min_lockout(client, active_user, active_user_token, db):
    headers = {"Authorization": f"Bearer {active_user_token}"}

    # Correct PIN verification
    r_ok = client.post("/api/auth/pin/verify", json={"pin": "123456"}, headers=headers)
    assert r_ok.status_code == 200

    # Wrong PIN attempt 1
    r_fail1 = client.post("/api/auth/pin/verify", json={"pin": "999999"}, headers=headers)
    assert r_fail1.status_code == 401
    assert "2 attempt(s) remaining" in r_fail1.json()["detail"]

    # Wrong PIN attempt 2
    r_fail2 = client.post("/api/auth/pin/verify", json={"pin": "999999"}, headers=headers)
    assert r_fail2.status_code == 401
    assert "1 attempt(s) remaining" in r_fail2.json()["detail"]

    # Wrong PIN attempt 3 (Trigger lockout)
    r_fail3 = client.post("/api/auth/pin/verify", json={"pin": "999999"}, headers=headers)
    assert r_fail3.status_code == 423
    assert "locked for 30 minutes" in r_fail3.json()["detail"].lower()

    # Even with correct PIN, user is locked out!
    r_locked = client.post("/api/auth/pin/verify", json={"pin": "123456"}, headers=headers)
    assert r_locked.status_code == 423
    assert "locked" in r_locked.json()["detail"].lower()

    # Check database state
    db.refresh(active_user)
    assert active_user.pin_locked_until is not None
    assert active_user.pin_locked_until.replace(tzinfo=timezone.utc) > utcnow()
