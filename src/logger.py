"""
Dual Logging Module (Local Rotating File + Console vs. Cloud Standard Output).

Compliant with AGENTS.md Part 2.4:
  - Always outputs clear progress and log messages to the console (`stdout`).
  - Local Execution: Writes detailed logs to rotating log files inside a relative
    log directory (`config.logging.log_dir`, defaulting to `./logs/`) in addition
    to console output.
  - Cloud Execution: When running in a cloud environment (detected via
    `config.project.environment == "cloud"`, `ENV=cloud`, or `K_SERVICE`), streams
    logs purely to standard output without creating local log files.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path
from typing import Optional

from src.config import get_workspace_root
from src.models import AppConfig


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def is_cloud_environment(config: AppConfig) -> bool:
    """
    Return True if executing in a cloud/serverless environment.

    Checks `config.project.environment == "cloud"`, `ENV=cloud`, or `K_SERVICE`
    (Google Cloud Run runtime indicator).
    """
    env_var = os.getenv("ENV", "").strip().lower()
    k_service = os.getenv("K_SERVICE", "").strip()
    return (
        config.project.environment.lower() == "cloud"
        or env_var == "cloud"
        or bool(k_service)
    )


def setup_logger(
    config: AppConfig,
    logger_name: str = "telco_agent",
    workspace_root: Optional[Path] = None,
) -> logging.Logger:
    """
    Configure and return a dual-mode logger instance based on `AppConfig`.

    Clears any existing handlers on `logger_name` so repeated invocations in tests
    or CLI scripts remain deterministic and do not duplicate log lines.
    """
    logger = logging.getLogger(logger_name)
    numeric_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    logger.propagate = False

    # Close and remove prior handlers for idempotency
    for existing_handler in list(logger.handlers):
        existing_handler.close()
        logger.removeHandler(existing_handler)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console handler (always attached)
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Local rotating file handler (attached only when NOT in cloud mode)
    if not is_cloud_environment(config):
        root_dir = workspace_root if workspace_root is not None else get_workspace_root()
        log_dir_path = root_dir / Path(config.logging.log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir_path / config.logging.log_filename

        file_handler = RotatingFileHandler(
            filename=str(log_file_path),
            maxBytes=config.logging.max_bytes,
            backupCount=config.logging.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

