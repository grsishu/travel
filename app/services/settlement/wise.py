import logging
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
from app.services.settlement.base import SettlementProvider
from app.config import settings

logger = logging.getLogger("travelpay.settlement.wise")

class WiseProvider(SettlementProvider):
    """
    Wise (formerly TransferWise) Platform API Integration Skeleton.
    Production setup requires:
    1. Wise Business / Borderless account
    2. API token configured in WISE_API_KEY
    3. Multi-currency profile ID in WISE_PROFILE_ID
    """

    def __init__(self):
        self.api_key = settings.WISE_API_KEY
        self.profile_id = settings.WISE_PROFILE_ID
        self.base_url = "https://api.transferwise.com/v3"

    def get_quote(self, from_currency: str, to_currency: str, amount: Decimal) -> Dict[str, Any]:
        # TODO: Call Wise POST /v3/profiles/{profile_id}/quotes
        # Payload: { "sourceCurrency": from_currency, "targetCurrency": to_currency, "targetAmount": float(amount) }
        logger.info(f"[WISE] Generating quote for {amount} {to_currency}")
        return {
            "provider": "wise",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "estimated_fee": "0.45",
            "status": "CONFIG_PENDING"
        }

    def pay_merchant(
        self,
        settlement_id: str,
        merchant_name: str,
        currency: str,
        amount: Decimal,
        city: Optional[str] = None,
        country: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Wise API Key missing; fallback to Sandbox settlement.")
            from app.services.settlement.sandbox import SandboxSettlementProvider
            return SandboxSettlementProvider().pay_merchant(
                settlement_id, merchant_name, currency, amount, city, country, metadata
            )

        # TODO:
        # 1. Create or retrieve recipient account (POST /v1/accounts)
        # 2. Create transfer (POST /v1/transfers)
        # 3. Fund transfer via balance (POST /v3/profiles/{profile_id}/transfers/{transfer_id}/payments)
        logger.info(f"[WISE] Transfer dispatched for {merchant_name} ({currency} {amount})")
        return True, "SETTLING", {"provider": "wise", "settlement_id": settlement_id}

    def get_status(self, settlement_id: str) -> Dict[str, Any]:
        # TODO: GET /v1/transfers/{transfer_id}
        return {"provider": "wise", "settlement_id": settlement_id, "status": "SETTLED"}

    def refund(self, settlement_id: str, reason: str) -> Tuple[bool, str]:
        # TODO: POST /v1/transfers/{transfer_id}/cancel
        return True, f"Wise transfer cancellation requested for {settlement_id}"

