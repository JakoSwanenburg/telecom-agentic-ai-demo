"""
Step 8 (IMP-010) Verification Runner: Southbound Operational Telemetry & CQRS Write MCP Servers.

Exercises `gnmi_telemetry_mcp`, `tmf640_activation_mcp`, and `tmf621_trouble_ticket_mcp`
across all 3 telemetry presets (`branch_a_soft_degradation`, `branch_b_hard_fiber_cut`,
`branch_c_maintenance_lock`) plus negative `pySHACL` rejection tests, writes
`reports/step8_mcp_cqrs_verification_report.html` (`.md`), and resets `data/cqrs_state/`
unless `--keep-state` is passed.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import List

from rich.console import Console
from rich.table import Table

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.logger import setup_logger
from src.mcp_servers.common import (
    resolve_ticket_journal_path,
    save_cqrs_state,
    utc_now_iso,
)
from src.mcp_servers.gnmi_telemetry_mcp import execute_probe_optical_ddm_telemetry
from src.mcp_servers.tmf621_trouble_ticket_mcp import execute_create_or_update_trouble_ticket
from src.mcp_servers.tmf640_activation_mcp import execute_recalibrate_optical_ddm_bias
from src.models import Step8VerificationCheck, Step8VerificationSummary
from src.state_manager import initialize_cqrs_state, load_cqrs_state


def _write_verification_reports(
    summary: Step8VerificationSummary,
    html_path: Path,
    md_path: Path,
) -> None:
    """Write Step 8 MCP & CQRS verification report in Markdown and HTML."""
    html_path.parent.mkdir(parents=True, exist_ok=True)

    md_lines = [
        "# Step 8 (`IMP-010`) Southbound MCP & CQRS Verification Report",
        "",
        f"- **Generated At (UTC):** `{summary.generated_at_utc}`",
        f"- **Checks Passed:** `{summary.passed_checks}/{summary.total_checks}`",
        f"- **CQRS State Reset After Verification:** `{summary.state_reset_at_end}`",
        "",
        "| Check ID | Preset | Server | Result | Detail |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for chk in summary.checks:
        status_str = "PASS" if chk.passed else "FAIL"
        md_lines.append(
            f"| `{chk.check_id}` | `{chk.preset}` | `{chk.server}` | **{status_str}** | {chk.detail} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    rows_html = "\n".join(
        f"<tr><td><code>{html.escape(c.check_id)}</code></td>"
        f"<td><code>{html.escape(c.preset)}</code></td>"
        f"<td><code>{html.escape(c.server)}</code></td>"
        f"<td><strong>{'PASS' if c.passed else 'FAIL'}</strong></td>"
        f"<td>{html.escape(c.detail)}</td></tr>"
        for c in summary.checks
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Step 8 (IMP-010) Southbound MCP &amp; CQRS Verification</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #111827; }}
    h1 {{ margin-bottom: 0.25rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #d1d5db; padding: 0.5rem 0.75rem; text-align: left; font-size: 0.92rem; }}
    th {{ background: #f3f4f6; }}
  </style>
</head>
<body>
  <h1>Step 8 (IMP-010) Southbound MCP &amp; CQRS Verification Report</h1>
  <p><strong>Generated At (UTC):</strong> <code>{html.escape(summary.generated_at_utc)}</code> |
     <strong>Checks Passed:</strong> <code>{summary.passed_checks}/{summary.total_checks}</code> |
     <strong>CQRS State Reset:</strong> <code>{summary.state_reset_at_end}</code></p>
  <table>
    <thead>
      <tr><th>Check ID</th><th>Preset</th><th>Server</th><th>Result</th><th>Detail</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
    html_path.write_text(html_doc, encoding="utf-8")


def run_verification(keep_state: bool = False) -> Step8VerificationSummary:
    """Execute end-to-end verification across all 3 southbound MCP servers."""
    config = load_config(PROJECT_ROOT / "config.yaml")
    logger = setup_logger(config, logger_name="telco_agent.step8_verify", workspace_root=PROJECT_ROOT)
    checks: List[Step8VerificationCheck] = []

    circuit_id = "CIR-994821"
    olt_port_id = "OLT04-P12"
    cpe_device_id = "CPE-ASN-7741"
    customer_id = "CUST-ENT-409"

    # Start from clean CQRS baseline
    initialize_cqrs_state(config, PROJECT_ROOT)
    journal_path = resolve_ticket_journal_path(config, PROJECT_ROOT)
    if journal_path.exists():
        journal_path.unlink()

    # 1. Branch A: Soft Degradation -> Recalibration -> Post-Check -> RESOLVED_AUTO ticket -> pySHACL negative
    pre_a = execute_probe_optical_ddm_telemetry(
        circuit_id=circuit_id, olt_port_id=olt_port_id, uncached=True, config=config, logger=logger, root_dir=PROJECT_ROOT
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-A1-GNMI-PRE",
            preset="branch_a_soft_degradation",
            server="gnmi_telemetry_mcp",
            passed=(pre_a["rx_power_dbm"] == -26.1 and pre_a["post_recalibration_verified"] is False),
            detail=f"rx_dbm={pre_a['rx_power_dbm']}, loss={pre_a['packet_loss_pct']}%, post_recal={pre_a['post_recalibration_verified']}",
        )
    )

    act_a = execute_recalibrate_optical_ddm_bias(
        circuit_id=circuit_id,
        olt_port_id=olt_port_id,
        cpe_device_id=cpe_device_id,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-A2-TMF640-EXEC",
            preset="branch_a_soft_degradation",
            server="tmf640_activation_mcp",
            passed=(act_a["executed"] is True and act_a["status"] == "EXECUTED"),
            detail=f"status={act_a['status']}, activations={act_a['tmf640_activations_count']}",
        )
    )

    post_a = execute_probe_optical_ddm_telemetry(
        circuit_id=circuit_id, olt_port_id=olt_port_id, uncached=True, config=config, logger=logger, root_dir=PROJECT_ROOT
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-A3-GNMI-POST",
            preset="branch_a_soft_degradation",
            server="gnmi_telemetry_mcp",
            passed=(
                post_a["rx_power_dbm"] == -21.4
                and post_a["packet_loss_pct"] == 0.01
                and post_a["post_recalibration_verified"] is True
            ),
            detail=f"rx_dbm={post_a['rx_power_dbm']}, loss={post_a['packet_loss_pct']}%, post_recal={post_a['post_recalibration_verified']}",
        )
    )

    tkt_a = execute_create_or_update_trouble_ticket(
        circuit_id=circuit_id,
        customer_id=customer_id,
        severity="MINOR",
        status="RESOLVED_AUTO",
        resolution_action="TMF640_DDM_BIAS_RECALIBRATION",
        summary="Soft attenuation resolved; Rx power restored to -21.4 dBm.",
        affected_resource_id=olt_port_id,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-A4-TMF621-VALID",
            preset="branch_a_soft_degradation",
            server="tmf621_trouble_ticket_mcp",
            passed=(tkt_a["persisted"] is True and tkt_a["shacl_conforms"] is True),
            detail=f"status={tkt_a['status']}, shacl_conforms={tkt_a['shacl_conforms']}",
        )
    )

    tkt_neg = execute_create_or_update_trouble_ticket(
        circuit_id=circuit_id,
        customer_id=customer_id,
        severity="INVALID_SEV",
        status="RESOLVED_AUTO",
        resolution_action="NONE",
        summary="Negative pySHACL test with invalid severity and missing affected_resource_id.",
        affected_resource_id=None,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-A5-TMF621-SHACL-REJECT",
            preset="branch_a_soft_degradation",
            server="tmf621_trouble_ticket_mcp",
            passed=(
                tkt_neg["persisted"] is False
                and tkt_neg["status"] == "REJECTED_SHACL_VIOLATION"
                and tkt_neg["shacl_conforms"] is False
            ),
            detail=f"status={tkt_neg['status']}, persisted={tkt_neg['persisted']}, shacl_conforms={tkt_neg['shacl_conforms']}",
        )
    )

    # 2. Branch B: Hard Fiber Cut
    state_b = load_cqrs_state(config, PROJECT_ROOT).model_copy(
        update={"active_telemetry_preset": "branch_b_hard_fiber_cut"}
    )
    save_cqrs_state(state_b, config, PROJECT_ROOT)

    probe_b = execute_probe_optical_ddm_telemetry(
        circuit_id=circuit_id, olt_port_id=olt_port_id, uncached=True, config=config, logger=logger, root_dir=PROJECT_ROOT
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-B1-GNMI-LOS",
            preset="branch_b_hard_fiber_cut",
            server="gnmi_telemetry_mcp",
            passed=(probe_b["rx_power_dbm"] == -38.5 and probe_b["los_alarm_active"] is True),
            detail=f"rx_dbm={probe_b['rx_power_dbm']}, loss={probe_b['packet_loss_pct']}%, los_alarm={probe_b['los_alarm_active']}",
        )
    )

    act_b = execute_recalibrate_optical_ddm_bias(
        circuit_id=circuit_id,
        olt_port_id=olt_port_id,
        cpe_device_id=cpe_device_id,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-B2-TMF640-INTERLOCK",
            preset="branch_b_hard_fiber_cut",
            server="tmf640_activation_mcp",
            passed=(
                act_b["executed"] is False
                and act_b["status"] == "REJECTED_SAFETY_INTERLOCK"
                and act_b["reason_code"] == "LOS_CRITICAL_CUTOFF_ACTIVE"
            ),
            detail=f"status={act_b['status']}, reason_code={act_b['reason_code']}",
        )
    )

    tkt_b = execute_create_or_update_trouble_ticket(
        circuit_id=circuit_id,
        customer_id=customer_id,
        severity="CRITICAL",
        status="P1_CRITICAL_FIELD_DISPATCH",
        resolution_action="DISPATCH_FIELD_ENGINEER_OTDR",
        summary="Hard fiber cut (-38.5 dBm LOS); dispatched field engineer.",
        affected_resource_id=olt_port_id,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-B3-TMF621-P1",
            preset="branch_b_hard_fiber_cut",
            server="tmf621_trouble_ticket_mcp",
            passed=(tkt_b["persisted"] is True and tkt_b["shacl_conforms"] is True),
            detail=f"status={tkt_b['status']}, shacl_conforms={tkt_b['shacl_conforms']}",
        )
    )

    # 3. Branch C: Maintenance Lock
    state_c = load_cqrs_state(config, PROJECT_ROOT).model_copy(
        update={"active_telemetry_preset": "branch_c_maintenance_lock"}
    )
    save_cqrs_state(state_c, config, PROJECT_ROOT)

    probe_c = execute_probe_optical_ddm_telemetry(
        circuit_id=circuit_id, olt_port_id=olt_port_id, uncached=True, config=config, logger=logger, root_dir=PROJECT_ROOT
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-C1-GNMI-LOCK",
            preset="branch_c_maintenance_lock",
            server="gnmi_telemetry_mcp",
            passed=(probe_c["maintenance_lock"] is True and probe_c["active_crq_id"] == "MAINT-CRQ-88210"),
            detail=f"maintenance_lock={probe_c['maintenance_lock']}, crq={probe_c['active_crq_id']}",
        )
    )

    act_c = execute_recalibrate_optical_ddm_bias(
        circuit_id=circuit_id,
        olt_port_id=olt_port_id,
        cpe_device_id=cpe_device_id,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-C2-TMF640-INTERLOCK",
            preset="branch_c_maintenance_lock",
            server="tmf640_activation_mcp",
            passed=(
                act_c["executed"] is False
                and act_c["status"] == "REJECTED_SAFETY_INTERLOCK"
                and act_c["reason_code"] == "MAINTENANCE_WINDOW_LOCK_ACTIVE"
            ),
            detail=f"status={act_c['status']}, reason_code={act_c['reason_code']}",
        )
    )

    tkt_c = execute_create_or_update_trouble_ticket(
        circuit_id=circuit_id,
        customer_id=customer_id,
        severity="WARNING",
        status="DEFERRED_MAINTENANCE_LOCK",
        resolution_action="DEFER_UNDER_MAINT_CRQ_88210",
        summary="Active maintenance lock MAINT-CRQ-88210; remediation deferred.",
        affected_resource_id=olt_port_id,
        config=config,
        logger=logger,
        root_dir=PROJECT_ROOT,
    )
    checks.append(
        Step8VerificationCheck(
            check_id="CHK-C3-TMF621-DEFERRED",
            preset="branch_c_maintenance_lock",
            server="tmf621_trouble_ticket_mcp",
            passed=(tkt_c["persisted"] is True and tkt_c["shacl_conforms"] is True),
            detail=f"status={tkt_c['status']}, shacl_conforms={tkt_c['shacl_conforms']}",
        )
    )

    if not keep_state:
        initialize_cqrs_state(config, PROJECT_ROOT)
        if journal_path.exists():
            journal_path.unlink()

    html_path = PROJECT_ROOT / Path(config.cqrs_action_plane.step8_verification_report_path)
    md_path = html_path.with_suffix(".md")
    summary = Step8VerificationSummary(
        generated_at_utc=utc_now_iso(),
        total_checks=len(checks),
        passed_checks=sum(1 for c in checks if c.passed),
        state_reset_at_end=not keep_state,
        report_html_path=html_path,
        report_markdown_path=md_path,
        checks=checks,
    )
    _write_verification_reports(summary, html_path, md_path)

    if summary.passed_checks != summary.total_checks:
        raise RuntimeError(
            f"Step 8 MCP verification failed: {summary.passed_checks}/{summary.total_checks} checks passed."
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Step 8 Southbound Operational Telemetry & CQRS MCP Servers."
    )
    parser.add_argument(
        "--keep-state",
        action="store_true",
        help="Keep CQRS runtime state and TMF621 ticket journal after verification instead of resetting.",
    )
    args = parser.parse_args()

    summary = run_verification(keep_state=args.keep_state)
    console = Console()
    table = Table(title="Step 8 (IMP-010) Southbound MCP & CQRS Verification")
    table.add_column("Check ID", style="cyan")
    table.add_column("Preset", style="magenta")
    table.add_column("Server", style="blue")
    table.add_column("Result", style="green")
    table.add_column("Detail")
    for chk in summary.checks:
        table.add_row(
            chk.check_id,
            chk.preset,
            chk.server,
            "PASS" if chk.passed else "FAIL",
            chk.detail,
        )
    console.print(table)
    console.print(
        f"[bold green]Passed {summary.passed_checks}/{summary.total_checks} checks[/bold green] | "
        f"State Reset: {summary.state_reset_at_end} | Report: {summary.report_html_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
