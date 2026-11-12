"""
CLI Entrypoint for Scenario `DT-01a` — Prong 1 SQL CMDB Schema Profiler,
Pruned TMF SID/eTOM TBox, Base SHACL Shapes, W3C R2RML Virtual Graph Mapping &
Mandatory Two-Phase HITL Gate 1 Sign-Off (`scripts/run_dt01a_cmdb_gate1.py`).

Usage:
  python scripts/run_dt01a_cmdb_gate1.py                                  # Default: --mode candidate
  python scripts/run_dt01a_cmdb_gate1.py --mode candidate                 # Phase 1: Generate candidate proposal & HITL report
  python scripts/run_dt01a_cmdb_gate1.py --mode approve                   # Phase 2: Lock TBox, R2RML & SHACL shapes
  python scripts/run_dt01a_cmdb_gate1.py --interactive                    # Phase 1 -> Interactive HITL prompt -> Phase 2
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
from src.models import Dt01aExecutionResult
from src.track_b.s1_cmdb_tbox_profiler import run_dt01a_cmdb_profiler


def _render_result_panel(
    console: Console, result: Dt01aExecutionResult
) -> None:
    """Render the Rich execution summary panel for `DT-01a`."""
    status_style = (
        "bold green" if result.gate1_status == "LOCKED_APPROVED" else "bold yellow"
    )
    tbox_rel = (
        result.tbox_path.relative_to(PROJECT_ROOT).as_posix()
        if result.tbox_path is not None
        else "data/semantic_store/tbox_sid_etom.ttl"
    )
    trig_rel = (
        result.trig_dataset_path.relative_to(PROJECT_ROOT).as_posix()
        if result.trig_dataset_path is not None
        else "data/semantic_store/knowledge_graph.trig"
    )
    tbox_status_line = (
        f"[bold cyan]Conceptual TBox ({tbox_rel}):[/bold cyan] "
        f"{result.evaluator_critique.tbox_class_count} OWL classes | "
        f"{result.evaluator_critique.tbox_property_count} properties | "
        f"{result.evaluator_critique.tbox_skos_alt_label_count} skos:altLabel synonyms | "
        f"SQL Leakage: 0 tokens (LOCKED)"
        if result.gate1_status == "LOCKED_APPROVED"
        else f"[bold cyan]Candidate Proposal ({result.candidate_proposal_path.relative_to(PROJECT_ROOT).as_posix()}):[/bold cyan] "
        f"{result.evaluator_critique.tbox_class_count} proposed OWL classes | "
        f"{result.evaluator_critique.tbox_property_count} properties | "
        f"{result.evaluator_critique.tbox_skos_alt_label_count} skos:altLabel synonyms | "
        f"[yellow]TBox & R2RML NOT locked yet (Awaiting HITL Gate 1 Approval)[/yellow]"
    )
    virtual_graph_line = (
        f"[bold cyan]Virtual Graph TriG ({trig_rel}):[/bold cyan] "
        f"0 persisted triples in <urn:telco:graph:virtual:ib> (BOUND_ZERO_COPY)"
        if result.gate1_status == "LOCKED_APPROVED"
        else "[bold cyan]Virtual Graph (<urn:telco:graph:virtual:ib>):[/bold cyan] "
        "[yellow]UNBOUND (Pending Gate 1 Lock)[/yellow]"
    )

    console.print(
        Panel(
            f"[bold cyan]Scenario:[/bold cyan] {result.scenario_id} — Dynamic AI Schema Profiler, TBox & R2RML Mapping\n"
            f"[bold cyan]HITL Gate 1 Status:[/bold cyan] [{status_style}]{result.gate1_status}[/{status_style}] (mode={result.gate1_mode})\n"
            f"[bold cyan]SQLite Tables Dynamically Introspected:[/bold cyan] {result.total_tables_inspected} tables ({result.total_rows_inspected} rows) — "
            f"[green]{result.bound_tables_count} bound[/green], [red]{result.excluded_noise_tables_count} excluded noise[/red]\n"
            f"[bold cyan]SCD2 & QUDT Ground Truth ({result.scd2_verification.circuit_id}):[/bold cyan] "
            f"Filtered row {result.scd2_verification.expired_row_id} ({result.scd2_verification.expired_product_sku}) | "
            f"Retained active row {result.scd2_verification.active_row_id} ({result.scd2_verification.active_product_sku}, "
            f"status='{result.scd2_verification.canonical_oper_status}', {result.scd2_verification.normalized_bandwidth_gbps} Gbps)\n"
            f"{tbox_status_line}\n"
            f"{virtual_graph_line}\n"
            f"[bold cyan]HITL Gate 1 Report:[/bold cyan] {result.hitl_html_report_path.relative_to(PROJECT_ROOT).as_posix()}\n"
            f"[bold cyan]Golden Reference Updated:[/bold cyan] {result.golden_ref_updated}",
            title=(
                "DT-01a Phase 2 Complete — HITL Gate 1 LOCKED_APPROVED"
                if result.gate1_status == "LOCKED_APPROVED"
                else "DT-01a Phase 1 Complete — CANDIDATE_PROPOSED (Awaiting HITL Gate 1 Sign-Off)"
            ),
            border_style="green" if result.gate1_status == "LOCKED_APPROVED" else "yellow",
        )
    )


def main() -> int:
    """Parse CLI arguments and run Scenario `DT-01a`."""
    parser = argparse.ArgumentParser(
        description=(
            "Scenario DT-01a: Dynamic Prong 1 SQL CMDB Schema Profiler, Pruned TMF SID/eTOM TBox, "
            "R2RML Virtual Graph Mapping & Mandatory Two-Phase HITL Gate 1 Sign-Off"
        )
    )
    parser.add_argument(
        "--mode",
        choices=["candidate", "approve"],
        default="candidate",
        help=(
            "HITL Gate 1 sign-off mode: 'candidate' (default) runs dynamic AI schema profiling "
            "and writes gate1_candidate_proposal.json + HITL review report without locking TBox/R2RML; "
            "'approve' compiles and locks tbox_sid_etom.ttl, cmdb_r2rml.ttl, and shapes/*.ttl."
        ),
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        default=False,
        help=(
            "Run Phase 1 (--mode candidate), display the HITL Gate 1 Architect Verification "
            "Questions, and interactively prompt to approve and lock Phase 2 (--mode approve)."
        ),
    )
    parser.add_argument(
        "--update-golden-ref",
        action="store_true",
        default=False,
        help=(
            "Optional flag to promote approved Step 2 artifacts (tbox_sid_etom.ttl, "
            "cmdb_r2rml.ttl, shapes/*.ttl) into data/golden_reference/ when mode=approve."
        ),
    )
    args = parser.parse_args()

    config = load_config()
    logger = setup_logger(config, logger_name="telco_agent.dt01a")
    console = Console()

    initial_mode = "candidate" if args.interactive else args.mode
    result = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode=initial_mode,
        update_golden_ref=args.update_golden_ref if initial_mode == "approve" else False,
        workspace_root=PROJECT_ROOT,
    )
    _render_result_panel(console, result)

    if result.gate1_status == "CANDIDATE_PROPOSED":
        q_lines = "\n".join(
            f"[bold yellow]{idx}.[/bold yellow] {q}"
            for idx, q in enumerate(result.architect_verification_questions, start=1)
        )
        console.print(
            Panel(
                f"{q_lines}\n\n"
                "[bold white]Review Artifact:[/bold white] "
                f"[cyan]{result.hitl_html_report_path.relative_to(PROJECT_ROOT).as_posix()}[/cyan]\n"
                "[bold white]Candidate JSON:[/bold white]  "
                f"[cyan]{result.candidate_proposal_path.relative_to(PROJECT_ROOT).as_posix()}[/cyan]\n\n"
                "[bold green]How to Approve & Lock HITL Gate 1:[/bold green]\n"
                "  • CLI Sign-Off:         [bold]python scripts/run_dt01a_cmdb_gate1.py --mode approve[/bold]\n"
                "  • Interactive Sign-Off: [bold]python scripts/run_dt01a_cmdb_gate1.py --interactive[/bold]",
                title="HITL Gate 1 — Lead Architect Verification Checklist",
                border_style="magenta",
            )
        )

        if args.interactive:
            answer = console.input(
                "\n[bold yellow]Approve and lock HITL Gate 1 ontology & R2RML mappings now? [y/N]: [/bold yellow]"
            )
            if answer.strip().lower() in {"y", "yes"}:
                approved_result = run_dt01a_cmdb_profiler(
                    config=config,
                    logger=logger,
                    mode="approve",
                    update_golden_ref=args.update_golden_ref,
                    workspace_root=PROJECT_ROOT,
                )
                _render_result_panel(console, approved_result)
            else:
                console.print(
                    "[yellow]HITL Gate 1 remains in CANDIDATE_PROPOSED state (TBox & R2RML unlocked).[/yellow]"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
