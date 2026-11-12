"""
Configuration Loader Facade (`src/config_loader.py`).

Re-exports `load_config`, `get_workspace_root`, and `AppConfig` so components
referencing either `src.config` or `src.config_loader` read the single root `config.yaml`.
"""

from __future__ import annotations

from src.config import DEFAULT_CONFIG_FILENAME, get_workspace_root, load_config
from src.models import AppConfig

__all__ = [
    "AppConfig",
    "DEFAULT_CONFIG_FILENAME",
    "get_workspace_root",
    "load_config",
]

