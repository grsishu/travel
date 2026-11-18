import abc
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional

class SettlementProvider(abc.ABC):
    """
    Abstract Settlement Rail Provider.
    Handles converting INR / settled funds into foreign local currency payout to foreign merchant.
    """

    @abc.abstractmethod
    def get_quote(self, from_currency: str, to_currency: str, amount: Decimal) -> Dict[str, Any]:
        """Gets live conversion quote and estimated settlement fee from provider."""
        pass

    @abc.abstractmethod
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
        """
        Dispatches local currency payment to merchant via local rail.
        Returns: (success: bool, status: str, details: dict)
        """
        pass

    @abc.abstractmethod
    def get_status(self, settlement_id: str) -> Dict[str, Any]:
        """Queries settlement rail for current execution status."""
        pass

    @abc.abstractmethod
    def refund(self, settlement_id: str, reason: str) -> Tuple[bool, str]:
        """Requests reversal/refund of settled payment."""
        pass

