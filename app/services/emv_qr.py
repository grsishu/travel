import json
import re
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple
from app.services.rates import NUMERIC_TO_ALPHA_CURRENCY

def calculate_crc16(payload_without_crc_value: str) -> str:
    """
    EMVCo CRC-16 (CCITT, polynomial 0x1021, init 0xFFFF, non-reflected).
    Calculated over the data including '6304'.
    """
    crc = 0xFFFF
    for byte in payload_without_crc_value.encode("utf-8"):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

class EMVCoQRParser:
    @staticmethod
    def parse_tlv(payload: str) -> Dict[str, str]:
        """Parses top-level EMVCo TLV string into dictionary of tag -> value."""
        tlv_dict = {}
        idx = 0
        n = len(payload)
        while idx < n:
            if idx + 4 > n:
                break
            tag = payload[idx:idx+2]
            length_str = payload[idx+2:idx+4]
            if not length_str.isdigit():
                break
            length = int(length_str)
            idx += 4
            if idx + length > n:
                break
            value = payload[idx:idx+length]
            tlv_dict[tag] = value
            idx += length
        return tlv_dict

    @classmethod
    def verify_crc(cls, payload: str) -> Tuple[bool, str, str]:
        """
        Verifies Tag 63 CRC.
        Returns: (is_valid, expected_crc, actual_crc)
        """
        match = re.search(r"6304([0-9A-Fa-f]{4})$", payload)
        if not match:
            return False, "", ""
        actual_crc = match.group(1).upper()
        # Payload up to and including '6304'
        payload_to_crc = payload[:match.start() + 4]
        expected_crc = calculate_crc16(payload_to_crc).upper()
        return (expected_crc == actual_crc), expected_crc, actual_crc

    @classmethod
    def parse(cls, qr_string: str) -> Dict[str, Any]:
        """
        Universal QR parser: EMVCo TLV or JSON.
        Returns structured dict with merchant, country, currency, amount, etc.
        """
        text = qr_string.strip()

        # 1. Try JSON parsing
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                merchant = data.get("merchant") or data.get("merchant_name") or "Foreign Merchant"
                currency = (data.get("currency") or "USD").upper()
                amount_raw = data.get("amount")
                amount = Decimal(str(amount_raw)) if amount_raw is not None else None
                return {
                    "raw": text,
                    "format": "JSON",
                    "merchant_name": merchant,
                    "merchant_city": data.get("city", "City"),
                    "merchant_country": data.get("country", "US"),
                    "currency": currency,
                    "currency_numeric": None,
                    "amount": amount,
                    "tip_amount": None,
                    "reference_id": data.get("reference") or data.get("ref_id"),
                    "valid_crc": True
                }
            except Exception as e:
                pass

        # 2. Try EMVCo TLV parsing
        # Look for Tag 00 == "01"
        if len(text) >= 10 and text.startswith("000201"):
            tlvs = cls.parse_tlv(text)
            if "00" in tlvs and tlvs["00"] == "01":
                is_valid_crc, exp_crc, act_crc = cls.verify_crc(text)

                currency_num = tlvs.get("53")
                currency_alpha = NUMERIC_TO_ALPHA_CURRENCY.get(currency_num, "THB") if currency_num else "THB"

                amount_str = tlvs.get("54")
                amount = Decimal(amount_str) if amount_str else None

                country = tlvs.get("58", "TH")
                merchant_name = tlvs.get("59", "Foreign Merchant")
                city = tlvs.get("60", "City")

                ref_id = None
                if "62" in tlvs:
                    sub_tlvs = cls.parse_tlv(tlvs["62"])
                    ref_id = sub_tlvs.get("01") or sub_tlvs.get("05")

                return {
                    "raw": text,
                    "format": "EMVCo",
                    "merchant_name": merchant_name,
                    "merchant_city": city,
                    "merchant_country": country,
                    "currency": currency_alpha,
                    "currency_numeric": currency_num,
                    "amount": amount,
                    "tip_amount": None,
                    "reference_id": ref_id,
                    "valid_crc": is_valid_crc
                }

        # 3. Fallback: URL or unstructured text
        raise ValueError("Unsupported or malformed QR format. Expected EMVCo TLV QR (PromptPay, QRIS, SGQR) or JSON.")

