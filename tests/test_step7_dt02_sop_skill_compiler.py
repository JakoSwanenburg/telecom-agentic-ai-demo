"""
Unit Tests for Step 7 (Track A — DT-02a & DT-02b):
100% Document-Independent SOP-to-Skill Compiler, Adverse Guardrail Rejection
Test Harness, and Two-Phase Mandatory HITL Gate 3 Lock.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.catalog_manager import set_tmf621_primitive_enabled
from src.config_loader import load_config
from src.models import (
    CompiledGuardrailsSpec,
    CompiledSkillSpec,
    CompiledSopSkillProposal,
    MachineGuardrailRule,
    SkillBranchRule,
    SkillWorkflowStep,
    SopProcedureAssessment,
)
from src.state_inspector import inspect_system_state
from src.state_manager import reset_to_clean_slate
from src.track_a.sop_to_skill_compiler import run_dt02_sop_skill_compiler

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def _setup_track_a_workspace(tmp_path: Path) -> Path:
    """Create an isolated workspace copy with DT-01a..c outputs + SOP + Catalog."""
    for rel_dir in (
        "data/semantic_store",
        "data/raw_sources/sop",
        "data/cqrs_state",
        "data/golden_reference",
        "config",
        "prompts",
        "skills",
        "reports",
        "logs",
        "mappings",
        "shapes",
    ):
        (tmp_path / rel_dir).mkdir(parents=True, exist_ok=True)

    for rel_file in (
        "config.yaml",
        "data/semantic_store/tbox_sid_etom.ttl",
        "data/semantic_store/knowledge_graph.trig",
        "data/raw_sources/uc001_use_case_charter.md",
        "data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.md",
        "config/mcp_primitives_catalog.json",
        "prompts/track_a_sop_compiler_prompt.md",
    ):
        shutil.copy2(WORKSPACE_ROOT / rel_file, tmp_path / rel_file)

    return tmp_path


def _sample_sop_proposal() -> CompiledSopSkillProposal:
    """Return a valid CompiledSopSkillProposal matching SOP-ASSUR-402."""
    return CompiledSopSkillProposal(
        procedure_assessments=[
            SopProcedureAssessment(
                section_heading="Section 1: Purpose, General NOC Safety & Change Control Governance",
                procedure_id="GOV-NOC-001",
                relevance_score=0.5,
                disposition="GOVERNANCE_CONTEXT",
                rationale="General safety invariants apply across all procedures.",
            ),
            SopProcedureAssessment(
                section_heading="Section 2 (SOP-ASSUR-101): BGP Peering Session Flap Triage & Dampening",
                procedure_id="SOP-ASSUR-101",
                relevance_score=0.05,
                disposition="OUT_OF_SCOPE_PRUNED",
                rationale="IP Core eBGP routing flap is out of scope for UC-001 L2 fiber assurance.",
            ),
            SopProcedureAssessment(
                section_heading="Section 5 (SOP-ASSUR-402 — TARGET): Enterprise L2 Fiber Packet-Loss Triage & Optical DDM Recalibration",
                procedure_id="SOP-ASSUR-402",
                relevance_score=0.99,
                disposition="IN_SCOPE_SELECTED",
                rationale="Exact match for UC-001 Enterprise L2 dedicated fiber packet-loss & DDM recalibration.",
            ),
        ],
        skill_spec=CompiledSkillSpec(
            uc_id="UC-001",
            sop_id="SOP-ASSUR-402",
            skill_id="telco.assurance.l2_fiber_degradation",
            etom_process_ids=["1.3.7", "1.4.5"],
            bound_mcp_primitives=[
                "mcp://semantic-read/query_knowledge_fabric",
                "cqrs://singleton-check/probe_resource_state",
                "cqrs://transactional-write/execute_governed_mutation",
                "cqrs://transactional-write/commit_validated_graph_triples",
            ],
            workflow_steps=[
                SkillWorkflowStep(
                    step_number=1,
                    step_id="STEP_1_SEMANTIC_CONTEXT",
                    description="Query 6-graph federated circuit context via Layer 3/4.",
                    mcp_primitive_uri="mcp://semantic-read/query_knowledge_fabric",
                    protocol="SPARQL_1_1_FEDERATED_READ",
                    guardrail_ids=[],
                ),
                SkillWorkflowStep(
                    step_number=2,
                    step_id="STEP_2_SINGLETON_OPTICAL_PROBE",
                    description="Probe un-cached live gNMI optical Rx power and acquire mutex lock.",
                    mcp_primitive_uri="cqrs://singleton-check/probe_resource_state",
                    protocol="gNMI_OPTICAL_TELEMETRY",
                    guardrail_ids=["GR-PRE-01"],
                ),
                SkillWorkflowStep(
                    step_number=3,
                    step_id="STEP_3_BRANCH_EXECUTION",
                    description="Evaluate GR-INV-01/02 and execute Branch A recalibration or Branch B/C routing.",
                    mcp_primitive_uri="cqrs://transactional-write/execute_governed_mutation",
                    protocol="TMF640_SERVICE_ACTIVATION",
                    guardrail_ids=["GR-PRE-01", "GR-INV-01", "GR-INV-02"],
                ),
                SkillWorkflowStep(
                    step_number=4,
                    step_id="STEP_4_POST_CHECK_AND_TICKET",
                    description="Post-recalibration verification and TMF621 trouble ticket / RDF commit.",
                    mcp_primitive_uri="cqrs://transactional-write/execute_governed_mutation",
                    protocol="TMF621_TROUBLE_TICKET",
                    guardrail_ids=["GR-POST-01"],
                ),
            ],
            branch_routing=[
                SkillBranchRule(
                    branch_id="BRANCH_A_SOFT_DEGRADATION",
                    condition_summary="rx_power in [-25.0, -27.5] dBm and maintenance_lock == false",
                    allowed_mcp_primitive_uri="cqrs://transactional-write/execute_governed_mutation",
                    allowed_protocol="TMF640_SERVICE_ACTIVATION",
                    outcome_status="RESOLVED_AUTO",
                ),
                SkillBranchRule(
                    branch_id="BRANCH_B_CRITICAL_LOS",
                    condition_summary="rx_power < -27.5 dBm",
                    allowed_mcp_primitive_uri="cqrs://transactional-write/execute_governed_mutation",
                    allowed_protocol="TMF621_TROUBLE_TICKET",
                    outcome_status="P1_CRITICAL_FIELD_DISPATCH",
                ),
                SkillBranchRule(
                    branch_id="BRANCH_C_MAINTENANCE_LOCK",
                    condition_summary="maintenance_lock == true",
                    allowed_mcp_primitive_uri="cqrs://transactional-write/execute_governed_mutation",
                    allowed_protocol="TMF621_TROUBLE_TICKET",
                    outcome_status="DEFERRED_MAINTENANCE_LOCK",
                ),
            ],
        ),
        guardrails_spec=CompiledGuardrailsSpec(
            uc_id="UC-001",
            sop_id="SOP-ASSUR-402",
            rules=[
                MachineGuardrailRule(
                    guardrail_id="GR-PRE-01",
                    phase="PRE_CONDITION",
                    description="Require live un-cached gNMI optical probe before mutation.",
                    parameter="gnmi_uncached_probed",
                    operator="==",
                    threshold_value=True,
                    blocking_action="BLOCK_ABORT_REQUIRE_GNMI_PROBE",
                    target_tool="TMF640_SERVICE_ACTIVATION",
                ),
                MachineGuardrailRule(
                    guardrail_id="GR-INV-01",
                    phase="EXECUTION_INVARIANT",
                    description="Block DDM recalibration below critical LOS cutoff (-27.5 dBm).",
                    parameter="rx_power_dbm",
                    operator=">=",
                    threshold_value=-27.5,
                    blocking_action="BLOCK_ROUTE_TO_TMF621_FIELD_DISPATCH",
                    target_tool="TMF640_SERVICE_ACTIVATION",
                ),
                MachineGuardrailRule(
                    guardrail_id="GR-INV-02",
                    phase="EXECUTION_INVARIANT",
                    description="Block remote mutations when customer maintenance lock is active.",
                    parameter="maintenance_lock",
                    operator="==",
                    threshold_value=False,
                    blocking_action="BLOCK_DEFER_MAINTENANCE_LOCK",
                    target_tool="TMF640_SERVICE_ACTIVATION",
                ),
                MachineGuardrailRule(
                    guardrail_id="GR-POST-01",
                    phase="POST_CONDITION",
                    description="Require post-recalibration gNMI verification.",
                    parameter="post_check_required",
                    operator="==",
                    threshold_value=True,
                    blocking_action="REQUIRE_POST_CHECK_VERIFICATION",
                    target_tool="TMF640_SERVICE_ACTIVATION",
                ),
            ],
        ),
        architect_verification_questions=[
            "Q1: Approve pruning SOP-ASSUR-101/205/310/509 and selecting SOP-ASSUR-402?",
            "Q2: Approve the 4-step workflow state machine and MCP primitive bindings?",
            "Q3: Approve GR-PRE-01, GR-INV-01 (-27.5 dBm), GR-INV-02, and GR-POST-01?",
            "Q4: Confirm DT-02b 3/3 adverse guardrail interception proof?",
        ],
    )


def test_zero_hardcoded_sop_or_dbm_literals_in_compiler() -> None:
    compiler_path = WORKSPACE_ROOT / "src/track_a/sop_to_skill_compiler.py"
    content = compiler_path.read_text(encoding="utf-8")
    forbidden = (
        "-25.0",
        "-27.5",
        "SOP-ASSUR-101",
        "SOP-ASSUR-205",
        "SOP-ASSUR-310",
        "SOP-ASSUR-402",
        "SOP-ASSUR-509",
        "gNodeB",
        "GPON",
        "EDFA",
    )
    for token in forbidden:
        assert token not in content, f"Forbidden hardcoded SOP/dBm token '{token}' in compiler"


def test_dt02a_fails_fast_on_missing_tbox_and_partial_gap(tmp_path: Path) -> None:
    ws = _setup_track_a_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = logging.getLogger("test_dt02_fail_fast")

    # 1. Missing TBox -> fail fast
    tbox = ws / config.layer4_compiler_federation.tbox_path
    tbox.unlink()
    with pytest.raises(RuntimeError, match="TBox not found"):
        run_dt02_sop_skill_compiler(config=config, logger=logger, mode="candidate", root_dir=ws)

    # Restore TBox and set PARTIAL_GAP
    shutil.copy2(WORKSPACE_ROOT / "data/semantic_store/tbox_sid_etom.ttl", tbox)
    set_tmf621_primitive_enabled(enabled=False, config=config, workspace_root=ws)

    with pytest.raises(RuntimeError, match="PARTIAL_GAP"):
        run_dt02_sop_skill_compiler(config=config, logger=logger, mode="candidate", root_dir=ws)

    missing_spec = ws / config.layer2_worker_and_sop.missing_primitive_spec_path
    assert missing_spec.exists()
    assert (ws / config.layer2_worker_and_sop.hitl_sop_review_report_path).exists()
    assert not (ws / config.layer2_worker_and_sop.gate3_candidate_proposal_path).exists()
    assert not (ws / config.layer2_worker_and_sop.active_skill_path).exists()


def test_dt02_two_phase_hitl_gate3_and_dt00_cleanup(tmp_path: Path) -> None:
    ws = _setup_track_a_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = logging.getLogger("test_dt02_e2e")

    with patch(
        "src.track_a.sop_to_skill_compiler._call_sop_compiler_llm",
        return_value=_sample_sop_proposal(),
    ):
        cand_res = run_dt02_sop_skill_compiler(
            config=config, logger=logger, mode="candidate", root_dir=ws
        )

    assert cand_res.mode == "candidate"
    assert cand_res.sys01_element6_state == "CANDIDATE_COMPILED (Awaiting HITL Gate 3)"
    assert cand_res.adverse_tests_passed == 3
    assert cand_res.adverse_tests_total == 3
    assert len(cand_res.architect_verification_questions) == 4
    assert cand_res.candidate_proposal_path.exists()
    assert not cand_res.active_skill_path.exists()
    assert not cand_res.active_guardrails_path.exists()
    html_text = cand_res.hitl_report_html_path.read_text(encoding="utf-8")
    assert "Machine-Enforceable Guardrails" in html_text
    assert "HITL Gate 3 NOC Architect Verification Questions" in html_text
    for q in cand_res.architect_verification_questions:
        assert q in html_text

    sys01_cand = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    assert sys01_cand.elements[5].state == "CANDIDATE_COMPILED (Awaiting HITL Gate 3)"

    # Phase 2: Approve
    app_res = run_dt02_sop_skill_compiler(
        config=config, logger=logger, mode="approve", root_dir=ws
    )
    assert app_res.mode == "approve"
    assert app_res.sys01_element6_state == "VERIFIED_LOCKED"
    assert app_res.active_skill_path.exists()
    assert app_res.active_guardrails_path.exists()

    sys01_app = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    assert sys01_app.elements[5].state == "VERIFIED_LOCKED"

    # DT-00 reset deletes Gate 3 candidate, active skill/guardrails, and reports
    reset_to_clean_slate(config, logger, workspace_root=ws)
    assert not cand_res.candidate_proposal_path.exists()
    assert not app_res.active_skill_path.exists()
    assert not app_res.active_guardrails_path.exists()
    assert not app_res.hitl_report_html_path.exists()
    assert not app_res.hitl_report_markdown_path.exists()

    sys01_reset = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    assert sys01_reset.elements[5].state == "EMPTY"
