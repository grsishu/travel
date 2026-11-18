import pytest
from decimal import Decimal
from app.services.emv_qr import EMVCoQRParser, EMVCoQRGenerator, calculate_crc16

def test_promptpay_thailand_emv_qr_parsing():
    qr = EMVCoQRGenerator.generate_promptpay_qr(
        phone_or_biller="0066812345678",
        merchant_name="Siam Paragon Cafe",
        city="Bangkok",
        amount=Decimal("150.00")
    )
    parsed = EMVCoQRParser.parse(qr)
    assert parsed["format"] == "EMVCo"
    assert parsed["merchant_name"] == "Siam Paragon Cafe"
    assert parsed["merchant_city"] == "Bangkok"
    assert parsed["merchant_country"] == "TH"
    assert parsed["currency"] == "THB"
    assert parsed["amount"] == Decimal("150.00")
    assert parsed["valid_crc"] is True

def test_qris_indonesia_emv_qr_parsing():
    qr = EMVCoQRGenerator.generate_qris_qr(
        merchant_name="Warung Kopi Bali",
        city="Denpasar",
        amount=Decimal("45000.00")
    )
    parsed = EMVCoQRParser.parse(qr)
    assert parsed["format"] == "EMVCo"
    assert parsed["merchant_name"] == "Warung Kopi Bali"
    assert parsed["merchant_city"] == "Denpasar"
    assert parsed["merchant_country"] == "ID"
    assert parsed["currency"] == "IDR"
    assert parsed["amount"] == Decimal("45000.00")
    assert parsed["valid_crc"] is True

def test_sgqr_singapore_emv_qr_parsing():
    qr = EMVCoQRGenerator.generate_sgqr_qr(
        merchant_name="Maxwell Hawker Centre",
        city="Singapore",
        amount=Decimal("18.50")
    )
    parsed = EMVCoQRParser.parse(qr)
    assert parsed["format"] == "EMVCo"
    assert parsed["merchant_name"] == "Maxwell Hawker Centre"
    assert parsed["currency"] == "SGD"
    assert parsed["amount"] == Decimal("18.50")
    assert parsed["valid_crc"] is True

def test_json_qr_parsing():
    json_qr = EMVCoQRGenerator.generate_json_qr(
        merchant="Shibuya Ramen",
        currency="JPY",
        amount=Decimal("1400"),
        city="Tokyo",
        country="JP"
    )
    parsed = EMVCoQRParser.parse(json_qr)
    assert parsed["format"] == "JSON"
    assert parsed["merchant_name"] == "Shibuya Ramen"
    assert parsed["currency"] == "JPY"
    assert parsed["amount"] == Decimal("1400")

def test_tampered_crc_qr_rejection():
    valid_qr = EMVCoQRGenerator.generate_promptpay_qr()
    tampered_qr = valid_qr[:-4] + "0000"  # Invalid CRC
    is_valid, exp_crc, act_crc = EMVCoQRParser.verify_crc(tampered_qr)
    assert is_valid is False
    assert exp_crc != act_crc

