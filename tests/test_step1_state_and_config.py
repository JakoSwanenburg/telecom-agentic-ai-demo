"""
Unit Tests for Development Step 1 (`IMP-003`):
  - Stage 0 Activity 0.3 Lock (`config.yaml` & `src/config_loader.py`)
  - Manifest SCD2 row ID consistency (`CFS_ROW_ID=2000` & `CFS_ROW_ID=2001`)
  - Southbound MCP Platform Primitive Catalog (`config/mcp_primitives_catalog.json` & `src/catalog_manager.py`)
  - Scenario `DT-00` Clean-Slate Wipe (`src/state_manager.py`)
  - `SYS-01` Live System State Inspector (`src/state_inspector.py`)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from rdflib import Dataset, Graph, Literal as RdfLiteral, Namespace, RDF, URIRef
from rdflib.namespace import OWL, SKOS

from src.catalog_manager import (
    get_active_protocols_for_primitive,
    load_catalog,
    set_tmf621_primitive_enabled,
)
from src.config_loader import get_workspace_root, load_config
from src.state_inspector import (
    GRAPH_BITES_HW,
    GRAPH_BITES_MSA,
    GRAPH_BRIDGE_ER,
    GRAPH_REF_CATALOG,
    TMF_NS,
    inspect_system_state,
)
from src.state_manager import load_cqrs_state, reset_to_clean_slate


def test_step1_config_loader_and_activity_03_lock() -> None:
    """Verify `load_config` validates all 7 Step 1 sections and Activity 0.3 ground truth."""
    config = load_config()

    # 1. Use case ground truth
    assert config.use_case.use_case_id == "UC-001"
    assert config.use_case.customer_name == "A Corporate Enterprise"
    assert config.use_case.customer_id == "CUST-ENT-409"
    assert config.use_case.customer_bv_name == "A Corporate Enterprise B.V."
    assert config.use_case.customer_registration_kvk == "NL-8841209"
    assert config.use_case.circuit_id == "CIR-994821"
    assert config.use_case.active_product_sku == "ETH-10G-GOLD"
    assert config.use_case.expired_product_sku == "ETH-1G-SILVER"
    assert config.use_case.cfs_expired_row_id == 2000
    assert config.use_case.cfs_active_row_id == 2001
    assert config.use_case.pe_router_hostname == "NLD-HAG-PE02"
    assert config.use_case.olt_port_id == "OLT04-P12"
    assert config.use_case.rfs_id == "RFS-OLT04-P12"
    assert config.use_case.cpe_asset_id == "CPE-ASN-7741"
    assert config.use_case.cpe_model_sku == "NOK-7210-SAS-Mxp"
    assert config.use_case.sop_id == "SOP-ASSUR-402"

    # 2. Layer 1 Orchestrator (Option 1D)
    assert config.layer1_orchestrator.option_id == "1D"
    assert config.layer1_orchestrator.transport_mode in {"in_process", "sse"}
    assert config.layer1_orchestrator.sse_port == 8000
    assert config.layer1_orchestrator.llm_model == "gemini-3.8-flash"
    assert (
        config.layer1_orchestrator.export_ai_studio_schema_path
        == "reports/ai_studio_tool_declarations.json"
    )

    # 3. Layer 2 Worker & SOP (Option 2.1D-Catalog + 2.2A)
    assert config.layer2_worker_and_sop.compiler_option_id == "2.1D-Catalog"
    assert config.layer2_worker_and_sop.runtime_option_id == "2.2A"
    assert config.layer2_worker_and_sop.active_skill_path == "skills/skill_sop_402.yaml"
    assert (
        config.layer2_worker_and_sop.active_guardrails_path
        == "skills/guardrails_sop_402.json"
    )

    # 4. Layer 3 NL2Semantics (Option 3C-Dual)
    assert config.layer3_nl2semantics.option_id == "3C-Dual"
    assert config.layer3_nl2semantics.execution_mode == "dual_comparison"

    # 5. Layer 4 Compiler & Federation (Option 4A)
    assert config.layer4_compiler_federation.option_id == "4A"
    assert (
        config.layer4_compiler_federation.dataset_trig_path
        == "data/semantic_store/knowledge_graph.trig"
    )
    assert (
        config.layer4_compiler_federation.tbox_path
        == "data/semantic_store/tbox_sid_etom.ttl"
    )
    assert (
        config.layer4_compiler_federation.r2rml_path == "mappings/cmdb_r2rml.ttl"
    )
    assert (
        config.layer4_compiler_federation.sqlite_db_path
        == "data/raw_sources/sql/cmdb_installed_base.db"
    )

    # 6. Track B Ingestion & ER (Option 5A-HITL)
    assert config.track_b_ingestion_and_er.option_id == "5A-HITL"
    assert (
        config.track_b_ingestion_and_er.use_case_charter_path
        == "data/raw_sources/uc001_use_case_charter.md"
    )
    assert (
        config.track_b_ingestion_and_er.tmf_sid_etom_vocab_path
        == "data/reference_standards/tmf_sid_etom_vocab.json"
    )
    assert (
        config.track_b_ingestion_and_er.hitl_gate1_report_path
        == "reports/hitl_gate1_ontology_mapping_review.html"
    )
    assert (
        config.track_b_ingestion_and_er.hitl_gate2_report_path
        == "reports/hitl_gate2_ingestion_er_curation.html"
    )
    assert (
        config.track_b_ingestion_and_er.shacl_quarantine_report_path
        == "reports/shacl_quarantine_report.html"
    )

    # 7. CQRS Action Plane (Option 6A-Generic)
    assert config.cqrs_action_plane.option_id == "6A-Generic"
    assert (
        config.cqrs_action_plane.state_file_path
        == "data/cqrs_state/cqrs_runtime_state.json"
    )
    assert (
        config.cqrs_action_plane.active_telemetry_preset
        == "branch_a_soft_degradation"
    )
    assert config.cqrs_action_plane.rate_limit_max_tokens == 3
    assert config.cqrs_action_plane.mutex_ttl_seconds == 60


def test_step1_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment variable overrides apply to Layer 1, Layer 3, and CQRS settings."""
    monkeypatch.setenv("LAYER1_TRANSPORT_MODE", "sse")
    monkeypatch.setenv("LAYER3_EXECUTION_MODE", "voicebox_hybrid")
    monkeypatch.setenv("CQRS_TELEMETRY_PRESET", "branch_b_hard_fiber_cut")

    config = load_config()
    assert config.layer1_orchestrator.transport_mode == "sse"
    assert config.layer3_nl2semantics.execution_mode == "voicebox_hybrid"
    assert config.cqrs_action_plane.active_telemetry_preset == "branch_b_hard_fiber_cut"


