import pytest
from decimal import Decimal
from app.services.rates import get_currency_decimals, format_currency_amount, RatesService
from app.config import settings

def test_minor_units_decimals():
    # JPY: 0 decimals
    assert get_currency_decimals("JPY") == 0
    # KWD: 3 decimals
    assert get_currency_decimals("KWD") == 3
    # BHD: 3 decimals
    assert get_currency_decimals("BHD") == 3
    # USD, EUR, SGD, THB: 2 decimals
    assert get_currency_decimals("USD") == 2
    assert get_currency_decimals("EUR") == 2
    assert get_currency_decimals("SGD") == 2
    assert get_currency_decimals("THB") == 2

    # Formatting checks
    jpy_amt = format_currency_amount(Decimal("1250.75"), "JPY")
    assert jpy_amt == Decimal("1251")

    kwd_amt = format_currency_amount(Decimal("12.3456"), "KWD")
    assert kwd_amt == Decimal("12.346")

    usd_amt = format_currency_amount(Decimal("10.555"), "USD")
    assert usd_amt == Decimal("10.56")

def test_fee_and_gst_calculation(db):
    # Test formula with deterministic test numbers
    # Say foreign amount = 100 USD, rate = 0.0116 (approx 1 USD = 86.2069 INR)
    rate, inr_base, markup, gst, total = RatesService.calculate_inr_for_foreign(
        db, foreign_currency="USD", foreign_amount=Decimal("100.00")
    )
    assert isinstance(rate, Decimal)
    assert isinstance(inr_base, Decimal)
    assert isinstance(markup, Decimal)
    assert isinstance(gst, Decimal)
    assert isinstance(total, Decimal)

    # Base formula assertions
    # markup = inr_base * 2%
    expected_markup = (inr_base * settings.MARKUP_PERCENT / Decimal("100")).quantize(Decimal("0.01"))
    assert markup == expected_markup

    # gst = markup * 18%
    expected_gst = (markup * settings.GST_PERCENT / Decimal("100")).quantize(Decimal("0.01"))
    assert gst == expected_gst

    # total = inr_base + markup + gst
    expected_total = (inr_base + markup + gst).quantize(Decimal("0.01"))
    assert total == expected_total

    # Verify no float drift: difference is exactly zero
    assert (total - inr_base - markup - gst) == Decimal("0.00")

