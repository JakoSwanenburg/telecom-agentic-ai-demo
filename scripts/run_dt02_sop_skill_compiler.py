r"""
CLI Runner for Track A Scenarios DT-02a & DT-02b:
100% Document-Independent SOP-to-Skill Compiler, Adverse Guardrail Rejection Test Harness,
and Two-Phase Mandatory HITL Gate 3 Lock.

Usage:
  .\.venv\Scripts\python.exe scripts\run_dt02_sop_skill_compiler.py                     # Default: --mode candidate
  .\.venv\Scripts\python.exe scripts\run_dt02_sop_skill_compiler.py --mode approve      # Phase 2: Materialize skills/
  .\.venv\Scripts\python.exe scripts\run_dt02_sop_skill_compiler.py --interactive       # Phase 1 -> Prompt -> Phase 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config_loader import load_config
from src.logger import setup_logger
from src.track_a.sop_to_skill_compiler import run_dt02_sop_skill_compiler


def _print_result(console: Console, res) -> None:
    console.print(
        Panel.fit(
            f"Mode: {res.mode}\n"
            f"SYS-01 Element 6 State: {res.sys01_element6_state}\n"
            f"Model Used: {res.model_used}\n"
            f"MCP Catalog State: {res.catalog_state}\n"
            f"DT-02b Adverse Proof: {res.adverse_tests_passed}/{res.adverse_tests_total} PASSED\n"
            f"Candidate JSON: {res.candidate_proposal_path}\n"
            f"Active Skill YAML: {res.active_skill_path}\n"
            f"Active Guardrails JSON: {res.active_guardrails_path}\n"
            f"HITL Gate 3 HTML: {res.hitl_report_html_path}\n"
            f"HITL Gate 3 MD: {res.hitl_report_markdown_path}",
            title="Track A DT-02a / DT-02b & HITL Gate 3 Summary",
        )
    )
    if res.mode == "candidate":
        console.print("\n[bold yellow]HITL Gate 3 NOC Architect Verification Questions:[/bold yellow]")
        for idx, q in enumerate(res.architect_verification_questions, start=1):
            console.print(f"  {idx}. {q}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Track A DT-02a & DT-02b SOP-to-Skill Compiler (Two-Phase HITL Gate 3)."
    )
    parser.add_argument(
        "--mode",
        choices=["candidate", "approve"],
        default="candidate",
        help="Execution mode (default: candidate).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run candidate mode, prompt for approval, then run approve mode.",
    )
    parser.add_argument(
        "--update-golden-ref",
        action="store_true",
        help="In approve mode, copy skill_sop_402.yaml and guardrails_sop_402.json to data/golden_reference/.",
    )
    args = parser.parse_args()

    config = load_config(WORKSPACE_ROOT / "config.yaml")
    logger = setup_logger(config, "run_dt02_sop_skill_compiler", WORKSPACE_ROOT)
    console = Console()

    if args.interactive:
        res_cand = run_dt02_sop_skill_compiler(
            config=config,
            logger=logger,
            mode="candidate",
            update_golden_ref=False,
            root_dir=WORKSPACE_ROOT,
        )
        _print_result(console, res_cand)
        ans = input(
            "\nApprove HITL Gate 3 and materialize skills/skill_sop_402.yaml & skills/guardrails_sop_402.json? [y/N]: "
        ).strip().lower()
        if ans not in {"y", "yes"}:
            console.print("[yellow]HITL Gate 3 paused at CANDIDATE_COMPILED.[/yellow]")
            return 0
        res_app = run_dt02_sop_skill_compiler(
            config=config,
            logger=logger,
            mode="approve",
            update_golden_ref=args.update_golden_ref,
            root_dir=WORKSPACE_ROOT,
        )
        _print_result(console, res_app)
        return 0

    res = run_dt02_sop_skill_compiler(
        config=config,
        logger=logger,
        mode=args.mode,
        update_golden_ref=args.update_golden_ref,
        root_dir=WORKSPACE_ROOT,
    )
    _print_result(console, res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

