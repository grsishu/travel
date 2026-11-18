from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.config import settings
from app.models import PaymentQuote, User, utcnow
from app.services.rates import RatesService, format_currency_amount

class QuoteService:
    @staticmethod
    def create_quote(
        db: Session,
        user: User,
        merchant_name: str,
        currency: str,
        foreign_amount: Decimal,
        merchant_city: str = None,
        merchant_country: str = None
    ) -> PaymentQuote:
        """
        Creates a locked quote valid for 120 seconds.
        """
        curr = currency.upper()
        decimals_adjusted_amount = format_currency_amount(foreign_amount, curr)

        rate, inr_base, markup_inr, gst_inr, total_inr = RatesService.calculate_inr_for_foreign(
            db, curr, decimals_adjusted_amount
        )

        now = utcnow()
        expires_at = now + timedelta(seconds=settings.QUOTE_TTL_SECONDS)

        quote = PaymentQuote(
            user_id=user.id,
            merchant_name=merchant_name,
            merchant_city=merchant_city,
            merchant_country=merchant_country,
            foreign_currency=curr,
            foreign_amount=decimals_adjusted_amount,
            exchange_rate=rate,
            inr_base_amount=inr_base,
            markup_percent=settings.MARKUP_PERCENT,
            markup_inr=markup_inr,
            gst_percent=settings.GST_PERCENT,
            gst_inr=gst_inr,
            total_inr=total_inr,
            expires_at=expires_at,
            is_used=False,
            created_at=now
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)
        return quote

    @staticmethod
    def get_valid_quote(db: Session, quote_id: str, user_id: int) -> PaymentQuote:
        quote = (
            db.query(PaymentQuote)
            .filter(PaymentQuote.id == quote_id, PaymentQuote.user_id == user_id)
            .first()
        )
        if not quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment quote not found."
            )

        if quote.is_used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This quote has already been used for a transaction."
            )

        now = utcnow()
        exp = quote.expires_at.replace(tzinfo=timezone.utc)
        if now > exp:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Payment quote has expired (120-second validity window passed). Please scan again to get a fresh rate."
            )

        return quote

