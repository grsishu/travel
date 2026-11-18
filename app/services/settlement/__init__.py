from app.config import settings
from app.services.settlement.base import SettlementProvider
from app.services.settlement.sandbox import SandboxSettlementProvider
from app.services.settlement.wise import WiseProvider
from app.services.settlement.airwallex import AirwallexProvider

def get_settlement_provider(provider_name: str = None) -> SettlementProvider:
    name = (provider_name or settings.SETTLEMENT_PROVIDER).lower()
    if name == "wise":
        return WiseProvider()
    elif name == "airwallex":
        return AirwallexProvider()
    return SandboxSettlementProvider()

