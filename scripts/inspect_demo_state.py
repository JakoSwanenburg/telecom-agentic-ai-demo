#!/usr/bin/env python3
"""
CLI Entrypoint for `SYS-01` (Live System State Inspector).

Inspects all 7 architectural elements, prints a Rich status table to the console,
and writes `reports/system_state_dashboard.html` and `reports/system_state_dashboard.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config_loader import load_config
from src.logger import setup_logger
from src.state_inspector import inspect_system_state


def main() -> int:
    """Load configuration, run `SYS-01` inspection, and render outputs."""
    config = load_config()
    logger = setup_logger(
        config=config,
        logger_name="telco_agent.sys01",
        workspace_root=WORKSPACE_ROOT,
    )
    inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=WORKSPACE_ROOT,
        render_console=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

