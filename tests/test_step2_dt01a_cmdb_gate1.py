"""
Unit Tests for Development Step 2 (`IMP-004` — Scenario `DT-01a`):
  - Dynamic SQLite CMDB Schema & Column Disposition Profiler (`PRAGMA table_info`)
  - Pruned TMF SID/eTOM Conceptual Ontology (`tbox_sid_etom.ttl`) & Zero SQL Leakage
  - Base W3C SHACL Shapes (`service_spec_shape.ttl` & `trouble_ticket_shape.ttl`)
  - Physical W3C R2RML Virtual Graph Mapping (`cmdb_r2rml.ttl`)
  - Mandatory HITL Gate 1 (`CANDIDATE_PROPOSED` vs. `LOCKED_APPROVED`) & `--update-golden-ref`
  - `SYS-01` Live State Inspector transitions (`LOCKED_APPROVED` & `BOUND_ZERO_COPY` -> `DT-00` wipe)
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
import warnings

from rdflib import Dataset, Graph, Namespace, RDF, URIRef
from rdflib.namespace import OWL, SKOS

from src.config_loader import get_workspace_root, load_config
from src.state_inspector import inspect_system_state
from src.state_manager import reset_to_clean_slate
from src.track_b.s1_cmdb_tbox_profiler import (
    GRAPH_TBOX_URI,
    GRAPH_VIRTUAL_IB_URI,
    RR_NS,
    SH_NS,
    profile_cmdb_sqlite_database,
    run_dt01a_cmdb_profiler,
)


def _prepare_isolated_workspace_with_sqlite(tmp_path: Path) -> Path:
    """Copy the frozen Stage 0 SQLite database into `tmp_path` for isolated testing."""
    real_root = get_workspace_root()
    src_sqlite = real_root / Path("data/raw_sources/sql/cmdb_installed_base.db")
    dst_sqlite = tmp_path / Path("data/raw_sources/sql/cmdb_installed_base.db")
    dst_sqlite.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_sqlite, dst_sqlite)
    return dst_sqlite


def test_dynamic_sqlite_schema_profiler_and_column_dispositions() -> None:
    """Verify dynamic `PRAGMA table_info(...)` profiling and exact column dispositions."""
    config = load_config()
    sqlite_path = get_workspace_root() / Path(
        config.layer4_compiler_federation.sqlite_db_path
    )
    table_profiles, scd2 = profile_cmdb_sqlite_database(
        sqlite_path=sqlite_path,
        target_circuit_id=config.use_case.circuit_id,
    )

    assert len(table_profiles) == 4
    assert sum(t.total_rows for t in table_profiles) == 104

    by_name = {t.table_name: t for t in table_profiles}

    # 1. T_BILLING_AUDIT_NOISE: 25 rows, all 10 columns EXCLUDED_NOISE
    noise_tbl = by_name["T_BILLING_AUDIT_NOISE"]
    assert noise_tbl.total_rows == 25
    assert noise_tbl.active_rows == 0
    assert noise_tbl.table_disposition == "EXCLUDED_NOISE"
    assert len(noise_tbl.columns) == 10
    assert all(c.disposition == "EXCLUDED_NOISE" for c in noise_tbl.columns)
    noise_col_map = {c.column_name: c for c in noise_tbl.columns}
    assert "ERP_BATCH_REF" in noise_col_map
    assert "AUDIT_HASH" in noise_col_map
    assert "ERP_BATCH_REF" in noise_col_map["ERP_BATCH_REF"].audit_rationale
    assert "AUDIT_HASH" in noise_col_map["AUDIT_HASH"].audit_rationale

    # 2. T_OSS_CUST_PARTY: 15 rows, 4 mapped + 3 EXCLUDED_INTERNAL_OR_LEGACY
    cust_tbl = by_name["T_OSS_CUST_PARTY"]
    assert cust_tbl.total_rows == 15
    assert cust_tbl.table_disposition == "BOUND_VIRTUAL_GRAPH"
    cust_cols = {c.column_name: c.disposition for c in cust_tbl.columns}
    assert cust_cols["PARTY_SURR_ID"] == "EXCLUDED_INTERNAL_OR_LEGACY"
    assert cust_cols["LEGACY_CRM_ID"] == "EXCLUDED_INTERNAL_OR_LEGACY"
    assert cust_cols["CREATED_TS"] == "EXCLUDED_INTERNAL_OR_LEGACY"
    assert cust_cols["CUST_EXT_REF"] == "MAPPED_TO_TBOX"
    assert cust_cols["LEGAL_NAME"] == "MAPPED_TO_TBOX"
    assert cust_cols["SEGMENT_CD"] == "MAPPED_TO_TBOX"
    assert cust_cols["ACCT_MGR_ID"] == "MAPPED_TO_TBOX"

    # 3. T_CMDB_CFS_CIRCUIT: 32 total rows, 25 active rows (7 expired SCD2 rows), SCD2 & legacy dispositions
    cfs_tbl = by_name["T_CMDB_CFS_CIRCUIT"]
    assert cfs_tbl.total_rows == 32
    assert cfs_tbl.active_rows == 25
    cfs_cols = {c.column_name: c.disposition for c in cfs_tbl.columns}
    assert cfs_cols["LEGACY_BILL_TAG"] == "EXCLUDED_LEGACY"
    assert cfs_cols["CFS_ROW_ID"] == "PHYSICAL_SCD2_CONTROL_ONLY"
    assert cfs_cols["VALID_FROM_TS"] == "PHYSICAL_SCD2_CONTROL_ONLY"
    assert cfs_cols["VALID_TO_TS"] == "PHYSICAL_SCD2_CONTROL_ONLY"
    assert cfs_cols["CIRCUIT_ID"] == "MAPPED_TO_TBOX"
    assert cfs_cols["OPER_STATUS_CD"] == "MAPPED_TO_TBOX"
    assert cfs_cols["BW_VAL"] == "MAPPED_TO_TBOX"
    assert cfs_cols["BW_UNIT_CD"] == "MAPPED_TO_TBOX"

    # 4. T_CMDB_RFS_RESOURCE: 32 rows, LAST_SYNC_UTC flagged EXCLUDED_SYNC_METADATA
    rfs_tbl = by_name["T_CMDB_RFS_RESOURCE"]
    assert rfs_tbl.total_rows == 32
    rfs_cols = {c.column_name: c.disposition for c in rfs_tbl.columns}
    assert rfs_cols["LAST_SYNC_UTC"] == "EXCLUDED_SYNC_METADATA"
    assert rfs_cols["RFS_ID"] == "MAPPED_TO_TBOX"
    assert rfs_cols["OLT_PORT_ID"] == "MAPPED_TO_TBOX"
    assert rfs_cols["CPE_MODEL_SKU"] == "MAPPED_TO_TBOX"

    # 5. SCD2 ground truth for CIR-994821
    assert scd2.circuit_id == "CIR-994821"
    assert scd2.expired_row_id == 2000
    assert scd2.expired_product_sku == "ETH-1G-SILVER"
    assert scd2.active_row_id == 2001
    assert scd2.active_product_sku == "ETH-10G-GOLD"
    assert scd2.raw_oper_status_cd == "10"
    assert scd2.canonical_oper_status == "ACTIVE"
    assert scd2.normalized_bandwidth_gbps == 10.0


def test_dt01a_tbox_r2rml_shapes_and_zero_sql_leakage(tmp_path: Path) -> None:
    """
    Verify `run_dt01a_cmdb_profiler` generates valid W3C Turtle/R2RML/SHACL/TriG
    artifacts with zero SQL leakage in the TBox and 0 persisted virtual triples on disk.
    """
    _prepare_isolated_workspace_with_sqlite(tmp_path)
    config = load_config()
    logger = logging.getLogger("test_dt01a_artifacts")

    result = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode="approve",
        update_golden_ref=False,
        workspace_root=tmp_path,
    )

    assert result.scenario_id == "DT-01a"
    assert result.gate1_status == "LOCKED_APPROVED"
    assert result.golden_ref_updated is False
    assert result.evaluator_critique.overall_passed is True
    assert result.evaluator_critique.zero_sql_leakage_in_tbox is True
    assert result.evaluator_critique.leaked_sql_tokens == []
    assert result.evaluator_critique.tbox_class_count == 14
    assert result.evaluator_critique.tbox_skos_alt_label_count >= 24

    # 1. Verify tbox_sid_etom.ttl parses cleanly and contains zero SQL table/column tokens
    g_tbox = Graph()
    g_tbox.parse(str(result.tbox_path), format="turtle")
    assert len(set(g_tbox.subjects(RDF.type, OWL.Class))) == 14
    assert len(list(g_tbox.triples((None, SKOS.altLabel, None)))) >= 24

    # 2. Verify cmdb_r2rml.ttl parses cleanly and contains 3 TriplesMaps + SCD2 filter
    g_r2rml = Graph()
    g_r2rml.parse(str(result.r2rml_path), format="turtle")
    triples_maps = set(g_r2rml.subjects(RDF.type, RR_NS.TriplesMap))
    assert len(triples_maps) == 3
    r2rml_text = result.r2rml_path.read_text(encoding="utf-8")
    assert "WHERE VALID_TO_TS IS NULL" in r2rml_text
    assert "CFS_ROW_ID=2001" in r2rml_text
    assert "CFS_ROW_ID=2000" in r2rml_text
    assert "T_BILLING_AUDIT_NOISE" not in "\n".join(
        str(o) for _, _, o in g_r2rml.triples((None, RR_NS.sqlQuery, None))
    )

    # 3. Verify both SHACL shape files parse cleanly in rdflib
    g_spec_shape = Graph()
    g_spec_shape.parse(str(result.service_spec_shape_path), format="turtle")
    assert len(set(g_spec_shape.subjects(RDF.type, SH_NS.NodeShape))) == 1

    g_ticket_shape = Graph()
    g_ticket_shape.parse(str(result.trouble_ticket_shape_path), format="turtle")
    assert len(set(g_ticket_shape.subjects(RDF.type, SH_NS.NodeShape))) == 1

    # 4. Verify knowledge_graph.trig has TBox triples in <urn:telco:graph:tbox:sid-etom>
    #    and 0 persisted triples in <urn:telco:graph:virtual:ib>
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(result.trig_dataset_path), format="trig")
    tbox_ctx = ds.graph(URIRef(GRAPH_TBOX_URI))
    virtual_ctx = ds.graph(URIRef(GRAPH_VIRTUAL_IB_URI))
    assert len(tbox_ctx) == len(g_tbox)
    assert len(virtual_ctx) == 0

    # 5. Verify golden_reference remained untouched by default (update_golden_ref=False)
    golden_dir = tmp_path / Path("data/golden_reference")
    assert not (golden_dir / "tbox_sid_etom.ttl").exists()


def test_dt01a_candidate_vs_approve_sys01_and_dt00_reset(tmp_path: Path) -> None:
    """
    Verify `SYS-01` transitions Element 1 to `CANDIDATE_PROPOSED` (`mode='candidate'`),
    `LOCKED_APPROVED` (`mode='approve'`), Element 2 to `BOUND_ZERO_COPY`, and returns
    to `EMPTY` / `UNBOUND` when `DT-00` (`reset_to_clean_slate`) runs. Also verify
    `update_golden_ref=True` populates `data/golden_reference/` and `DT-00` preserves it.
    """
    _prepare_isolated_workspace_with_sqlite(tmp_path)
    config = load_config()
    logger = logging.getLogger("test_dt01a_sys01_transitions")

    # Start from clean slate
    reset_to_clean_slate(config=config, logger=logger, workspace_root=tmp_path)

    # 1. Run DT-01a in candidate mode
    res_candidate = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode="candidate",
        update_golden_ref=False,
        workspace_root=tmp_path,
    )
    assert res_candidate.gate1_status == "CANDIDATE_PROPOSED"

    sys01_candidate = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert sys01_candidate.elements[0].state == "CANDIDATE_PROPOSED"
    assert "HITL Gate 1: PENDING_REVIEW" in sys01_candidate.elements[0].metrics_summary
    assert sys01_candidate.elements[1].state == "BOUND_ZERO_COPY"
    assert "Persisted triples on disk: 0" in sys01_candidate.elements[1].metrics_summary

    # 2. Run DT-01a in approve mode with update_golden_ref=True
    res_approve = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode="approve",
        update_golden_ref=True,
        workspace_root=tmp_path,
    )
    assert res_approve.gate1_status == "LOCKED_APPROVED"
    assert res_approve.golden_ref_updated is True
    assert (tmp_path / Path("data/golden_reference/tbox_sid_etom.ttl")).exists()
    assert (tmp_path / Path("data/golden_reference/cmdb_r2rml.ttl")).exists()

    sys01_approved = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert sys01_approved.elements[0].state == "LOCKED_APPROVED"
    assert "Classes: 14" in sys01_approved.elements[0].metrics_summary
    assert "HITL Gate 1: APPROVED" in sys01_approved.elements[0].metrics_summary
    assert sys01_approved.elements[1].state == "BOUND_ZERO_COPY"

    # 3. Run DT-00 reset_to_clean_slate and verify SYS-01 returns to EMPTY / UNBOUND
    #    while golden_reference remains preserved
    reset_to_clean_slate(config=config, logger=logger, workspace_root=tmp_path)
    sys01_after_wipe = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert sys01_after_wipe.elements[0].state == "EMPTY"
    assert sys01_after_wipe.elements[1].state == "UNBOUND"
    assert (tmp_path / Path("data/golden_reference/tbox_sid_etom.ttl")).exists()
