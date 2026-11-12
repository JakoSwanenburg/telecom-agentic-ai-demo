#!/usr/bin/env python3
"""
CLI Entrypoint for Stage 0 (Activity 0.2) Raw Telecom Data Sources Generator (`UC-001`).

Loads centralized configuration from `config.yaml` (with environment variable overrides),
initializes dual local/cloud logging, and executes `run_stage0_generation`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project workspace root is importable when invoked as `python scripts/generate_stage0_raw_sources.py`
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config import load_config
from src.logger import setup_logger
from src.stage0_generator import run_stage0_generation


def main() -> int:
    """Load configuration, configure dual logging, and run Stage 0 generation."""
    config = load_config()
    logger = setup_logger(config=config, logger_name="telco_agent.stage0", workspace_root=WORKSPACE_ROOT)
    logger.info("Starting Stage 0 (Activity 0.2) raw sources generator for %s", config.project.use_case_id)
    run_stage0_generation(config=config, logger=logger, workspace_root=WORKSPACE_ROOT)
    logger.info("Completed Stage 0 (Activity 0.2) raw sources generation successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