def test_stage0_manifest_scd2_row_id_consistency() -> None:
    """Verify STAGE0_ARTIFACT_MANIFEST.md matches SQLite CFS_ROW_ID=2000 & 2001."""
    manifest_path = (
        get_workspace_root()
        / Path("data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md")
    )
    assert manifest_path.exists()
    content = manifest_path.read_text(encoding="utf-8")
    assert "CFS_ROW_ID=2000" in content
    assert "CFS_ROW_ID=2001" in content
    assert "ETH-1G-SILVER" in content
    assert "ETH-10G-GOLD" in content


def test_mcp_primitives_catalog_load_and_gap_toggle(tmp_path: Path) -> None:
    """Verify loading and toggling `enable_tmf621_dispatch_primitive` in the MCP catalog."""
    config = load_config()

    # Load from workspace root first
    workspace_catalog = load_catalog(config)
    assert workspace_catalog.enable_tmf621_dispatch_primitive is True
    uris = [p.primitive_uri for p in workspace_catalog.primitives]
    assert uris == [
        "mcp://semantic-read/query_knowledge_fabric",
        "cqrs://singleton-check/probe_resource_state",
        "cqrs://transactional-write/execute_governed_mutation",
        "cqrs://transactional-write/commit_validated_graph_triples",
    ]

    # Toggle in isolated tmp_path
    catalog_gap = set_tmf621_primitive_enabled(
        enabled=False, config=config, workspace_root=tmp_path
    )
    assert catalog_gap.enable_tmf621_dispatch_primitive is False
    active_protocols_gap = get_active_protocols_for_primitive(
        catalog_gap, "cqrs://transactional-write/execute_governed_mutation"
    )
    assert active_protocols_gap == ["TMF640_SERVICE_ACTIVATION"]

    # Re-enable TMF621
    catalog_complete = set_tmf621_primitive_enabled(
        enabled=True, config=config, workspace_root=tmp_path
    )
    assert catalog_complete.enable_tmf621_dispatch_primitive is True
    active_protocols_complete = get_active_protocols_for_primitive(
        catalog_complete, "cqrs://transactional-write/execute_governed_mutation"
    )
    assert "TMF640_SERVICE_ACTIVATION" in active_protocols_complete
    assert "TMF621_TROUBLE_TICKET" in active_protocols_complete


