from pathlib import Path

import yaml

from kl_server.config.config import AppConfig


DEEPSEEK_PRESET = {
    "name": "deepseek",
    "type": "openai-compatible",
    "base_url": "https://api.deepseek.com",
    "default_model": "deepseek-v4-flash",
    "max_context": 20000,
    "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    "api_key": None,
    "credential_ref": None,
}


def _merge_deepseek_preset(data: dict) -> dict:
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    existing = next(
        (key for key in providers if str(key).lower() == "deepseek"),
        None,
    )
    target = existing or "deepseek"
    preset = dict(DEEPSEEK_PRESET)
    if target in providers and isinstance(providers[target], dict):
        user_config = providers[target]
        preset.update(
            {
                key: value
                for key, value in user_config.items()
                if value is not None
            }
        )
    providers[target] = preset
    data["providers"] = providers
    if not data.get("default_provider"):
        data["default_provider"] = target
    return data


def load_app_config(path: Path) -> AppConfig:
    if not Path(path).exists():
        data = {}
    else:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(_merge_deepseek_preset(dict(data)))
