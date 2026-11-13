"""
CLI Verification Runner for Step 5 (Layer 4: Deterministic R2RML-to-SQLite
Pushdown Compiler, Multi-Graph Federated Executor & 5-Challenge Resolution Proof).

Usage:
  python scripts/run_step5_layer4_federation.py --circuit-id CIR-994821
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_config
from src.layer4.federated_executor import query_federated_circuit_context
from src.logger import setup_logger


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for Step 5 Layer 4 Federation verification."""
    parser = argparse.ArgumentParser(
        description=(
            "Step 5: Layer 4 R2RML-to-SQLite Pushdown Compiler & Federated "
            "Multi-Graph Proof Runner"
        )
    )
    parser.add_argument(
        "--circuit-id",
        default="CIR-994821",
        help="Target circuit ID to query across the 6 federated Named Graphs.",
    )
    return parser.parse_args()


def main() -> int:
    """Execute Layer 4 pushdown + federated query and print Rich audit tables."""
    args = parse_args()
    config = load_config()
    logger = setup_logger(config)
    console = Console()

    result = query_federated_circuit_context(
        circuit_id=args.circuit_id,
        config=config,
        logger=logger,
    )
    ctx = result.circuit_context
    comp = result.compile_result

    console.print(
        Panel.fit(
            f"[bold]Step 5 Layer 4 Federation Complete — Circuit {ctx.circuit_id}[/bold]\n"
            f"Customer: {ctx.customer_id} ('{ctx.customer_name}') <-> "
            f"'{ctx.bridged_legal_name or 'N/A'}' (ER={ctx.bridged_er_confidence})\n"
            f"Active CFS: {ctx.product_sku} | Status: {ctx.operational_status} | "
            f"Bandwidth: {ctx.bandwidth_gbps} Gbps\n"
            f"Topology: RFS={ctx.rfs_id} | Router={ctx.pe_router_hostname} | "
            f"Port={ctx.olt_port_id} | CPE={ctx.cpe_asset_id} ({ctx.cpe_model_sku})\n"
            f"Catalog SLA: maxPacketLossPct={ctx.max_packet_loss_pct}% | "
            f"autoRemediationAllowed={ctx.auto_remediation_allowed} | "
            f"Upgrade={ctx.eligible_upgrade_sku}\n"
            f"Optical Cutoffs: rxOpticalPowerMinDbm={ctx.rx_optical_power_min_dbm} dBm | "
            f"rxLosCutThresholdDbm={ctx.rx_los_cut_threshold_dbm} dBm\n"
            f"In-Memory virtual:ib Triples: {comp.in_memory_virtual_ib_triples} | "
            f"On-Disk virtual:ib Triples: {result.disk_virtual_ib_triples_after}\n"
            f"Report HTML: {result.report_html_path}\n"
            f"Report MD  : {result.report_markdown_path}",
            title="Layer 4 Federated Context",
        )
    )

    sql_table = Table(title="Compiled R2RML-to-SQLite Pushdown Queries")
    sql_table.add_column("TriplesMap", style="cyan")
    sql_table.add_column("Rows", justify="right")
    sql_table.add_column("Triples", justify="right")
    sql_table.add_column("Latency (ms)", justify="right")
    sql_table.add_column("Unbound Cols")
    for rec in comp.query_records:
        sql_table.add_row(
            rec.triples_map_iri.rsplit("#", 1)[-1],
            str(rec.rows_returned),
            str(rec.triples_projected),
            f"{rec.execution_latency_ms:.3f}",
            ", ".join(rec.unbound_columns_projected) or "-",
        )
    console.print(sql_table)

    proof_table = Table(title="5-Challenge Resolution Proof Table")
    proof_table.add_column("#", justify="right", style="bold")
    proof_table.add_column("Challenge", style="cyan")
    proof_table.add_column("Live Verification Evidence")
    proof_table.add_column("Status", style="green")
    for entry in result.proof_table.entries:
        proof_table.add_row(
            str(entry.challenge_number),
            entry.challenge_name,
            entry.live_verification_evidence,
            entry.status,
        )
    console.print(proof_table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

