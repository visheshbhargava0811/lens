"""Loaders for the YAML files in `config/`."""

from pathlib import Path
from typing import Any

import yaml

from lens.core.settings import get_settings


def load_yaml(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or get_settings().config_dir) / name
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return data
