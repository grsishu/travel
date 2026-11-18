from decimal import Decimal
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.schemas import ConvertRequest, ConvertResponse
from app.services.rates import RatesService, get_currency_decimals, format_currency_amount

router = APIRouter(prefix="/api/rates", tags=["Exchange Rates"])

# Currencies metadata mapping
CURRENCY_NAMES = {
    "USD": ("US Dollar", "🇺🇸", "US"),
    "EUR": ("Euro", "🇪🇺", "EU"),
    "GBP": ("British Pound", "🇬🇧", "GB"),
    "THB": ("Thai Baht", "🇹🇭", "TH"),
    "SGD": ("Singapore Dollar", "🇸🇬", "SG"),
    "IDR": ("Indonesian Rupiah", "🇮🇩", "ID"),
    "MYR": ("Malaysian Ringgit", "🇲🇾", "MY"),
    "AED": ("UAE Dirham", "🇦🇪", "AE"),
    "JPY": ("Japanese Yen", "🇯🇵", "JP"),
    "VND": ("Vietnamese Dong", "🇻🇳", "VN"),
    "KWD": ("Kuwaiti Dinar", "🇰🇼", "KW"),
    "AUD": ("Australian Dollar", "🇦🇺", "AU"),
    "CAD": ("Canadian Dollar", "🇨🇦", "CA"),
    "CHF": ("Swiss Franc", "🇨🇭", "CH"),
    "CNY": ("Chinese Yuan", "🇨🇳", "CN"),
    "HKD": ("Hong Kong Dollar", "🇭🇰", "HK"),
    "NZD": ("New Zealand Dollar", "🇳🇿", "NZ"),
    "QAR": ("Qatari Riyal", "🇶🇦", "QA"),
    "SAR": ("Saudi Riyal", "🇸🇦", "SA"),
    "INR": ("Indian Rupee", "🇮🇳", "IN")
}

@router.get("/latest")
def get_latest_rates(db: Session = Depends(get_db)):
    rates, fetched_at, provider = RatesService.get_rates(db)
    return {
        "base": "INR",
        "provider": provider,
        "fetched_at": fetched_at.isoformat(),
        "total_currencies": len(rates),
        "rates": {k: float(v) for k, v in rates.items()}
    }

@router.get("/currencies")
def get_currencies(db: Session = Depends(get_db)):
    rates, _, _ = RatesService.get_rates(db)
    result = []
    for code, rate in rates.items():
        name, flag, country = CURRENCY_NAMES.get(code, (f"{code} Currency", "🌐", "GLOBAL"))
        inr_per_unit = (Decimal("1.0") / rate) if rate > 0 else Decimal("0")
        result.append({
            "code": code,
            "name": name,
            "flag": flag,
            "country_code": country,
            "decimals": get_currency_decimals(code),
            "rate_against_inr": float(rate),
            "inr_per_foreign_unit": float(inr_per_unit.quantize(Decimal("0.0001")))
        })
    # Sort popular currencies first
    popular = ["THB", "SGD", "IDR", "USD", "EUR", "AED", "JPY", "GBP", "VND", "MYR", "KWD"]
    result.sort(key=lambda x: (0 if x["code"] in popular else 1, popular.index(x["code"]) if x["code"] in popular else x["code"]))
    return result

@router.post("/convert", response_model=ConvertResponse)
def convert_currency(payload: ConvertRequest, db: Session = Depends(get_db)):
    from_curr = payload.from_currency.upper()
    to_curr = payload.to_currency.upper()
    rates, _, _ = RatesService.get_rates(db)

    if from_curr not in rates or to_curr not in rates:
        raise ValueError(f"One or both currencies not supported: {from_curr}, {to_curr}")

    if from_curr == "INR":
        # Convert INR to Foreign
        target_rate = rates[to_curr]
        converted = (payload.amount * target_rate)
        converted = format_currency_amount(converted, to_curr)
        return ConvertResponse(
            from_currency=from_curr,
            to_currency=to_curr,
            amount=payload.amount,
            rate=target_rate,
            converted_amount=converted
        )
    else:
        # Convert Foreign to INR with fees
        rate, inr_base, markup, gst, total = RatesService.calculate_inr_for_foreign(
            db, from_curr, payload.amount
        )
        return ConvertResponse(
            from_currency=from_curr,
            to_currency="INR",
            amount=payload.amount,
            rate=rate,
            converted_amount=inr_base,
            markup_inr=markup,
            gst_inr=gst,
            total_inr=total
        )

