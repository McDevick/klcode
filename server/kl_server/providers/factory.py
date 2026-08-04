from kl_server.config.config import AppConfig
from kl_server.providers.mock import MockProvider
from kl_server.providers.openai_compatible import OpenAICompatibleProvider
from kl_server.providers.registry import ProviderRegistry


def build_provider_registry(config: AppConfig, credential_store) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("mock", MockProvider())
    for name, provider_config in config.providers.items():
        api_key = credential_store.get(provider_config.credential_ref) if provider_config.credential_ref else None
        registry.register(
            name,
            OpenAICompatibleProvider(
                base_url=provider_config.base_url,
                api_key=api_key,
                model=provider_config.default_model,
            ),
        )
    return registry
