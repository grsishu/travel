from decimal import Decimal
from fastapi import APIRouter, HTTPException, status
from app.schemas import ParseQRRequest, ParsedQRResponse
from app.services.emv_qr import EMVCoQRParser, EMVCoQRGenerator

router = APIRouter(prefix="/api/qr", tags=["QR Code Parser & Test Generator"])

@router.post("/parse", response_model=ParsedQRResponse)
def parse_qr(payload: ParseQRRequest):
    try:
        parsed = EMVCoQRParser.parse(payload.qr_data)
        if not parsed.get("valid_crc", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QR Code integrity check failed (CRC16 mismatch). The QR code may be corrupted or tampered."
            )
        return ParsedQRResponse(
            raw=parsed["raw"],
            format=parsed["format"],
            merchant_name=parsed["merchant_name"],
            merchant_city=parsed.get("merchant_city"),
            merchant_country=parsed.get("merchant_country"),
            currency=parsed["currency"],
            currency_numeric=parsed.get("currency_numeric"),
            amount=parsed.get("amount"),
            tip_amount=parsed.get("tip_amount"),
            reference_id=parsed.get("reference_id"),
            valid_crc=parsed["valid_crc"]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/sample-codes")
def get_sample_qr_codes():
    """Generates valid and invalid sample QR codes for dev/testing."""
    promptpay_fixed = EMVCoQRGenerator.generate_promptpay_qr(
        merchant_name="Bangkok Street Food",
        city="Bangkok",
        amount=Decimal("150.00")
    )
    promptpay_no_amount = EMVCoQRGenerator.generate_promptpay_qr(
        merchant_name="Siam Souvenirs",
        city="Bangkok",
        amount=None
    )
    qris_indonesia = EMVCoQRGenerator.generate_qris_qr(
        merchant_name="Warung Kopi Bali",
        city="Denpasar",
        amount=Decimal("45000.00")
    )
    sgqr_singapore = EMVCoQRGenerator.generate_sgqr_qr(
        merchant_name="Maxwell Hawker Centre",
        city="Singapore",
        amount=Decimal("18.50")
    )
    json_japan = EMVCoQRGenerator.generate_json_qr(
        merchant="Shibuya Ramen Bar",
        currency="JPY",
        amount=Decimal("1400"),
        city="Tokyo",
        country="JP"
    )
    tampered = promptpay_fixed[:-4] + "FFFF"  # Invalid CRC

    return {
        "samples": [
            {
                "title": "PromptPay (Thailand) - 150.00 THB",
                "rail": "PromptPay",
                "currency": "THB",
                "amount": "150.00",
                "qr_string": promptpay_fixed
            },
            {
                "title": "PromptPay (Thailand) - Dynamic (No Amount)",
                "rail": "PromptPay",
                "currency": "THB",
                "amount": None,
                "qr_string": promptpay_no_amount
            },
            {
                "title": "QRIS (Indonesia) - 45,000 IDR",
                "rail": "QRIS",
                "currency": "IDR",
                "amount": "45000.00",
                "qr_string": qris_indonesia
            },
            {
                "title": "SGQR (Singapore) - 18.50 SGD",
                "rail": "SGQR",
                "currency": "SGD",
                "amount": "18.50",
                "qr_string": sgqr_singapore
            },
            {
                "title": "JSON QR (Japan) - 1,400 JPY",
                "rail": "JSON",
                "currency": "JPY",
                "amount": "1400",
                "qr_string": json_japan
            },
            {
                "title": "Tampered QR (Invalid CRC) - Rejection Test",
                "rail": "Tampered",
                "currency": "THB",
                "amount": "150.00",
                "qr_string": tampered
            }
        ]
    }