class EMVCoQRGenerator:
    """Helper to generate valid EMVCo QR strings for PromptPay, QRIS, SGQR, and test JSON"""

    @staticmethod
    def build_tlv(tag: str, value: str) -> str:
        length = f"{len(value):02d}"
        return f"{tag}{length}{value}"

    @classmethod
    def generate_promptpay_qr(
        cls,
        phone_or_biller: str = "0066812345678",
        merchant_name: str = "Siam Paragon Cafe",
        city: str = "Bangkok",
        amount: Optional[Decimal] = Decimal("150.00")
    ) -> str:
        """Thailand PromptPay QR (Currency: 764 THB, Country: TH)"""
        # Tag 29 is PromptPay info
        tag29_aid = cls.build_tlv("00", "A000000677010111")
        tag29_target = cls.build_tlv("01", phone_or_biller)
        tag29_val = tag29_aid + tag29_target

        parts = [
            cls.build_tlv("00", "01"),
            cls.build_tlv("01", "12" if amount else "11"),
            cls.build_tlv("29", tag29_val),
            cls.build_tlv("53", "764"),  # THB
        ]
        if amount:
            parts.append(cls.build_tlv("54", f"{amount:.2f}"))
        parts.extend([
            cls.build_tlv("58", "TH"),
            cls.build_tlv("59", merchant_name),
            cls.build_tlv("60", city),
        ])
        raw_without_crc = "".join(parts) + "6304"
        crc = calculate_crc16(raw_without_crc)
        return raw_without_crc + crc

    @classmethod
    def generate_qris_qr(
        cls,
        merchant_name: str = "Warung Bali Delight",
        city: str = "Denpasar",
        amount: Optional[Decimal] = Decimal("50000.00")
    ) -> str:
        """Indonesia QRIS QR (Currency: 360 IDR, Country: ID)"""
        # Tag 26 QRIS info
        tag26_aid = cls.build_tlv("00", "ID.CO.QRIS.WWW")
        tag26_mid = cls.build_tlv("01", "ID1020030040050")
        tag26_val = tag26_aid + tag26_mid

        parts = [
            cls.build_tlv("00", "01"),
            cls.build_tlv("01", "12" if amount else "11"),
            cls.build_tlv("26", tag26_val),
            cls.build_tlv("52", "5812"),
            cls.build_tlv("53", "360"),  # IDR
        ]
        if amount:
            parts.append(cls.build_tlv("54", f"{amount:.2f}"))
        parts.extend([
            cls.build_tlv("58", "ID"),
            cls.build_tlv("59", merchant_name),
            cls.build_tlv("60", city),
        ])
        raw_without_crc = "".join(parts) + "6304"
        crc = calculate_crc16(raw_without_crc)
        return raw_without_crc + crc

    @classmethod
    def generate_sgqr_qr(
        cls,
        merchant_name: str = "Marina Bay Street Food",
        city: str = "Singapore",
        amount: Optional[Decimal] = Decimal("25.50")
    ) -> str:
        """Singapore SGQR (Currency: 702 SGD, Country: SG)"""
        tag26_aid = cls.build_tlv("00", "COM.NETS.SGQR")
        tag26_mid = cls.build_tlv("01", "111199998888")
        tag26_val = tag26_aid + tag26_mid

        parts = [
            cls.build_tlv("00", "01"),
            cls.build_tlv("01", "12" if amount else "11"),
            cls.build_tlv("26", tag26_val),
            cls.build_tlv("52", "5411"),
            cls.build_tlv("53", "702"),  # SGD
        ]
        if amount:
            parts.append(cls.build_tlv("54", f"{amount:.2f}"))
        parts.extend([
            cls.build_tlv("58", "SG"),
            cls.build_tlv("59", merchant_name),
            cls.build_tlv("60", city),
        ])
        raw_without_crc = "".join(parts) + "6304"
        crc = calculate_crc16(raw_without_crc)
        return raw_without_crc + crc

    @classmethod
    def generate_json_qr(
        cls,
        merchant: str = "Shinjuku Ramen",
        currency: str = "JPY",
        amount: Decimal = Decimal("1200"),
        city: str = "Tokyo",
        country: str = "JP"
    ) -> str:
        data = {
            "merchant": merchant,
            "currency": currency,
            "amount": float(amount),
            "city": city,
            "country": country,
            "type": "merchant_payment"
        }
        return json.dumps(data)

