"""
Unit Tests for Step 5 (Layer 4): Deterministic R2RML-to-SQLite Pushdown Compiler,
Multi-Graph Federated Executor & 5-Challenge Resolution Proof.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import warnings

import pytest
from rdflib import Dataset, Literal, URIRef

from src.config_loader import get_workspace_root, load_config
from src.layer4.federated_executor import (
    execute_readonly_sparql,
    query_federated_circuit_context,
)
from src.layer4.r2rml_sqlite_compiler import (
    GRAPH_VIRTUAL_IB,
    compile_r2rml_to_virtual_graph,
)
from src.state_manager import reset_to_clean_slate


def _setup_isolated_workspace(tmp_path: Path) -> Path:
    """Copy approved Track B + SQLite artifacts into an isolated temp workspace."""
    repo_root = get_workspace_root()
    files_to_copy = [
        "config.yaml",
        "config/mcp_primitives_catalog.json",
        "data/raw_sources/sql/cmdb_installed_base.db",
        "data/semantic_store/tbox_sid_etom.ttl",
        "data/semantic_store/knowledge_graph.trig",
        "data/semantic_store/gate2_candidate_proposal.json",
        "mappings/cmdb_r2rml.ttl",
    ]
    for rel in files_to_copy:
        src = repo_root / rel
        if not src.exists():
            continue
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


def test_zero_hardcoded_sql_table_or_column_names_in_compiler() -> None:
    """Verify r2rml_sqlite_compiler.py contains zero hardcoded SQL table or column names."""
    source_path = (
        get_workspace_root() / "src" / "layer4" / "r2rml_sqlite_compiler.py"
    )
    source_text = source_path.read_text(encoding="utf-8")

    forbidden = [
        "T_OSS_CUST_PARTY",
        "T_CMDB_CFS_CIRCUIT",
        "T_CMDB_RFS_RESOURCE",
        "T_BILLING_AUDIT_NOISE",
        "CIRCUIT_ID",
        "CFS_ROW_ID",
        "VALID_TO_TS",
        "CPE_MODEL_SKU",
        "PROD_SPEC_CODE",
        "BANDWIDTH_GBPS",
        "ETH-1G-SILVER",
        "ETH-10G-GOLD",
        "CIR-994821",
    ]
    for literal in forbidden:
        assert literal not in source_text, (
            f"Hardcoded SQL/domain identifier '{literal}' found in r2rml_sqlite_compiler.py"
        )


def test_layer4_fails_fast_when_prerequisites_missing_or_virtual_ib_nonempty(
    tmp_path: Path,
) -> None:
    """Verify Layer 4 fails fast if Track B artifacts are missing or virtual:ib > 0 on disk."""
    config = load_config()
    logger = logging.getLogger("test_layer4_prereq")

    with pytest.raises(RuntimeError, match="prerequisite"):
        compile_r2rml_to_virtual_graph(config=config, logger=logger, root_dir=tmp_path)

    ws = _setup_isolated_workspace(tmp_path)
    trig_path = ws / config.layer4_compiler_federation.dataset_trig_path
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(trig_path), format="trig")
        ds.graph(GRAPH_VIRTUAL_IB).add(
            (URIRef("urn:test:s"), URIRef("urn:test:p"), Literal("leak"))
        )
        ds.serialize(destination=str(trig_path), format="trig")

    with pytest.raises(RuntimeError, match="Zero-Copy Invariant Violation"):
        compile_r2rml_to_virtual_graph(config=config, logger=logger, root_dir=ws)


@pytest.mark.parametrize(
    "bad_query",
    [
        "INSERT DATA { <urn:a> <urn:b> <urn:c> }",
        "DELETE WHERE { ?s ?p ?o }",
        "DROP GRAPH <urn:telco:graph:ref:catalog>",
        "CLEAR ALL",
        "LOAD <http://example.org/data.ttl>",
    ],
)
def test_readonly_sparql_rejects_mutation_keywords(bad_query: str) -> None:
    """Verify read-only SPARQL guard rejects SPARQL UPDATE mutation keywords."""
    ds = Dataset()
    with pytest.raises(ValueError, match="Read-only SPARQL guard"):
        execute_readonly_sparql(ds, bad_query)


def test_r2rml_pushdown_filters_scd2_and_projects_virtual_ib_in_memory_only(
    tmp_path: Path,
) -> None:
    """
    Verify R2RML pushdown suppresses expired SCD2 row (ETH-1G-SILVER), retains active row
    (ETH-10G-GOLD, ACTIVE, 10.0 Gbps), excludes T_BILLING_AUDIT_NOISE, and keeps disk = 0.
    """
    ws = _setup_isolated_workspace(tmp_path)
    config = load_config()
    logger = logging.getLogger("test_layer4_pushdown")

    runtime_ds, compile_res = compile_r2rml_to_virtual_graph(
        config=config, logger=logger, root_dir=ws
    )
    assert compile_res.disk_virtual_ib_triples_before == 0
    assert compile_res.in_memory_virtual_ib_triples > 0
    assert "T_BILLING_AUDIT_NOISE" in compile_res.scd2_audit.excluded_unmapped_tables
    assert "T_CMDB_CFS_CIRCUIT" in compile_res.scd2_audit.scd2_filtered_tables
    assert compile_res.scd2_audit.historical_rows_suppressed >= 1

    # Query in-memory virtual:ib for CIR-994821
    rows = execute_readonly_sparql(
        runtime_ds,
        """
        PREFIX tmf: <http://tmforum.org/sid/>
        PREFIX telco: <http://telco.enterprise.org/ontology/>
        SELECT ?spec ?status ?bw
        WHERE {
          GRAPH <urn:telco:graph:virtual:ib> {
            ?cfs tmf:serviceId "CIR-994821" ;
                 tmf:isDescribedBy ?spec ;
                 tmf:operationalStatus ?status ;
                 telco:bandwidthGbps ?bw .
          }
        }
        """,
    )
    assert len(rows) == 1
    assert str(rows[0]["spec"]) == "urn:telco:spec:service:ETH-10G-GOLD"
    assert rows[0]["status"] == "ACTIVE"
    assert float(rows[0]["bw"]) == 10.0

    # Confirm disk knowledge_graph.trig still has 0 virtual:ib triples
    trig_path = ws / config.layer4_compiler_federation.dataset_trig_path
    ds_disk = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds_disk.parse(str(trig_path), format="trig")
    assert len(ds_disk.graph(GRAPH_VIRTUAL_IB)) == 0


def test_federated_six_graph_join_and_five_challenge_proof_for_cir994821(
    tmp_path: Path,
) -> None:
    """
    Verify 6-graph federated SPARQL join for CIR-994821, 5-Challenge Proof Table,
    HTML/MD report generation, zero disk virtual:ib triples, and DT-00 cleanup.
    """
    ws = _setup_isolated_workspace(tmp_path)
    config = load_config()
    logger = logging.getLogger("test_layer4_fed")

    result = query_federated_circuit_context(
        circuit_id="CIR-994821",
        config=config,
        logger=logger,
        root_dir=ws,
    )
    ctx = result.circuit_context
    assert ctx.circuit_id == "CIR-994821"
    assert ctx.customer_id == "CUST-ENT-409"
    assert ctx.customer_name == "A Corporate Enterprise"
    assert ctx.bridged_legal_name == "A Corporate Enterprise B.V."
    assert ctx.bridged_er_confidence is not None and 0.85 <= ctx.bridged_er_confidence <= 0.95
    assert ctx.product_sku == "ETH-10G-GOLD"
    assert ctx.operational_status == "ACTIVE"
    assert ctx.bandwidth_gbps == 10.0
    assert ctx.rfs_id == "RFS-OLT04-P12"
    assert ctx.pe_router_hostname == "NLD-HAG-PE02"
    assert ctx.olt_port_id == "OLT04-P12"
    assert ctx.cpe_asset_id == "CPE-ASN-7741"
    assert ctx.cpe_model_sku == "NOK-7210-SAS-Mxp"
    assert ctx.max_packet_loss_pct == 0.1
    assert ctx.auto_remediation_allowed is True
    assert ctx.eligible_upgrade_sku == "ETH-100G-PLATINUM"
    assert ctx.rx_optical_power_min_dbm == -25.0
    assert ctx.rx_los_cut_threshold_dbm == -27.5
    assert "ACTIVE" in ctx.doc_lifecycle_statuses

    assert len(result.proof_table.entries) == 5
    assert all(e.status == "RESOLVED" for e in result.proof_table.entries)
    assert result.disk_virtual_ib_triples_after == 0
    assert result.report_html_path.exists()
    assert result.report_markdown_path.exists()

    # Verify DT-00 reset removes Step 5 proof reports
    reset_to_clean_slate(config=config, logger=logger, workspace_root=ws)
    assert not result.report_html_path.exists()
    assert not result.report_markdown_path.exists()

