from pathlib import Path

import yaml

from kl_server.config.config import AppConfig


def load_app_config(path: Path) -> AppConfig:
    if not Path(path).exists():
        return AppConfig()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)