def test_dt00_clean_slate_wipe_and_sys01_inspection(tmp_path: Path) -> None:
    """
    Verify Scenario `DT-00` wipes active semantic/skill/report artifacts while
    preserving `data/raw_sources/` and `data/golden_reference/`, and verify `SYS-01`
    reports exact states across all 7 elements.
    """
    config = load_config()
    logger = logging.getLogger("test_dt00_sys01")

    # Seed Stage 0 raw sources and golden reference in tmp_path
    raw_sql_path = tmp_path / Path("data/raw_sources/sql/cmdb_installed_base.db")
    raw_sql_path.parent.mkdir(parents=True, exist_ok=True)
    raw_sql_path.write_bytes(b"SQLITE_DUMMY_HEADER")

    golden_ref_path = tmp_path / Path("data/golden_reference/golden_tbox.ttl")
    golden_ref_path.parent.mkdir(parents=True, exist_ok=True)
    golden_ref_path.write_text("# Golden Reference TBox\n", encoding="utf-8")

    # Seed active artifacts that DT-00 must wipe
    seeded_rel_paths = [
        Path(config.layer4_compiler_federation.dataset_trig_path),
        Path(config.layer4_compiler_federation.tbox_path),
        Path(config.layer3_nl2semantics.stored_sparql_templates_path),
        Path(config.layer4_compiler_federation.r2rml_path),
        Path(config.layer4_compiler_federation.excel_rml_path),
        Path(config.layer2_worker_and_sop.active_skill_path),
        Path(config.layer2_worker_and_sop.active_guardrails_path),
        Path(config.layer2_worker_and_sop.missing_primitive_spec_path),
        Path(config.track_b_ingestion_and_er.hitl_gate1_report_path),
        Path(config.track_b_ingestion_and_er.hitl_gate2_report_path),
        Path(config.track_b_ingestion_and_er.shacl_quarantine_report_path),
        Path("shapes/b2b_sla_shape.ttl"),
    ]
    for rel in seeded_rel_paths:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("dummy content", encoding="utf-8")

    # Execute DT-00 with set_catalog_gap=True
    wipe_summary = reset_to_clean_slate(
        config=config,
        logger=logger,
        set_catalog_gap=True,
        workspace_root=tmp_path,
    )
    assert wipe_summary.scenario_id == "DT-00"
    assert wipe_summary.catalog_gap_enabled is True
    assert wipe_summary.enable_tmf621_dispatch_primitive is False
    assert wipe_summary.preserved_raw_sources_count == 1
    assert len(wipe_summary.removed_files) == len(seeded_rel_paths)

    # Verify raw sources and golden reference are untouched
    assert raw_sql_path.exists()
    assert golden_ref_path.exists()

    # Verify all seeded active artifacts were removed
    for rel in seeded_rel_paths:
        assert not (tmp_path / rel).exists()

    # Verify CQRS state reset to 0 locks and 3/3 tokens
    cqrs_state = load_cqrs_state(config, tmp_path)
    assert len(cqrs_state.active_mutex_locks) == 0
    assert cqrs_state.rate_limit_remaining_tokens == 3
    assert cqrs_state.rate_limit_max_tokens == 3

    # Run SYS-01 after DT-00 (with catalog gap enabled)
    report_gap = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert report_gap.inspector_id == "SYS-01"
    assert len(report_gap.elements) == 7
    states_gap = [el.state for el in report_gap.elements]
    assert states_gap == [
        "EMPTY",
        "UNBOUND",
        "EMPTY",
        "EMPTY",
        "PARTIAL_GAP",
        "REMOVED",
        "ACTIVE_PRESET",
    ]
    assert report_gap.html_report_path.exists()
    assert report_gap.markdown_report_path.exists()

    # Now populate artifacts in tmp_path to verify SYS-01 detects populated states
    tbox_file = tmp_path / Path(config.layer4_compiler_federation.tbox_path)
    g_tbox = Graph()
    g_tbox.add((TMF_NS.Customer, RDF.type, OWL.Class))
    g_tbox.add((TMF_NS.Customer, SKOS.altLabel, RdfLiteral("Enterprise Subscriber")))
    g_tbox.serialize(destination=str(tbox_file), format="turtle")

    r2rml_file = tmp_path / Path(config.layer4_compiler_federation.r2rml_path)
    r2rml_file.write_text("# R2RML Mapping\n", encoding="utf-8")

    gate1_file = tmp_path / Path(config.track_b_ingestion_and_er.hitl_gate1_report_path)
    gate1_file.write_text("<html>LOCKED_APPROVED</html>", encoding="utf-8")

    trig_file = tmp_path / Path(config.layer4_compiler_federation.dataset_trig_path)
    trig_content = """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix tmf: <http://tmforum.org/sid/> .

<urn:telco:graph:ref:catalog> {
    <urn:sku:ETH-10G-GOLD> rdf:type tmf:ServiceSpecification .
}

<urn:telco:graph:bites:doc-hw-v4> {
    <urn:hw:NOK-7210> rdf:type tmf:ResourceSpecification .
}

<urn:telco:graph:bites:doc-msa-v1> {
    <urn:msa:409> rdf:type tmf:ServiceLevelAgreement .
}

<urn:telco:graph:bridge:er> {
    <urn:cust:409> owl:sameAs <urn:msa:party:409> .
}
"""
    trig_file.write_text(trig_content, encoding="utf-8")

    quarantine_file = tmp_path / Path(
        config.track_b_ingestion_and_er.shacl_quarantine_report_path
    )
    quarantine_file.write_text("<html>Quarantined: 2</html>", encoding="utf-8")

    gate2_file = tmp_path / Path(config.track_b_ingestion_and_er.hitl_gate2_report_path)
    gate2_file.write_text("<html>PROMOTED</html>", encoding="utf-8")

    set_tmf621_primitive_enabled(enabled=True, config=config, workspace_root=tmp_path)

    skill_file = tmp_path / Path(config.layer2_worker_and_sop.active_skill_path)
    skill_file.write_text(
        "workflow_states:\n  S1: {}\n  S2: {}\n  S3: {}\n  S4: {}\n",
        encoding="utf-8",
    )
    guardrails_file = tmp_path / Path(
        config.layer2_worker_and_sop.active_guardrails_path
    )
    guardrails_file.write_text('{"guardrails": ["GR-PRE-01"]}', encoding="utf-8")

    report_populated = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    states_populated = [el.state for el in report_populated.elements]
    assert states_populated == [
        "LOCKED_APPROVED",
        "BOUND_ZERO_COPY",
        "LOADED_WITH_QUARANTINE",
        "PROMOTED",
        "COMPLETE",
        "DEPLOYED_MCP_READY",
        "ACTIVE_PRESET",
    ]
