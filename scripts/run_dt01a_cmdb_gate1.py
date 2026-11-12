"""
CLI Entrypoint for Scenario `DT-01a` — Prong 1 SQL CMDB Schema Profiler,
Pruned TMF SID/eTOM TBox, Base SHACL Shapes, W3C R2RML Virtual Graph Mapping &
Mandatory HITL Gate 1 Sign-Off (`scripts/run_dt01a_cmdb_gate1.py`).

Usage:
  python scripts/run_dt01a_cmdb_gate1.py
  python scripts/run_dt01a_cmdb_gate1.py --mode candidate
  python scripts/run_dt01a_cmdb_gate1.py --mode approve
  python scripts/run_dt01a_cmdb_gate1.py --mode approve --update-golden-ref
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from rich.console import Console
from rich.panel import Panel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_config
from src.logger import setup_logger
from src.track_b.s1_cmdb_tbox_profiler import run_dt01a_cmdb_profiler


def main() -> int:
    """Parse CLI arguments and run Scenario `DT-01a`."""
    parser = argparse.ArgumentParser(
        description=(
            "Scenario DT-01a: Prong 1 SQL CMDB Schema Profiler, Pruned TMF SID/eTOM TBox, "
            "R2RML Virtual Graph Mapping & Mandatory HITL Gate 1 Sign-Off"
        )
    )
    parser.add_argument(
        "--mode",
        choices=["candidate", "approve"],
        default="approve",
        help=(
            "HITL Gate 1 sign-off mode: 'candidate' sets status to CANDIDATE_PROPOSED; "
            "'approve' (default) locks status as LOCKED_APPROVED."
        ),
    )
    parser.add_argument(
        "--update-golden-ref",
        action="store_true",
        default=False,
        help=(
            "Optional flag to promote approved Step 2 artifacts (tbox_sid_etom.ttl, "
            "cmdb_r2rml.ttl, shapes/*.ttl) into data/golden_reference/."
        ),
    )
    args = parser.parse_args()

    config = load_config()
    logger = setup_logger(config, logger_name="telco_agent.dt01a")

    result = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode=args.mode,
        update_golden_ref=args.update_golden_ref,
        workspace_root=PROJECT_ROOT,
    )

    console = Console()
    status_style = (
        "bold green" if result.gate1_status == "LOCKED_APPROVED" else "bold yellow"
    )
    console.print(
        Panel(
            f"[bold cyan]Scenario:[/bold cyan] {result.scenario_id} — Prong 1 SQL CMDB Profiler, TBox & R2RML Mapping\n"
            f"[bold cyan]HITL Gate 1 Status:[/bold cyan] [{status_style}]{result.gate1_status}[/{status_style}] (mode={result.gate1_mode})\n"
            f"[bold cyan]SQLite Tables Profiled:[/bold cyan] {result.total_tables_inspected} tables ({result.total_rows_inspected} rows) — "
            f"[green]{result.bound_tables_count} bound[/green], [red]{result.excluded_noise_tables_count} excluded noise (T_BILLING_AUDIT_NOISE)[/red]\n"
            f"[bold cyan]SCD2 & QUDT Ground Truth ({result.scd2_verification.circuit_id}):[/bold cyan] "
            f"Filtered row {result.scd2_verification.expired_row_id} ({result.scd2_verification.expired_product_sku}) | "
            f"Retained active row {result.scd2_verification.active_row_id} ({result.scd2_verification.active_product_sku}, "
            f"status='{result.scd2_verification.canonical_oper_status}', {result.scd2_verification.normalized_bandwidth_gbps} Gbps)\n"
            f"[bold cyan]Conceptual TBox ({result.tbox_path.relative_to(PROJECT_ROOT).as_posix()}):[/bold cyan] "
            f"{result.evaluator_critique.tbox_class_count} OWL classes | "
            f"{result.evaluator_critique.tbox_property_count} properties | "
            f"{result.evaluator_critique.tbox_skos_alt_label_count} skos:altLabel synonyms | "
            f"SQL Leakage: 0 tokens\n"
            f"[bold cyan]Virtual Graph TriG ({result.trig_dataset_path.relative_to(PROJECT_ROOT).as_posix()}):[/bold cyan] "
            f"0 persisted triples in <urn:telco:graph:virtual:ib> (Zero-Copy Virtualization)\n"
            f"[bold cyan]HITL Gate 1 Report:[/bold cyan] {result.hitl_html_report_path.relative_to(PROJECT_ROOT).as_posix()}\n"
            f"[bold cyan]Golden Reference Updated:[/bold cyan] {result.golden_ref_updated}",
            title="DT-01a Prong 1 SQL CMDB & HITL Gate 1 Complete",
            border_style="green" if result.gate1_status == "LOCKED_APPROVED" else "yellow",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

