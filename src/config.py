"""
Centralized Configuration Loader (`config.yaml` + Environment Variable Overrides).

Enforces fail-fast execution and strict Pydantic v2 validation per AGENTS.md
Part 2.3, Part 2.5, and Part 3.1.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from src.models import AppConfig


DEFAULT_CONFIG_FILENAME = "config.yaml"


def get_workspace_root() -> Path:
    """Return the OS-agnostic project workspace root directory."""
    return Path(__file__).resolve().parent.parent


def _apply_env_overrides(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply environment variable overrides on top of the parsed `config.yaml` dictionary.

    Supported environment variables:
      - `ENV`: Overrides `project.environment` (e.g. `local`, `cloud`, `prod`)
      - `GCP_PROJECT_ID`: Overrides `gcp.project_id`
      - `GCP_REGION`: Overrides `gcp.region`
      - `LOG_LEVEL`: Overrides `logging.level`
      - `LOG_DIR`: Overrides `logging.log_dir`
      - `STAGE0_RAW_DIR`: Overrides `paths.raw_sources_dir`
      - `STAGE0_SEED`: Overrides `stage0.seed`
      - `AI_MODEL_NAME`: Overrides `ai.model_name`
      - `LAYER3_EXECUTION_MODE`: Overrides `layer3_nl2semantics.execution_mode`
      - `CQRS_TELEMETRY_PRESET`: Overrides `cqrs_action_plane.active_telemetry_preset`
    """
    env_val = os.getenv("ENV")
    if env_val:
        raw_data.setdefault("project", {})["environment"] = env_val.strip()

    gcp_project = os.getenv("GCP_PROJECT_ID")
    if gcp_project:
        raw_data.setdefault("gcp", {})["project_id"] = gcp_project.strip()

    gcp_region = os.getenv("GCP_REGION")
    if gcp_region:
        raw_data.setdefault("gcp", {})["region"] = gcp_region.strip()

    log_level = os.getenv("LOG_LEVEL")
    if log_level:
        raw_data.setdefault("logging", {})["level"] = log_level.strip().upper()

    log_dir = os.getenv("LOG_DIR")
    if log_dir:
        raw_data.setdefault("logging", {})["log_dir"] = log_dir.strip()

    raw_dir = os.getenv("STAGE0_RAW_DIR")
    if raw_dir:
        raw_data.setdefault("paths", {})["raw_sources_dir"] = raw_dir.strip()

    seed_str = os.getenv("STAGE0_SEED")
    if seed_str is not None and seed_str.strip() != "":
        try:
            raw_data.setdefault("stage0", {})["seed"] = int(seed_str.strip())
        except ValueError as exc:
            raise ValueError(
                f"Invalid integer value for environment variable STAGE0_SEED='{seed_str}'"
            ) from exc

    ai_model = os.getenv("AI_MODEL_NAME")
    if ai_model:
        raw_data.setdefault("ai", {})["model_name"] = ai_model.strip()

    layer1_mode = os.getenv("LAYER1_TRANSPORT_MODE")
    if layer1_mode:
        raw_data.setdefault("layer1_orchestrator", {})[
            "transport_mode"
        ] = layer1_mode.strip()

    layer3_mode = os.getenv("LAYER3_EXECUTION_MODE")
    if layer3_mode:
        raw_data.setdefault("layer3_nl2semantics", {})["execution_mode"] = layer3_mode.strip()

    telemetry_preset = os.getenv("CQRS_TELEMETRY_PRESET")
    if telemetry_preset:
        raw_data.setdefault("cqrs_action_plane", {})[
            "active_telemetry_preset"
        ] = telemetry_preset.strip()

    return raw_data


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """
    Load and validate `config.yaml` using Pydantic v2 (`AppConfig`).

    Fails fast with explicit `FileNotFoundError` or `ValueError` if the configuration
    file is missing, empty, or violates the schema.
    """
    resolved_path = (
        config_path
        if config_path is not None
        else get_workspace_root() / DEFAULT_CONFIG_FILENAME
    )

    if not resolved_path.exists() or not resolved_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found at expected path: {resolved_path}"
        )

    raw_text = resolved_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw_text)
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(
            f"Configuration file '{resolved_path}' must contain a non-empty YAML mapping."
        )

    merged = _apply_env_overrides(parsed)
    return AppConfig.model_validate(merged)
