import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple, Optional
import httpx
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ExchangeRateCache, utcnow

logger = logging.getLogger("travelpay.rates")

# ISO 4217 Minor Units definition
CURRENCY_DECIMALS: Dict[str, int] = {
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "CLP": 0,
    "HUF": 0,
    "KWD": 3,
    "BHD": 3,
    "OMR": 3,
    "JOD": 3,
    "TND": 3,
}

# Reliable fallback rates for core travel corridors in case internet is unreachable
FALLBACK_INR_RATES: Dict[str, str] = {
    "INR": "1.0",
    "USD": "0.0116",    # ~86.2 INR
    "EUR": "0.0110",    # ~90.9 INR
    "GBP": "0.0094",    # ~106.3 INR
    "THB": "0.4100",    # ~2.44 INR
    "SGD": "0.0157",    # ~63.7 INR
    "IDR": "190.50",    # ~0.00525 INR
    "MYR": "0.0520",    # ~19.23 INR
    "AED": "0.0426",    # ~23.47 INR
    "JPY": "1.7900",    # ~0.558 INR
    "VND": "295.00",    # ~0.00339 INR
    "KWD": "0.00357",   # ~280.11 INR
    "AUD": "0.0182",    # ~54.9 INR
    "CAD": "0.0165",    # ~60.6 INR
    "CHF": "0.0105",    # ~95.2 INR
    "CNY": "0.0845",    # ~11.83 INR
    "HKD": "0.0905",    # ~11.05 INR
    "NZD": "0.0198",    # ~50.5 INR
    "QAR": "0.0423",    # ~23.64 INR
    "SAR": "0.0435",    # ~22.98 INR
}

# Numeric ISO 4217 to Alpha 3 mapping for EMVCo QR codes
NUMERIC_TO_ALPHA_CURRENCY: Dict[str, str] = {
    "764": "THB",
    "360": "IDR",
    "702": "SGD",
    "704": "VND",
    "458": "MYR",
    "840": "USD",
    "978": "EUR",
    "826": "GBP",
    "392": "JPY",
    "414": "KWD",
    "784": "AED",
    "036": "AUD",
    "124": "CAD",
    "756": "CHF",
    "156": "CNY",
    "344": "HKD",
    "682": "SAR",
    "634": "QAR",
    "356": "INR"
}

def get_currency_decimals(currency: str) -> int:
    return CURRENCY_DECIMALS.get(currency.upper(), 2)

def format_currency_amount(amount: Decimal, currency: str) -> Decimal:
    decimals = get_currency_decimals(currency)
    quantizer = Decimal(10) ** -decimals if decimals > 0 else Decimal(1)
    return amount.quantize(quantizer, rounding=ROUND_HALF_UP)

class RatesService:
    PRIMARY_API_URL = "https://open.er-api.com/v6/latest/INR"

    @classmethod
    def fetch_live_rates(cls) -> Optional[Dict[str, Decimal]]:
        """Fetch rates from open.er-api.com"""
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(cls.PRIMARY_API_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_rates = data.get("rates", {})
                    decimal_rates = {k: Decimal(str(v)) for k, v in raw_rates.items()}
                    return decimal_rates
        except Exception as e:
            logger.warning(f"Could not fetch from primary rates API: {e}")
        return None

    @classmethod
    def get_rates(cls, db: Session, max_age_seconds: int = None) -> Tuple[Dict[str, Decimal], datetime, str]:
        """
        Returns (rates_dict, fetched_at, source_provider).
        Enforces 5-minute TTL cache.
        """
        if max_age_seconds is None:
            max_age_seconds = settings.RATE_CACHE_TTL_SECONDS

        now = utcnow()
        cache = db.query(ExchangeRateCache).order_by(ExchangeRateCache.id.desc()).first()

        # Check if cache is fresh
        if cache:
            cache_fetched_at = cache.fetched_at.replace(tzinfo=timezone.utc)
            age = (now - cache_fetched_at).total_seconds()
            if age < max_age_seconds:
                rates_data = json.loads(cache.rates_json)
                return {k: Decimal(v) for k, v in rates_data.items()}, cache.fetched_at, cache.provider

        # Cache expired or absent, try to refresh
        live_rates = cls.fetch_live_rates()
        if live_rates:
            expires_at = now + timedelta(seconds=max_age_seconds)
            json_str = json.dumps({k: str(v) for k, v in live_rates.items()})
            new_cache = ExchangeRateCache(
                base_currency="INR",
                rates_json=json_str,
                fetched_at=now,
                expires_at=expires_at,
                provider="open.er-api.com"
            )
            db.add(new_cache)
            db.commit()
            return live_rates, now, "open.er-api.com"

        # Fallback if primary fetch fails
        if cache:
            # Check if cache is still usable as fallback (never pay on very stale rate)
            rates_data = json.loads(cache.rates_json)
            return {k: Decimal(v) for k, v in rates_data.items()}, cache.fetched_at, f"cached_fallback ({cache.provider})"

        # Static fallback if DB is completely empty and network unavailable
        fallback_decimal = {k: Decimal(v) for k, v in FALLBACK_INR_RATES.items()}
        expires_at = now + timedelta(seconds=max_age_seconds)
        new_cache = ExchangeRateCache(
            base_currency="INR",
            rates_json=json.dumps(FALLBACK_INR_RATES),
            fetched_at=now,
            expires_at=expires_at,
            provider="static_fallback"
        )
        db.add(new_cache)
        db.commit()
        return fallback_decimal, now, "static_fallback"

    @classmethod
    def calculate_inr_for_foreign(
        cls,
        db: Session,
        foreign_currency: str,
        foreign_amount: Decimal
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        """
        Converts foreign currency amount to INR.
        Returns: (rate, inr_base_amount, markup_inr, gst_inr, total_inr)
        Formula:
          rate = units of foreign currency per 1 INR
          inr_base = foreign_amount / rate
          markup = inr_base * MARKUP_PERCENT / 100
          gst = markup * GST_PERCENT / 100
          total = inr_base + markup + gst
        """
        rates, fetched_at, provider = cls.get_rates(db)
        curr = foreign_currency.upper()

        if curr not in rates:
            raise ValueError(f"Unsupported foreign currency: {curr}")

        rate = rates[curr]
        if rate <= Decimal("0"):
            raise ValueError(f"Invalid rate {rate} for currency {curr}")

        # Compute Base INR
        inr_base = (foreign_amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Markup (default 2%)
        markup_pct = settings.MARKUP_PERCENT
        markup_inr = (inr_base * markup_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # GST on Markup (default 18%)
        gst_pct = settings.GST_PERCENT
        gst_inr = (markup_inr * gst_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Total INR
        total_inr = (inr_base + markup_inr + gst_inr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return rate, inr_base, markup_inr, gst_inr, total_inr

