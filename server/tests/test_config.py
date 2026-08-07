from pathlib import Path

from kl_server.config.config import AppConfig
from kl_server.config.loader import load_app_config


def test_app_config_default_model_defaults_to_empty():
    config = AppConfig()

    assert config.default_provider == "mock"
    assert config.default_model == ""


def test_app_config_loads_default_model_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "default_provider: deepseek\n"
        "default_model: deepseek-chat\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.default_provider == "deepseek"
    assert config.default_model == "deepseek-chat"
    assert config.providers["deepseek"].max_context == 20000


def test_app_config_loads_max_context_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n"
        "    max_context: 128000\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.providers["deepseek"].max_context == 128000


def test_app_config_loads_models_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-v4-flash\n"
        "    models:\n"
        "      - deepseek-v4-flash\n"
        "      - deepseek-v4-pro\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.providers["deepseek"].models == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]


def test_app_config_merges_deepseek_preset_when_missing(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")

    config = load_app_config(path)

    assert config.default_provider == "deepseek"
    provider = config.providers["deepseek"]
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.default_model == "deepseek-v4-flash"
    assert provider.models == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert provider.credential_ref is None


def test_app_config_user_deepseek_overrides_preset_fields(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    base_url: https://custom.deepseek.com\n"
        "    default_model: deepseek-v4-pro\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    provider = config.providers["deepseek"]
    assert provider.base_url == "https://custom.deepseek.com"
    assert provider.default_model == "deepseek-v4-pro"
    assert provider.max_context == 20000
    assert provider.models == ["deepseek-v4-flash", "deepseek-v4-pro"]


def test_app_config_merges_existing_capitalized_deepseek(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  Deepseek:\n"
        "    base_url: https://custom.deepseek.com\n"
        "    default_model: deepseek-v4-pro\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.default_provider == "Deepseek"
    provider = config.providers["Deepseek"]
    assert provider.base_url == "https://custom.deepseek.com"
    assert provider.max_context == 20000
