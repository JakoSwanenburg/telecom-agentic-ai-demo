"""
Step 9 (IMP-011) CLI Runner: Layer 2 Skill-Governed Assurance Specialist Agent (`RT-01`, `RT-02`, `RT-03`).

Executes Branch A (`RT-01`), Branch B (`RT-02`), and Branch C (`RT-03`) through
`run_layer2_assurance_workflow`, prints Rich SOP state machine traces, LLM orchestration
decisions, guardrail interception proofs, and pySHACL ticket outcomes, and writes
`reports/rt01_rt03_layer2_execution_report.html` (`.md`).
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import Dict, List, Literal

from rich.console import Console
from rich.table import Table

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.layer2.assurance_specialist_agent import run_layer2_assurance_workflow
from src.logger import setup_logger
from src.mcp_servers.common import resolve_ticket_journal_path, utc_now_iso
from src.models import Layer2ExecutionResult, Step9BranchReportSummary
from src.state_manager import initialize_cqrs_state

_SCENARIO_TO_PRESET: Dict[
    str,
    Literal[
        "branch_a_soft_degradation",
        "branch_b_hard_fiber_cut",
        "branch_c_maintenance_lock",
    ],
] = {
    "RT-01": "branch_a_soft_degradation",
    "RT-02": "branch_b_hard_fiber_cut",
    "RT-03": "branch_c_maintenance_lock",
}


def _write_reports(
    summary: Step9BranchReportSummary, html_path: Path, md_path: Path
) -> None:
    """Write Step 9 Layer 2 execution report in Markdown and HTML."""
    html_path.parent.mkdir(parents=True, exist_ok=True)

    md_lines = [
        "# Step 9 (`IMP-011`) Layer 2 Assurance Specialist Execution Report (`RT-01` .. `RT-03`)",
        "",
        f"- **Generated At (UTC):** `{summary.generated_at_utc}`",
        f"- **Scenarios Executed:** `{', '.join(summary.scenarios_executed)}`",
        f"- **CQRS State Reset After Run:** `{summary.state_reset_at_end}`",
        "",
        "## 1. Branch Execution Summary",
        "",
        "| Scenario | Preset | Selected Branch | TMF640 Calls | Blocking Guardrails | TMF621 Ticket | SHACL Conforms |",
        "| :--- | :--- | :--- | :---: | :--- | :--- | :---: |",
    ]
    for r in summary.results:
        tkt = r.tmf621_response.ticket
        tkt_label = f"{tkt.ticket_id} ({tkt.severity} / {tkt.status})" if tkt else "NONE"
        blocks = ", ".join(r.pre_guardrail_decision.blocking_guardrail_ids) or "NONE"
        md_lines.append(
            f"| `{r.scenario_id}` | `{r.telemetry_preset}` | `{r.selected_branch}` | "
            f"`{r.tmf640_invocations_count}` | `{blocks}` | `{tkt_label}` | "
            f"`{r.tmf621_response.shacl_conforms}` |"
        )

    for r in summary.results:
        md_lines.extend(
            [
                "",
                f"## Scenario `{r.scenario_id}` (`{r.telemetry_preset}`)",
                f"- **LLM Model:** `{r.model_used}`",
                f"- **LLM Proposed Branch / Recalibration:** `{r.llm_proposal.proposed_branch}` / `{r.llm_proposal.proposed_recalibration}`",
                f"- **Pre-Execution Guardrails:** `remediation_allowed={r.pre_guardrail_decision.remediation_allowed}`, `blocking={r.pre_guardrail_decision.blocking_guardrail_ids}`",
                f"- **Grounded Root-Cause Summary:** {r.llm_proposal.engineering_root_cause_summary}",
                "",
                "| Step # | Step ID | Catalog Primitive URI | Concrete MCP Tool | Status | Detail |",
                "| :---: | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for tr in r.step_traces:
            md_lines.append(
                f"| `{tr.step_number}` | `{tr.step_id}` | `{tr.catalog_primitive_uri}` | `{tr.concrete_mcp_tool}` | `{tr.status}` | {tr.detail} |"
            )

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    summary_rows = "\n".join(
        f"<tr><td><code>{html.escape(r.scenario_id)}</code></td>"
        f"<td><code>{html.escape(r.telemetry_preset)}</code></td>"
        f"<td><code>{html.escape(r.selected_branch)}</code></td>"
        f"<td><code>{r.tmf640_invocations_count}</code></td>"
        f"<td><code>{html.escape(', '.join(r.pre_guardrail_decision.blocking_guardrail_ids) or 'NONE')}</code></td>"
        f"<td><code>{html.escape(r.tmf621_response.ticket.ticket_id + ' (' + r.tmf621_response.ticket.severity + '/' + r.tmf621_response.ticket.status + ')' if r.tmf621_response.ticket else 'NONE')}</code></td>"
        f"<td><code>{r.tmf621_response.shacl_conforms}</code></td></tr>"
        for r in summary.results
    )

    detail_sections = []
    for r in summary.results:
        trace_rows = "\n".join(
            f"<tr><td>{tr.step_number}</td><td><code>{html.escape(tr.step_id)}</code></td>"
            f"<td><code>{html.escape(tr.catalog_primitive_uri)}</code></td>"
            f"<td><code>{html.escape(tr.concrete_mcp_tool)}</code></td>"
            f"<td><strong>{html.escape(tr.status)}</strong></td>"
            f"<td>{html.escape(tr.detail)}</td></tr>"
            for tr in r.step_traces
        )
        detail_sections.append(
            f"<h2>Scenario {html.escape(r.scenario_id)} (<code>{html.escape(r.telemetry_preset)}</code>)</h2>"
            f"<p><strong>LLM Model:</strong> <code>{html.escape(r.model_used)}</code> | "
            f"<strong>Proposed Branch:</strong> <code>{html.escape(r.llm_proposal.proposed_branch)}</code> | "
            f"<strong>Guardrail Remediation Allowed:</strong> <code>{r.pre_guardrail_decision.remediation_allowed}</code></p>"
            f"<p><strong>Grounded Root-Cause Summary:</strong> {html.escape(r.llm_proposal.engineering_root_cause_summary)}</p>"
            f"<table><thead><tr><th>#</th><th>Step ID</th><th>Catalog URI</th><th>Concrete MCP Tool</th><th>Status</th><th>Detail</th></tr></thead>"
            f"<tbody>{trace_rows}</tbody></table>"
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Step 9 (IMP-011) Layer 2 Assurance Specialist Report</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #111827; }}
    h1, h2 {{ margin-top: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 0.75rem; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.5rem 0.75rem; text-align: left; font-size: 0.9rem; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>Step 9 (IMP-011) Layer 2 Assurance Specialist Execution Report (RT-01 .. RT-03)</h1>
  <p><strong>Generated At (UTC):</strong> <code>{html.escape(summary.generated_at_utc)}</code> |
     <strong>Scenarios:</strong> <code>{html.escape(', '.join(summary.scenarios_executed))}</code> |
     <strong>CQRS State Reset:</strong> <code>{summary.state_reset_at_end}</code></p>
  <table>
    <thead>
      <tr><th>Scenario</th><th>Preset</th><th>Selected Branch</th><th>TMF640 Calls</th><th>Blocking Guardrails</th><th>TMF621 Ticket</th><th>SHACL Conforms</th></tr>
    </thead>
    <tbody>{summary_rows}</tbody>
  </table>
  {''.join(detail_sections)}
</body>
</html>
"""
    html_path.write_text(html_doc, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Step 9 Layer 2 Skill-Governed Assurance Specialist scenarios (RT-01..RT-03)."
    )
    parser.add_argument(
        "--scenario",
        choices=["RT-01", "RT-02", "RT-03", "all"],
        default="all",
        help="Scenario(s) to execute (default: all).",
    )
    parser.add_argument(
        "--circuit-id",
        default="CIR-994821",
        help="Target circuit ID (default: CIR-994821).",
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="Keep CQRS runtime state and ticket journal after completion.",
    )
    args = parser.parse_args()

    config = load_config(PROJECT_ROOT / "config.yaml")
    logger = setup_logger(
        config, logger_name="telco_agent.step9_runner", workspace_root=PROJECT_ROOT
    )
    console = Console()

    scenarios = (
        ["RT-01", "RT-02", "RT-03"] if args.scenario == "all" else [args.scenario]
    )
    journal_path = resolve_ticket_journal_path(config, PROJECT_ROOT)
    if journal_path.exists():
        journal_path.unlink()

    results: List[Layer2ExecutionResult] = []
    for sc in scenarios:
        preset = _SCENARIO_TO_PRESET[sc]
        res = run_layer2_assurance_workflow(
            circuit_id=args.circuit_id,
            telemetry_preset=preset,
            config=config,
            logger=logger,
            root_dir=PROJECT_ROOT,
        )
        results.append(res)

        trace_tbl = Table(title=f"{sc} ({preset}) — SOP-ASSUR-402 Execution Trace")
        trace_tbl.add_column("Step #", style="cyan")
        trace_tbl.add_column("Step ID", style="magenta")
        trace_tbl.add_column("Concrete MCP Tool", style="blue")
        trace_tbl.add_column("Status", style="green")
        trace_tbl.add_column("Detail")
        for tr in res.step_traces:
            trace_tbl.add_row(
                str(tr.step_number),
                tr.step_id,
                tr.concrete_mcp_tool,
                tr.status,
                tr.detail,
            )
        console.print(trace_tbl)
        console.print(
            f"[bold]{sc} Narrative:[/bold] {res.llm_proposal.engineering_root_cause_summary}\n"
        )

    if not args.keep_state:
        initialize_cqrs_state(config, PROJECT_ROOT)
        if journal_path.exists():
            journal_path.unlink()

    html_path = PROJECT_ROOT / Path(
        config.layer2_worker_and_sop.runtime_branches_report_path
    )
    md_path = html_path.with_suffix(".md")
    summary = Step9BranchReportSummary(
        generated_at_utc=utc_now_iso(),
        scenarios_executed=scenarios,
        state_reset_at_end=not args.keep_state,
        report_html_path=html_path,
        report_markdown_path=md_path,
        results=results,
    )
    _write_reports(summary, html_path, md_path)
    console.print(
        f"[bold green]Step 9 complete[/bold green] | Scenarios: {', '.join(scenarios)} | Report: {html_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

