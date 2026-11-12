#!/usr/bin/env python3
"""
CLI Entrypoint for Scenario `DT-00` (Wipe & Reset to Clean Slate).

Usage:
  python scripts/reset_demo_state.py
  python scripts/reset_demo_state.py --set-catalog-gap
  python scripts/reset_demo_state.py --set-catalog-gap true
  python scripts/reset_demo_state.py --set-catalog-gap false
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from rich.console import Console
from rich.panel import Panel

from src.config_loader import load_config
from src.logger import setup_logger
from src.state_manager import reset_to_clean_slate


def _parse_bool_flag(val: str) -> bool:
    """Parse flexible CLI boolean strings (`true`, `false`, `1`, `0`, `yes`, `no`)."""
    normalized = val.strip().lower()
    if normalized in {"true", "1", "yes", "y", "gap"}:
        return True
    if normalized in {"false", "0", "no", "n", "complete"}:
        return False
    raise argparse.ArgumentTypeError(
        f"Invalid boolean value '{val}' for --set-catalog-gap (expected true or false)."
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser for `scripts/reset_demo_state.py`."""
    parser = argparse.ArgumentParser(
        description="Execute Scenario DT-00: Wipe & Reset Demo State to Clean Slate."
    )
    parser.add_argument(
        "--set-catalog-gap",
        nargs="?",
        const=True,
        default=False,
        type=_parse_bool_flag,
        help=(
            "When true (or passed without a value), disables TMF621 in "
            "config/mcp_primitives_catalog.json (PARTIAL_GAP for DT-02a). "
            "Defaults to false (enable_tmf621_dispatch_primitive=true)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, execute `reset_to_clean_slate`, and print a Rich summary."""
    args = build_arg_parser().parse_args(argv)
    config = load_config()
    logger = setup_logger(
        config=config,
        logger_name="telco_agent.dt00",
        workspace_root=WORKSPACE_ROOT,
    )

    summary = reset_to_clean_slate(
        config=config,
        logger=logger,
        set_catalog_gap=bool(args.set_catalog_gap),
        workspace_root=WORKSPACE_ROOT,
    )

    console = Console()
    catalog_mode = (
        "PARTIAL_GAP (enable_tmf621_dispatch_primitive=false)"
        if summary.catalog_gap_enabled
        else "COMPLETE (enable_tmf621_dispatch_primitive=true)"
    )
    panel_text = (
        f"[bold cyan]Scenario:[/bold cyan] {summary.scenario_id} — Wipe & Reset to Clean Slate\n"
        f"[bold cyan]Reset Timestamp (UTC):[/bold cyan] {summary.reset_timestamp_utc}\n"
        f"[bold cyan]Removed Build/Runtime Artifacts:[/bold cyan] {len(summary.removed_files)} file(s)\n"
        f"[bold cyan]Preserved Stage 0 Raw Files:[/bold cyan] {summary.preserved_raw_sources_count} file(s) in data/raw_sources/\n"
        f"[bold cyan]MCP Primitive Catalog Mode:[/bold cyan] {catalog_mode}\n"
        f"[bold cyan]CQRS Runtime State Reset:[/bold cyan] 0 active mutex locks | "
        f"{config.cqrs_action_plane.rate_limit_max_tokens}/{config.cqrs_action_plane.rate_limit_max_tokens} rate-limit tokens"
    )
    console.print(
        Panel(
            panel_text,
            title="[bold green]DT-00 Clean-Slate Wipe Complete[/bold green]",
            expand=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

