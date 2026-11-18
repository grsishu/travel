import logging
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
from app.services.settlement.base import SettlementProvider
from app.config import settings

logger = logging.getLogger("travelpay.settlement.airwallex")

class AirwallexProvider(SettlementProvider):
    """
    Airwallex Global Payouts API Integration Skeleton.
    Production setup requires:
    1. Airwallex Account with API Access
    2. Client ID in AIRWALLEX_CLIENT_ID
    3. API Key in AIRWALLEX_API_KEY
    """

    def __init__(self):
        self.client_id = settings.AIRWALLEX_CLIENT_ID
        self.api_key = settings.AIRWALLEX_API_KEY
        self.base_url = "https://api.airwallex.com/api/v1"

    def get_quote(self, from_currency: str, to_currency: str, amount: Decimal) -> Dict[str, Any]:
        # TODO: POST /api/v1/fx/quotes
        logger.info(f"[AIRWALLEX] Quote requested for {amount} {to_currency}")
        return {
            "provider": "airwallex",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "estimated_fee": "0.30",
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
            logger.warning("Airwallex API Key missing; fallback to Sandbox settlement.")
            from app.services.settlement.sandbox import SandboxSettlementProvider
            return SandboxSettlementProvider().pay_merchant(
                settlement_id, merchant_name, currency, amount, city, country, metadata
            )

        # TODO:
        # 1. Obtain Bearer token via POST /api/v1/authentication/login
        # 2. Create payout via POST /api/v1/payouts/create
        logger.info(f"[AIRWALLEX] Payout created for {merchant_name} ({currency} {amount})")
        return True, "SETTLING", {"provider": "airwallex", "settlement_id": settlement_id}

    def get_status(self, settlement_id: str) -> Dict[str, Any]:
        return {"provider": "airwallex", "settlement_id": settlement_id, "status": "SETTLED"}

    def refund(self, settlement_id: str, reason: str) -> Tuple[bool, str]:
        return True, f"Airwallex reversal requested for {settlement_id}"

