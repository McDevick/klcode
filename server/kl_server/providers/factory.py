import os

from kl_server.config.config import AppConfig
from kl_server.providers.mock import MockProvider
from kl_server.providers.openai_compatible import OpenAICompatibleProvider
from kl_server.providers.registry import ProviderRegistry


def build_provider_registry(config: AppConfig, credential_store) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("mock", MockProvider())
    for name, provider_config in config.providers.items():
        if provider_config.type != "openai-compatible":
            raise ValueError(f"unsupported provider type: {provider_config.type}")
        api_key = None
        if provider_config.credential_ref is not None:
            api_key = credential_store.get(provider_config.credential_ref)
        # Environment fallback (KL_KEY_<NAME>, e.g. KL_KEY_DEEPSEEK) so keys
        # survive restarts even when the OS keyring is unavailable.
        if api_key is None:
            api_key = os.environ.get(f"KL_KEY_{name.upper()}")
        if provider_config.credential_ref is not None and api_key is None:
            raise ValueError(f"credential not found: {provider_config.credential_ref}")
        registry.register(
            name,
            OpenAICompatibleProvider(
                base_url=provider_config.base_url,
                api_key=api_key,
                model=provider_config.default_model,
            ),
        )
    return registry
