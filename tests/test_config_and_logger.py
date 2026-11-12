"""
Unit tests for `src/config.py`, `src/models.py`, and `src/logger.py`.

Covers default YAML loading, environment variable overrides, Pydantic v2 schema
validation, fail-fast exceptions, and dual local vs. cloud logging behavior.
"""

from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import load_config
from src.logger import is_cloud_environment, setup_logger


def test_load_default_workspace_config() -> None:
    """Verify default `config.yaml` loads cleanly and matches locked project settings."""
    cfg = load_config()
    assert cfg.project.name == "telecom-agentic-ai-demo"
    assert cfg.project.use_case_id == "UC-001"
    assert cfg.gcp.project_id == "telecom-agentic-ai-demo"
    assert cfg.gcp.region == "europe-west4"
    assert cfg.stage0.target_circuit_id == "CIR-994821"
    assert cfg.stage0.target_customer_id == "CUST-ENT-409"
    assert cfg.stage0.target_product_sku == "ETH-10G-GOLD"
    assert cfg.stage0.target_cpe_model_sku == "NOK-7210-SAS-Mxp"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment variables override values defined in `config.yaml`."""
    monkeypatch.setenv("ENV", "cloud")
    monkeypatch.setenv("GCP_PROJECT_ID", "override-gcp-project")
    monkeypatch.setenv("GCP_REGION", "europe-west1")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_DIR", "custom_logs")
    monkeypatch.setenv("STAGE0_RAW_DIR", "custom/raw")
    monkeypatch.setenv("STAGE0_SEED", "99")
    monkeypatch.setenv("AI_MODEL_NAME", "gemini-2.5-flash")

    cfg = load_config()
    assert cfg.project.environment == "cloud"
    assert cfg.gcp.project_id == "override-gcp-project"
    assert cfg.gcp.region == "europe-west1"
    assert cfg.logging.level == "DEBUG"
    assert cfg.logging.log_dir == "custom_logs"
    assert cfg.paths.raw_sources_dir == "custom/raw"
    assert cfg.stage0.seed == 99
    assert cfg.ai.model_name == "gemini-2.5-flash"


def test_fail_fast_missing_config_file(tmp_path: Path) -> None:
    """Verify `load_config` fails fast with `FileNotFoundError` when file is missing."""
    missing_file = tmp_path / "nonexistent_config.yaml"
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config(config_path=missing_file)


def test_fail_fast_empty_config_file(tmp_path: Path) -> None:
    """Verify `load_config` fails fast with `ValueError` when YAML is empty."""
    empty_file = tmp_path / "empty.yaml"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty YAML mapping"):
        load_config(config_path=empty_file)


def test_fail_fast_invalid_seed_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify `STAGE0_SEED` fails fast when set to a non-integer string."""
    monkeypatch.setenv("STAGE0_SEED", "not-an-int")
    with pytest.raises(ValueError, match="Invalid integer value for environment variable STAGE0_SEED"):
        load_config()


def test_fail_fast_extra_unknown_field_in_yaml(tmp_path: Path) -> None:
    """Verify `ConfigDict(extra='forbid')` rejects unknown keys in `config.yaml`."""
    bad_yaml = tmp_path / "bad_config.yaml"
    default_text = Path("config.yaml").read_text(encoding="utf-8")
    bad_yaml.write_text(default_text + "\nunknown_top_level_key: 123\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(config_path=bad_yaml)


def test_dual_logger_local_mode_creates_rotating_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify local execution writes both to stdout and a rotating file in `logs/`."""
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)

    cfg = load_config()
    assert not is_cloud_environment(cfg)

    logger = setup_logger(config=cfg, logger_name="test.local.logger", workspace_root=tmp_path)
    logger.info("Local dual logging test message")

    for h in logger.handlers:
        h.flush()

    file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1

    expected_log_file = tmp_path / cfg.logging.log_dir / cfg.logging.log_filename
    assert expected_log_file.exists()
    assert "Local dual logging test message" in expected_log_file.read_text(encoding="utf-8")

    # Clean up handlers so tmp_path file locks are released on Windows
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def test_dual_logger_cloud_mode_skips_local_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify cloud execution (`K_SERVICE` or `ENV=cloud`) does NOT create local log files."""
    monkeypatch.setenv("K_SERVICE", "telco-agent-cloud-run")
    cfg = load_config()
    assert is_cloud_environment(cfg)

    logger = setup_logger(config=cfg, logger_name="test.cloud.logger", workspace_root=tmp_path)
    logger.info("Cloud stdout-only test message")

    file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 0

    log_dir = tmp_path / cfg.logging.log_dir
    assert not log_dir.exists()

