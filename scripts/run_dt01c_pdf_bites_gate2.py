"""
CLI Runner for Scenario `DT-01c` — Prong 3 PDF BITES Extractor, Fuzzy Entity
Resolution (`rapidfuzz`) & Mandatory Two-Phase HITL Gate 2 Lock.

Usage:
  python scripts/run_dt01c_pdf_bites_gate2.py                     # Default: --mode candidate
  python scripts/run_dt01c_pdf_bites_gate2.py --mode candidate    # Phase 1: Generate Gate 2 curation report
  python scripts/run_dt01c_pdf_bites_gate2.py --mode approve      # Phase 2: Promote BITES, Lifecycle & ER graphs
  python scripts/run_dt01c_pdf_bites_gate2.py --interactive       # Phase 1 -> Console Prompt -> Phase 2
  python scripts/run_dt01c_pdf_bites_gate2.py --mode approve --update-golden-ref
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from rich.console import Console
from rich.panel import Panel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_config
from src.layer3.template_compiler import compile_stored_sparql_templates
from src.logger import setup_logger
from src.models import Dt01cExecutionResult
from src.track_b.s3_pdf_bites_er_ingestor import run_dt01c_pdf_bites_gate2


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for Scenario `DT-01c`."""
    parser = argparse.ArgumentParser(
        description=(
            "Scenario DT-01c: Prong 3 PDF BITES Extractor, Fuzzy Entity Resolution "
            "& Two-Phase HITL Gate 2 Lock"
        )
    )
    parser.add_argument(
        "--mode",
        choices=["candidate", "approve"],
        default="candidate",
        help="Execution phase: 'candidate' (Phase 1 curation) or 'approve' (Phase 2 promotion).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run Phase 1 (--mode candidate), prompt for HITL Gate 2 approval, and promote.",
    )
    parser.add_argument(
        "--update-golden-ref",
        action="store_true",
        help="When --mode approve, copy complete knowledge_graph.trig & excel_catalog_rml.yaml to data/golden_reference/.",
    )
    return parser.parse_args()


def _print_result(console: Console, result: Dt01cExecutionResult) -> None:
    """Print structured summary and HITL Gate 2 Verification Questions."""
    console.print(
        Panel.fit(
            f"[bold]Scenario DT-01c ({result.gate2_mode}) -> {result.gate2_status}[/bold]\n"
            f"Model: {result.model_used} | Active PDFs: {result.active_pdfs_count}\n"
            f"GLOBAL_SCOPE Triples: {result.global_scope_triples_count} | "
            f"DOCUMENT_SCOPE Triples: {result.document_scope_triples_count}\n"
            f"Doc Lifecycle Triples: {result.doc_lifecycle_triples_count} | "
            f"ER Bridge Triples: {result.er_bridge_triples_count} (ER Links: {result.er_links_count})\n"
            f"Quarantined Excel Rows: {result.quarantined_excel_rows_count} | "
            f"Virtual IB Persisted Triples: {result.virtual_ib_triples_count}\n"
            f"Candidate JSON: {result.candidate_proposal_path}\n"
            f"Gate 2 HTML   : {result.gate2_html_report_path}\n"
            f"Gate 2 MD     : {result.gate2_markdown_report_path}",
            title="HITL Gate 2 Summary",
        )
    )
    console.print("\n[bold yellow]HITL Gate 2 Verification Questions:[/bold yellow]")
    for idx, question in enumerate(result.architect_verification_questions, start=1):
        console.print(f"  {idx}. {question}")


def _compile_layer3_templates_after_approve(
    console: Console,
    config,
    logger,
    update_golden_ref: bool,
) -> None:
    """Compile Layer 3 stored SPARQL templates once Gate 2 graphs are promoted."""
    compile_res = compile_stored_sparql_templates(
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    console.print(
        f"[green]Compiled {len(compile_res.template_ids)} Layer 3 SPARQL templates[/green] -> "
        f"{compile_res.output_path}"
    )
    if update_golden_ref:
        golden_dir = PROJECT_ROOT / Path(config.track_b_ingestion_and_er.golden_reference_dir)
        golden_dir.mkdir(parents=True, exist_ok=True)
        golden_dest = golden_dir / compile_res.output_path.name
        shutil.copy2(compile_res.output_path, golden_dest)
        console.print(f"[green]Updated Golden Reference[/green] -> {golden_dest}")


def main() -> int:
    """Execute Scenario `DT-01c`."""
    args = parse_args()
    config = load_config()
    logger = setup_logger(config)
    console = Console()

    if args.interactive:
        res_cand = run_dt01c_pdf_bites_gate2(
            config=config,
            logger=logger,
            mode="candidate",
            update_golden_ref=False,
        )
        _print_result(console, res_cand)
        answer = input(
            "\nApprove HITL Gate 2 and promote BITES/Lifecycle/ER graphs to knowledge_graph.trig? [y/N]: "
        ).strip().lower()
        if answer not in {"y", "yes"}:
            console.print("[yellow]HITL Gate 2 paused at CURATION_PENDING.[/yellow]")
            return 0
        res_app = run_dt01c_pdf_bites_gate2(
            config=config,
            logger=logger,
            mode="approve",
            update_golden_ref=args.update_golden_ref,
        )
        _print_result(console, res_app)
        _compile_layer3_templates_after_approve(
            console, config, logger, args.update_golden_ref
        )
        return 0

    result = run_dt01c_pdf_bites_gate2(
        config=config,
        logger=logger,
        mode=args.mode,
        update_golden_ref=args.update_golden_ref,
    )
    _print_result(console, result)
    if args.mode == "approve":
        _compile_layer3_templates_after_approve(
            console, config, logger, args.update_golden_ref
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

