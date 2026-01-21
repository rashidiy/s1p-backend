"""
Telephony provider abstraction layer
"""

from .base import TelephonyProvider, CallRequest, CallResponse, CallStatus, ProviderException
from .factory import ProviderFactory
from .sipuni_provider import SipuniProvider
from .binotel_provider import BinotelProvider

# Register providers
ProviderFactory.register('sipuni', SipuniProvider)
ProviderFactory.register('binotel', BinotelProvider)

__all__ = [
    "TelephonyProvider",
    "CallRequest",
    "CallResponse",
    "CallStatus",
    "ProviderException",
    "ProviderFactory",
    "SipuniProvider",
    "BinotelProvider",
]
