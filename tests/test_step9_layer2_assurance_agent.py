"""
Unit tests for Step 9 (IMP-011): Layer 2 Skill-Governed Assurance Specialist Agent & Guardrail Interceptor.
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
from rdflib import Dataset, URIRef

from src.config import get_workspace_root, load_config
from src.layer2.assurance_specialist_agent import run_layer2_assurance_workflow
from src.layer2.guardrail_interceptor import (
    load_compiled_skill_and_guardrails,
    validate_step_transition,
    validate_tool_invocation,
)
from src.logger import setup_logger
from src.models import Layer2OrchestrationAndNarrativeProposal
from src.state_manager import initialize_cqrs_state, reset_to_clean_slate


def _prepare_isolated_workspace(tmp_path: Path) -> Path:
    root = get_workspace_root()
    for rel_dir in (
        "data/semantic_store",
        "data/cqrs_state",
        "data/raw_sources/sql",
        "mappings",
        "shapes",
        "skills",
        "prompts",
        "config",
    ):
        (tmp_path / rel_dir).mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        "config.yaml",
        "config/mcp_primitives_catalog.json",
        "data/semantic_store/tbox_sid_etom.ttl",
        "data/semantic_store/knowledge_graph.trig",
        "data/semantic_store/stored_sparql_templates.yaml",
        "data/raw_sources/sql/cmdb_installed_base.db",
        "mappings/cmdb_r2rml.ttl",
        "shapes/trouble_ticket_shape.ttl",
        "skills/skill_sop_402.yaml",
        "skills/guardrails_sop_402.json",
        "prompts/layer2_assurance_agent_prompt.md",
        "prompts/layer3_voicebox_hybrid_prompt.md",
        "prompts/layer3_zero_shot_sparql_prompt.md",
    ]
    for rel in files_to_copy:
        src = root / rel
        if src.exists():
            shutil.copy2(src, tmp_path / rel)
    return tmp_path


def test_layer2_contains_zero_raw_source_references() -> None:
    root = get_workspace_root()
    layer2_dir = root / "src" / "layer2"
    forbidden = ("data/raw_sources/", "cmdb_r2rml.ttl", "cmdb_installed_base.db")
    for py_file in layer2_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in content, f"Forbidden raw-source reference '{token}' in {py_file}"


def test_step_transition_and_tool_whitelist_reject_deviations() -> None:
    root = get_workspace_root()
    config = load_config(root / "config.yaml")
    skill_spec, _ = load_compiled_skill_and_guardrails(config, root)

    # Out-of-order and unrecognized step transitions rejected
    with pytest.raises(PermissionError, match="expected 'STEP_1_SEMANTIC_CONTEXT'"):
        validate_step_transition(skill_spec, [], "STEP_2_SINGLETON_OPTICAL_PROBE")
    with pytest.raises(PermissionError, match="Unrecognized SOP step"):
        validate_step_transition(skill_spec, [], "STEP_99_ROGUE_ACTION")

    # Closed-world tool whitelist rejects unbound or wrong-step tools
    assert (
        validate_tool_invocation(
            skill_spec, "STEP_1_SEMANTIC_CONTEXT", "semantic_read_mcp.query_knowledge_fabric"
        )
        == "mcp://semantic-read/query_knowledge_fabric"
    )
    with pytest.raises(PermissionError, match="Closed-world tool whitelist"):
        validate_tool_invocation(
            skill_spec, "STEP_1_SEMANTIC_CONTEXT", "gnmi_telemetry_mcp.probe_optical_ddm_telemetry"
        )
    with pytest.raises(PermissionError, match="Guardrail Interceptor blocked"):
        validate_tool_invocation(
            skill_spec,
            "STEP_3_GUARDRAIL_BRANCH_EXECUTION",
            "tmf640_activation_mcp.recalibrate_optical_ddm_bias",
            selected_branch="BRANCH_B_HARD_FIBER_CUT",
            pre_decision=None,
        )


def test_layer2_fails_fast_when_compiled_skill_missing(tmp_path: Path) -> None:
    ws = _prepare_isolated_workspace(tmp_path)
    (ws / "skills" / "skill_sop_402.yaml").unlink()
    config = load_config(ws / "config.yaml")
    logger = setup_logger(config, logger_name="test.step9.missing_skill", workspace_root=ws)

    with pytest.raises(RuntimeError, match="Track A prerequisite missing"):
        run_layer2_assurance_workflow(
            telemetry_preset="branch_a_soft_degradation",
            layer3_mode="voicebox_hybrid",
            config=config,
            logger=logger,
            root_dir=ws,
        )


def test_rt01_rt02_rt03_branches_and_guardrail_override_and_dt00_cleanup(tmp_path: Path) -> None:
    ws = _prepare_isolated_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = setup_logger(config, logger_name="test.step9.branches", workspace_root=ws)
    initialize_cqrs_state(config, ws)

    # Intentionally have the mocked LLM propose recalibration even in Branch B/C
    # to prove the deterministic Python Guardrail Interceptor overrides it!
    rogue_or_branch_a_proposal = Layer2OrchestrationAndNarrativeProposal(
        ordered_step_ids=[
            "STEP_1_SEMANTIC_CONTEXT",
            "STEP_2_SINGLETON_OPTICAL_PROBE",
            "STEP_3_GUARDRAIL_BRANCH_EXECUTION",
            "STEP_4_POST_VERIFICATION_COMMIT",
        ],
        proposed_branch="BRANCH_A_SOFT_OPTICAL_DEGRADATION",
        proposed_recalibration=True,
        olt_port_id="OLT04-P12",
        cpe_device_id="CPE-ASN-7741",
        customer_id="CUST-ENT-409",
        affected_resource_id="OLT04-P12",
        recommended_ticket_severity="MINOR",
        recommended_ticket_status="RESOLVED_AUTO",
        recommended_resolution_action="CLOSED_LOOP_DDM_RECALIBRATED",
        engineering_root_cause_summary=(
            "CIR-994821 (A Corporate Enterprise B.V., ETH-10G-GOLD) triaged on OLT04-P12 / CPE-ASN-7741."
        ),
    )

    with patch(
        "src.layer2.assurance_specialist_agent._invoke_layer2_orchestration_llm",
        return_value=rogue_or_branch_a_proposal,
    ):
        # RT-01: Branch A (Soft Degradation -> TMF640 -> GR-POST-01 -> RESOLVED_AUTO)
        res_a = run_layer2_assurance_workflow(
            telemetry_preset="branch_a_soft_degradation",
            layer3_mode="voicebox_hybrid",
            config=config,
            logger=logger,
            root_dir=ws,
        )
        assert res_a.scenario_id == "RT-01"
        assert res_a.selected_branch == "BRANCH_A_SOFT_OPTICAL_DEGRADATION"
        assert res_a.pre_guardrail_decision.remediation_allowed is True
        assert res_a.tmf640_invocations_count == 1
        assert res_a.post_telemetry is not None
        assert res_a.post_telemetry.rx_power_dbm == -21.4
        assert res_a.post_guardrail_decision is not None
        assert res_a.post_guardrail_decision.passed is True
        assert res_a.tmf621_response.persisted is True
        assert res_a.tmf621_response.shacl_conforms is True
        assert res_a.tmf621_response.ticket is not None
        assert res_a.tmf621_response.ticket.status == "RESOLVED_AUTO"

        # RT-02: Branch B (Hard Fiber Cut -> GR-INV-01 blocks TMF640 -> 0 calls -> OPEN_DISPATCHED)
        res_b = run_layer2_assurance_workflow(
            telemetry_preset="branch_b_hard_fiber_cut",
            layer3_mode="voicebox_hybrid",
            config=config,
            logger=logger,
            root_dir=ws,
        )
        assert res_b.scenario_id == "RT-02"
        assert res_b.selected_branch == "BRANCH_B_HARD_FIBER_CUT"
        assert res_b.pre_guardrail_decision.remediation_allowed is False
        assert "GR-INV-01" in res_b.pre_guardrail_decision.blocking_guardrail_ids
        assert res_b.tmf640_invocations_count == 0
        assert res_b.tmf621_response.persisted is True
        assert res_b.tmf621_response.shacl_conforms is True
        assert res_b.tmf621_response.ticket is not None
        assert res_b.tmf621_response.ticket.severity == "CRITICAL"
        assert res_b.tmf621_response.ticket.status == "OPEN_DISPATCHED"

        # RT-03: Branch C (Maintenance Lock -> GR-INV-02 blocks TMF640 -> 0 calls -> DEFERRED_MAINTENANCE)
        res_c = run_layer2_assurance_workflow(
            telemetry_preset="branch_c_maintenance_lock",
            layer3_mode="voicebox_hybrid",
            config=config,
            logger=logger,
            root_dir=ws,
        )
        assert res_c.scenario_id == "RT-03"
        assert res_c.selected_branch == "BRANCH_C_MAINTENANCE_LOCK"
        assert res_c.pre_guardrail_decision.remediation_allowed is False
        assert "GR-INV-02" in res_c.pre_guardrail_decision.blocking_guardrail_ids
        assert res_c.tmf640_invocations_count == 0
        assert res_c.tmf621_response.persisted is True
        assert res_c.tmf621_response.shacl_conforms is True
        assert res_c.tmf621_response.ticket is not None
        assert res_c.tmf621_response.ticket.severity == "WARNING"
        assert res_c.tmf621_response.ticket.status == "DEFERRED_MAINTENANCE"

    # Verify virtual:ib still has 0 persisted triples on disk
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(ws / config.layer4_compiler_federation.dataset_trig_path), format="trig")
        assert len(ds.graph(URIRef("urn:telco:graph:virtual:ib"))) == 0

    # Verify DT-00 cleans Step 9 report artifacts
    rep_html = ws / Path(config.layer2_worker_and_sop.runtime_branches_report_path)
    rep_html.parent.mkdir(parents=True, exist_ok=True)
    rep_html.write_text("<html></html>", encoding="utf-8")
    rep_html.with_suffix(".md").write_text("# report", encoding="utf-8")
    reset_to_clean_slate(config, logger, workspace_root=ws)
    assert not rep_html.exists()
    assert not rep_html.with_suffix(".md").exists()
