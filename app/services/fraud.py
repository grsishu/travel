import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Transaction, Device, AuditLog, User, utcnow

logger = logging.getLogger("travelpay.fraud")

class FraudDetectionService:
    @staticmethod
    def assess_risk(
        db: Session,
        user: User,
        device_id: str,
        amount_inr: Decimal
    ) -> Tuple[bool, List[str]]:
        """
        Assesses transaction risk.
        Returns: (needs_review: bool, risk_flags: List[str])
        """
        flags: List[str] = []
        now = utcnow()

        # 1. Velocity check: More than 5 transactions in last 10 minutes
        ten_mins_ago = now - timedelta(minutes=10)
        recent_txns = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.created_at >= ten_mins_ago
            )
            .count()
        )
        if recent_txns >= 5:
            flags.append(f"High velocity: {recent_txns} transactions initiated in 10 minutes.")

        # 2. New device check: Device registered within last 1 hour
        device = (
            db.query(Device)
            .filter(Device.user_id == user.id, Device.device_id == device_id)
            .first()
        )
        if device:
            dev_age_hours = (now - device.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600.0
            if dev_age_hours < 1.0:
                flags.append(f"Recent device registration: active for only {int(dev_age_hours*60)} minutes.")

        # 3. Amount Anomaly: Check if current amount is > 5x average historical transaction
        avg_amount = (
            db.query(func.avg(Transaction.inr_amount))
            .filter(
                Transaction.user_id == user.id,
                Transaction.status == "SETTLED"
            )
            .scalar()
        )
        if avg_amount and amount_inr > (Decimal(str(avg_amount)) * Decimal("5.0")) and amount_inr > Decimal("20000.00"):
            flags.append(f"Amount anomaly: ₹{amount_inr:.2f} is significantly higher than historical average ₹{avg_amount:.2f}.")

        needs_review = len(flags) > 1 or (len(flags) == 1 and "High velocity" in flags[0])
        if flags:
            logger.warning(f"[FRAUD ASSESSMENT] User={user.id} Flags={flags} NeedsReview={needs_review}")
            db.add(AuditLog(
                user_id=user.id,
                action="FRAUD_RISK_FLAGGED",
                details=f"Flags: {'; '.join(flags)} | NeedsReview: {needs_review}"
            ))
            db.commit()

        return needs_review, flags

