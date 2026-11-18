import uuid
import logging
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional
from app.services.settlement.base import SettlementProvider

logger = logging.getLogger("travelpay.settlement.sandbox")

class SandboxSettlementProvider(SettlementProvider):
    """
    Simulated Settlement Rail for Development and Testing.
    Immediately settles or simulates failure when test triggers are detected.
    """

    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure

    def get_quote(self, from_currency: str, to_currency: str, amount: Decimal) -> Dict[str, Any]:
        return {
            "provider": "sandbox",
            "from_currency": from_currency,
            "to_currency": to_currency,
            "amount": str(amount),
            "estimated_fee": "0.00",
            "settlement_rail": "LOCAL_INSTANT_CLEARING"
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
        # Check if failure is simulated (e.g. merchant name contains FAIL or explicit flag)
        if self.simulate_failure or "FAIL" in merchant_name.upper():
            logger.warning(f"[SANDBOX SETTLEMENT] Simulated failure for merchant {merchant_name}")
            return False, "SETTLEMENT_FAILED", {
                "error": "Merchant bank account unreachable or rejected payment",
                "settlement_id": settlement_id,
                "provider": "sandbox"
            }

        ref_number = f"STL-SANDBOX-{uuid.uuid4().hex[:12].upper()}"
        logger.info(f"[SANDBOX SETTLEMENT] Paid {amount} {currency} to '{merchant_name}' in {city}, {country}. Ref={ref_number}")
        return True, "SETTLED", {
            "settlement_id": settlement_id,
            "reference_number": ref_number,
            "provider": "sandbox",
            "clearing_network": f"{country or 'GLOBAL'}_LOCAL_PAYOUT_RAIL"
        }

    def get_status(self, settlement_id: str) -> Dict[str, Any]:
        return {
            "settlement_id": settlement_id,
            "status": "SETTLED",
            "provider": "sandbox"
        }

    def refund(self, settlement_id: str, reason: str) -> Tuple[bool, str]:
        logger.info(f"[SANDBOX SETTLEMENT] Refunded settlement {settlement_id}. Reason: {reason}")
        return True, f"Refund completed in Sandbox for {settlement_id}"

