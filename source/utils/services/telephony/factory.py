"""
Telephony provider factory
"""

from typing import Dict, Any
from .base import TelephonyProvider


class ProviderFactory:
    """
    Factory for creating telephony provider instances

    Automatically routes to the correct provider based on provider_type
    """

    _providers: Dict[str, type] = {}

    @classmethod
    def create(
        cls,
        provider_type: str,
        config: Dict[str, Any]
    ) -> TelephonyProvider:
        """
        Create provider instance

        Args:
            provider_type: 'sipuni' or 'binotel'
            config: Provider configuration from companies.provider_config

        Returns:
            TelephonyProvider instance

        Raises:
            ValueError: If provider_type is not supported

        Example:
            >>> provider = ProviderFactory.create(
            ...     'sipuni',
            ...     {'cabinet_id': '12345', 'security_key': 'secret'}
            ... )
            >>> result = await provider.make_call(call_request)
        """
        provider_class = cls._providers.get(provider_type)

        if not provider_class:
            raise ValueError(
                f"Unsupported provider: {provider_type}. "
                f"Supported providers: {list(cls._providers.keys())}"
            )

        return provider_class(config)

    @classmethod
    def register(cls, provider_type: str, provider_class: type):
        """
        Register a new provider implementation

        Args:
            provider_type: Provider identifier (e.g., 'sipuni')
            provider_class: Provider class (must inherit from TelephonyProvider)

        Example:
            >>> ProviderFactory.register('my_provider', MyProviderClass)
        """
        cls._providers[provider_type] = provider_class

    @classmethod
    def list_providers(cls) -> list:
        """Get list of registered providers"""
        return list(cls._providers.keys())
