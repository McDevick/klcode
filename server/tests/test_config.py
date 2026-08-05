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
