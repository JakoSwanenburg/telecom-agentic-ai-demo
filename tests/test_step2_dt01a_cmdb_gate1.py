"""
Unit Tests for Development Step 2 Refinement (`IMP-004-R1` — Scenario `DT-01a`):
  - 100% Database-Schema & Use-Case Independence in `src/track_b/s1_cmdb_tbox_profiler.py`
    (verified by source-code inspection proving zero SQLite table/column names appear in Python)
  - Reusable Knowledge Inputs (`uc001_use_case_charter.md` & `tmf_sid_etom_vocab.json`)
  - Dynamic SQLite Introspection (`PRAGMA table_info`, `PRAGMA foreign_key_list`, low-cardinality codes, samples)
  - True Two-Phase Interactive HITL Gate 1 Workflow:
    * Phase 1 (`--mode candidate`): Generates `gate1_candidate_proposal.json` + HITL report +
      Architect Verification Questions while leaving `tbox_sid_etom.ttl` and `cmdb_r2rml.ttl`
      unlocked (`SYS-01` Element 1 = `CANDIDATE_PROPOSED`, Element 2 = `UNBOUND`).
    * Phase 2 (`--mode approve`): Compiles & locks `tbox_sid_etom.ttl`, `knowledge_graph.trig`
      (`0` persisted triples in `<urn:telco:graph:virtual:ib>`), `cmdb_r2rml.ttl`, and `shapes/*.ttl`
      from `gate1_candidate_proposal.json`, transitioning `SYS-01` to `LOCKED_APPROVED` & `BOUND_ZERO_COPY`.
  - Scenario `DT-00` reset preserving `uc001_use_case_charter.md` and `tmf_sid_etom_vocab.json`
    while wiping `gate1_candidate_proposal.json` and locked semantic artifacts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import shutil
from typing import Any, Dict
import warnings

from rdflib import Dataset, Graph, RDF, URIRef
from rdflib.namespace import OWL, SKOS

from src.config_loader import get_workspace_root, load_config
from src.models import (
    AppConfig,
    CandidateOntologyAndMappingProposal,
    SqliteDatabaseIntrospection,
)
from src.state_inspector import inspect_system_state
from src.state_manager import reset_to_clean_slate
from src.track_b.s1_cmdb_tbox_profiler import (
    GRAPH_TBOX_URI,
    GRAPH_VIRTUAL_IB_URI,
    RR_NS,
    SH_NS,
    introspect_sqlite_database,
    run_dt01a_cmdb_profiler,
)


def _prepare_isolated_workspace(tmp_path: Path) -> CandidateOntologyAndMappingProposal:
    """
    Seed `tmp_path` with Stage 0 SQLite DB, `uc001_use_case_charter.md`, and
    `tmf_sid_etom_vocab.json`, and return the validated `CandidateOntologyAndMappingProposal`.
    """
    real_root = get_workspace_root()
    for rel_str in [
        "data/raw_sources/sql/cmdb_installed_base.db",
        "data/raw_sources/uc001_use_case_charter.md",
        "data/reference_standards/tmf_sid_etom_vocab.json",
        "prompts/s1_cmdb_schema_profiler_prompt.md",
    ]:
        src_file = real_root / Path(rel_str)
        dst_file = tmp_path / Path(rel_str)
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)

    proposal_file = real_root / Path("data/semantic_store/gate1_candidate_proposal.json")
    assert proposal_file.exists(), (
        "Expected Vertex AI gemini-3.8-flash candidate proposal at "
        "data/semantic_store/gate1_candidate_proposal.json"
    )
    return CandidateOntologyAndMappingProposal.model_validate_json(
        proposal_file.read_text(encoding="utf-8")
    )


def test_zero_hardcoded_table_or_column_names_in_profiler_code() -> None:
    """
    Verify that `src/track_b/s1_cmdb_tbox_profiler.py` is 100% database-schema independent
    and contains ZERO hardcoded table names or column names from `cmdb_installed_base.db`.
    """
    root = get_workspace_root()
    config = load_config()
    sqlite_path = root / Path(config.layer4_compiler_federation.sqlite_db_path)
    introspection = introspect_sqlite_database(sqlite_path)

    assert introspection.total_tables == 4
    assert introspection.total_rows == 104

    discovered_tables = {t.table_name for t in introspection.tables}
    discovered_columns = {
        c.column_name for t in introspection.tables for c in t.columns
    }
    assert len(discovered_tables) == 4
    assert len(discovered_columns) == 36

    profiler_py_path = root / Path("src/track_b/s1_cmdb_tbox_profiler.py")
    profiler_source = profiler_py_path.read_text(encoding="utf-8")

    leaked_tables = [
        tbl
        for tbl in sorted(discovered_tables)
        if re.search(rf"\b{re.escape(tbl)}\b", profiler_source)
    ]
    leaked_columns = [
        col
        for col in sorted(discovered_columns)
        if re.search(rf"\b{re.escape(col)}\b", profiler_source)
    ]

    assert leaked_tables == [], (
        f"Hardcoded SQLite table names found in s1_cmdb_tbox_profiler.py: {leaked_tables}"
    )
    assert leaked_columns == [], (
        f"Hardcoded SQLite column names found in s1_cmdb_tbox_profiler.py: {leaked_columns}"
    )


def test_reusable_knowledge_inputs_and_dynamic_sqlite_introspection() -> None:
    """
    Verify Input 1 (`uc001_use_case_charter.md`), Input 2 (`tmf_sid_etom_vocab.json` with
    30+ SID classes across all 8 domains), and dynamic SQLite introspection.
    """
    root = get_workspace_root()
    config = load_config()

    # 1. Input 1: Use Case Charter markdown
    charter_path = root / Path(config.track_b_ingestion_and_er.use_case_charter_path)
    assert charter_path.exists()
    charter_text = charter_path.read_text(encoding="utf-8")
    assert "UC-001" in charter_text
    assert "1.3.7" in charter_text
    assert "1.4.5" in charter_text

    # 2. Input 2: Generic TMF SID / eTOM / QUDT reference vocabulary JSON
    vocab_path = root / Path(config.track_b_ingestion_and_er.tmf_vocab_path)
    assert vocab_path.exists()
    vocab_data = json.loads(vocab_path.read_text(encoding="utf-8"))
    sid_classes = vocab_data.get("sid_classes", [])
    assert len(sid_classes) >= 30
    domains = {c["domain"] for c in sid_classes}
    assert {
        "Party",
        "Market_Sales",
        "Product",
        "Customer",
        "Service",
        "Resource",
        "EngagedParty",
        "Common_Business",
    }.issubset(domains)
    assert len(vocab_data.get("etom_processes", [])) >= 8
    assert len(vocab_data.get("qudt_units", [])) >= 6

    # 3. Dynamic SQLite introspection
    sqlite_path = root / Path(config.layer4_compiler_federation.sqlite_db_path)
    introspection = introspect_sqlite_database(sqlite_path)
    assert introspection.total_tables == 4
    assert introspection.total_rows == 104
    for tbl in introspection.tables:
        assert len(tbl.columns) >= 7
        assert len(tbl.sample_rows) >= 5


def test_two_phase_hitl_gate1_candidate_then_approve_and_sys01_transitions(
    tmp_path: Path,
) -> None:
    """
    Verify the complete Two-Phase HITL Gate 1 workflow:
      - Phase 1 (`mode='candidate'`): Writes `gate1_candidate_proposal.json` + HTML/MD
        review report, leaves `tbox_sid_etom.ttl` and `cmdb_r2rml.ttl` unlocked, emits
        4+ Architect Verification Questions, and sets `SYS-01` to
        `CANDIDATE_PROPOSED (Awaiting HITL Approval)` / `UNBOUND (Pending Gate 1 Lock)`.
      - Phase 2 (`mode='approve'`): Reads `gate1_candidate_proposal.json`, compiles
        and locks `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and
        `shapes/*.ttl` with zero SQL leakage, and transitions `SYS-01` to
        `LOCKED_APPROVED` / `BOUND_ZERO_COPY`.
      - `DT-00` (`reset_to_clean_slate`): Wipes `gate1_candidate_proposal.json` and
        locked artifacts while preserving `uc001_use_case_charter.md`,
        `tmf_sid_etom_vocab.json`, and `data/golden_reference/`.
    """
    cached_proposal = _prepare_isolated_workspace(tmp_path)
    config = load_config()
    logger = logging.getLogger("test_two_phase_dt01a")
    reset_to_clean_slate(config=config, logger=logger, workspace_root=tmp_path)

    def _stub_llm_generator(
        _introspection: SqliteDatabaseIntrospection,
        _charter: str,
        _vocab: Dict[str, Any],
        _cfg: AppConfig,
        _log: logging.Logger,
    ) -> CandidateOntologyAndMappingProposal:
        return cached_proposal

    # -------------------------------------------------------------------------
    # Phase 1: --mode candidate (default)
    # -------------------------------------------------------------------------
    res_candidate = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode="candidate",
        update_golden_ref=False,
        workspace_root=tmp_path,
        proposal_generator=_stub_llm_generator,
    )

    assert res_candidate.scenario_id == "DT-01a"
    assert res_candidate.gate1_mode == "candidate"
    assert res_candidate.gate1_status == "CANDIDATE_PROPOSED"
    assert res_candidate.candidate_proposal_path.exists()
    assert res_candidate.hitl_html_report_path.exists()
    assert res_candidate.hitl_markdown_report_path.exists()
    assert len(res_candidate.architect_verification_questions) >= 4

    # Crucial Phase 1 invariant: TBox, TriG, R2RML, and SHACL shapes are NOT locked yet!
    assert res_candidate.tbox_path is None
    assert res_candidate.trig_dataset_path is None
    assert res_candidate.r2rml_path is None
    assert not (tmp_path / Path(config.layer4_compiler_federation.tbox_path)).exists()
    assert not (tmp_path / Path(config.layer4_compiler_federation.r2rml_path)).exists()
    assert not (
        tmp_path / Path(config.layer4_compiler_federation.dataset_trig_path)
    ).exists()

    # Verify SYS-01 in Phase 1 (candidate)
    sys01_candidate = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert sys01_candidate.elements[0].state == "CANDIDATE_PROPOSED"
    assert (
        "HITL Gate 1: Awaiting HITL Approval"
        in sys01_candidate.elements[0].metrics_summary
    )
    assert sys01_candidate.elements[1].state == "UNBOUND"
    assert (
        "Pending Gate 1 Lock (CANDIDATE_PROPOSED)"
        in sys01_candidate.elements[1].metrics_summary
    )

    # -------------------------------------------------------------------------
    # Phase 2: --mode approve (locks TBox, TriG, R2RML, and SHACL shapes)
    # -------------------------------------------------------------------------
    res_approve = run_dt01a_cmdb_profiler(
        config=config,
        logger=logger,
        mode="approve",
        update_golden_ref=True,
        workspace_root=tmp_path,
    )

    assert res_approve.gate1_mode == "approve"
    assert res_approve.gate1_status == "LOCKED_APPROVED"
    assert res_approve.golden_ref_updated is True
    assert res_approve.evaluator_critique.overall_passed is True
    assert res_approve.evaluator_critique.zero_sql_leakage_in_tbox is True
    assert res_approve.evaluator_critique.leaked_sql_tokens == []
    assert res_approve.tbox_path is not None and res_approve.tbox_path.exists()
    assert res_approve.r2rml_path is not None and res_approve.r2rml_path.exists()
    assert (
        res_approve.trig_dataset_path is not None
        and res_approve.trig_dataset_path.exists()
    )
    assert (
        res_approve.service_spec_shape_path is not None
        and res_approve.service_spec_shape_path.exists()
    )
    assert (
        res_approve.trouble_ticket_shape_path is not None
        and res_approve.trouble_ticket_shape_path.exists()
    )

    # Verify W3C Turtle & TriG parsing in rdflib
    g_tbox = Graph()
    g_tbox.parse(str(res_approve.tbox_path), format="turtle")
    assert len(set(g_tbox.subjects(RDF.type, OWL.Class))) >= 12
    assert len(list(g_tbox.triples((None, SKOS.altLabel, None)))) >= 24

    g_r2rml = Graph()
    g_r2rml.parse(str(res_approve.r2rml_path), format="turtle")
    assert len(set(g_r2rml.subjects(RDF.type, RR_NS.TriplesMap))) == 3
    r2rml_text = res_approve.r2rml_path.read_text(encoding="utf-8")
    assert "WHERE VALID_TO_TS IS NULL" in r2rml_text

    g_spec_shape = Graph()
    g_spec_shape.parse(str(res_approve.service_spec_shape_path), format="turtle")
    assert len(set(g_spec_shape.subjects(RDF.type, SH_NS.NodeShape))) == 1

    g_ticket_shape = Graph()
    g_ticket_shape.parse(str(res_approve.trouble_ticket_shape_path), format="turtle")
    assert len(set(g_ticket_shape.subjects(RDF.type, SH_NS.NodeShape))) == 1

    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(res_approve.trig_dataset_path), format="trig")
    assert len(ds.graph(URIRef(GRAPH_TBOX_URI))) == len(g_tbox)
    assert len(ds.graph(URIRef(GRAPH_VIRTUAL_IB_URI))) == 0

    # Verify SYS-01 in Phase 2 (approved)
    sys01_approved = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert sys01_approved.elements[0].state == "LOCKED_APPROVED"
    assert "HITL Gate 1: APPROVED" in sys01_approved.elements[0].metrics_summary
    assert sys01_approved.elements[1].state == "BOUND_ZERO_COPY"

    # -------------------------------------------------------------------------
    # Reset via DT-00 and verify clean-slate preservation rules
    # -------------------------------------------------------------------------
    reset_to_clean_slate(config=config, logger=logger, workspace_root=tmp_path)

    assert not (
        tmp_path / Path(config.track_b_ingestion_and_er.gate1_candidate_proposal_path)
    ).exists()
    assert not (tmp_path / Path(config.layer4_compiler_federation.tbox_path)).exists()
    assert not (tmp_path / Path(config.layer4_compiler_federation.r2rml_path)).exists()

    # Reusable inputs and golden reference must remain preserved
    assert (
        tmp_path / Path(config.track_b_ingestion_and_er.use_case_charter_path)
    ).exists()
    assert (tmp_path / Path(config.track_b_ingestion_and_er.tmf_vocab_path)).exists()
    assert (tmp_path / Path("data/golden_reference/tbox_sid_etom.ttl")).exists()

    sys01_after_wipe = inspect_system_state(
        config=config,
        logger=logger,
        workspace_root=tmp_path,
        render_console=False,
    )
    assert sys01_after_wipe.elements[0].state == "EMPTY"
    assert sys01_after_wipe.elements[1].state == "UNBOUND"
