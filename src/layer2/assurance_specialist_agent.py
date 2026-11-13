"""
Layer 2: Skill-Governed Assurance Specialist Agent (`SOP-ASSUR-402`, Step 9 / IMP-011).

Executes runtime triage (`RT-01` Branch A, `RT-02` Branch B, `RT-03` Branch C) strictly
inside the compiled `skills/skill_sop_402.yaml` and `skills/guardrails_sop_402.json` sandbox,
combining deterministic Python guardrail interception with Gemini NL orchestration.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Dict, List, Literal, Optional

from google.genai import types
from rdflib import Dataset, URIRef

from src.config import get_workspace_root, load_config
from src.layer2.guardrail_interceptor import (
    evaluate_post_execution_guardrail,
    evaluate_pre_execution_guardrails,
    load_compiled_skill_and_guardrails,
    validate_step_transition,
    validate_tool_invocation,
)
from src.llm_client import (
    create_genai_client,
    resolve_model_for_component,
    strip_unsupported_vertex_schema_keys,
)
from src.logger import setup_logger
from src.mcp_servers.common import save_cqrs_state, utc_now_iso
from src.mcp_servers.gnmi_telemetry_mcp import execute_probe_optical_ddm_telemetry
from src.mcp_servers.semantic_read_mcp import execute_query_knowledge_fabric
from src.mcp_servers.tmf621_trouble_ticket_mcp import execute_create_or_update_trouble_ticket
from src.mcp_servers.tmf640_activation_mcp import execute_recalibrate_optical_ddm_bias
from src.models import (
    AppConfig,
    FederatedCircuitContext,
    GnmiOpticalTelemetryResponse,
    Layer2ExecutionResult,
    Layer2OrchestrationAndNarrativeProposal,
    Layer2ToolCallTrace,
    PostExecutionGuardrailDecision,
    Tmf621TicketResponse,
    Tmf640ActivationResponse,
)
from src.state_manager import initialize_cqrs_state

_PRESET_TO_SCENARIO: Dict[str, Literal["RT-01", "RT-02", "RT-03"]] = {
    "branch_a_soft_degradation": "RT-01",
    "branch_b_hard_fiber_cut": "RT-02",
    "branch_c_maintenance_lock": "RT-03",
}


def _verify_layer2_prerequisites(config: AppConfig, workspace_root: Path) -> None:
    """Fail fast if Track B, Layer 3/4, or Track A (VERIFIED_LOCKED) prerequisites are missing."""
    tbox_path = workspace_root / Path(config.layer4_compiler_federation.tbox_path)
    trig_path = workspace_root / Path(config.layer4_compiler_federation.dataset_trig_path)
    r2rml_path = workspace_root / Path(config.layer4_compiler_federation.r2rml_path)
    templates_path = workspace_root / Path(config.layer3_nl2semantics.stored_sparql_templates_path)

    for label, path in (
        ("TBox ontology", tbox_path),
        ("Knowledge Graph TriG", trig_path),
        ("R2RML mapping", r2rml_path),
        ("Stored SPARQL templates", templates_path),
    ):
        if not path.exists():
            raise RuntimeError(
                f"Layer 2 prerequisite missing ({label} at {path}). "
                "Complete Track B and Layer 3 compilation before invoking Layer 2."
            )

    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(trig_path), format="trig")
        virtual_ib_count = len(ds.graph(URIRef("urn:telco:graph:virtual:ib")))
    if virtual_ib_count != 0:
        raise RuntimeError(
            f"Zero-Copy Invariant Violation: virtual:ib graph contains {virtual_ib_count} persisted triples."
        )

    skill_path = workspace_root / Path(config.layer2_worker_and_sop.active_skill_path)
    guardrails_path = workspace_root / Path(config.layer2_worker_and_sop.active_guardrails_path)
    if not skill_path.exists() or not guardrails_path.exists():
        raise RuntimeError(
            "Track A prerequisite missing: compiled skill/guardrails not found. "
            "Run Track A DT-02a/DT-02b (--mode approve) so SYS-01 Element 6 is VERIFIED_LOCKED."
        )


def _extract_federated_context(semantic_resp: dict) -> FederatedCircuitContext:
    """Extract `FederatedCircuitContext` from `semantic_read_mcp` response payload."""
    layer3_payload = semantic_resp.get("layer3_result") or semantic_resp
    raw_ctx = (
        layer3_payload.get("authoritative_context")
        or layer3_payload.get("circuit_context")
    )
    if not raw_ctx:
        raise RuntimeError(
            "semantic_read_mcp response did not contain a valid authoritative_context (FederatedCircuitContext)."
        )
    return FederatedCircuitContext.model_validate(raw_ctx)


def _render_agent_prompt(
    template_path: Path,
    circuit_id: str,
    incident_intent: str,
    skill_yaml_text: str,
    guardrails_json_text: str,
    federated_ctx: FederatedCircuitContext,
    telemetry: GnmiOpticalTelemetryResponse,
) -> str:
    """Render externalized Layer 2 assurance agent prompt template."""
    if not template_path.exists():
        raise FileNotFoundError(
            f"Layer 2 agent prompt template not found at {template_path}."
        )
    template = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{CIRCUIT_ID}}": circuit_id,
        "{{INCIDENT_INTENT}}": incident_intent,
        "{{SKILL_YAML}}": skill_yaml_text.strip(),
        "{{GUARDRAILS_JSON}}": guardrails_json_text.strip(),
        "{{FEDERATED_CONTEXT_JSON}}": json.dumps(federated_ctx.model_dump(), indent=2),
        "{{TELEMETRY_JSON}}": json.dumps(telemetry.model_dump(), indent=2),
    }
    rendered = template
    for key, val in replacements.items():
        rendered = rendered.replace(key, val)
    return rendered


def _invoke_layer2_orchestration_llm(
    config: AppConfig,
    prompt_text: str,
    model_name: str,
    logger: logging.Logger,
) -> Layer2OrchestrationAndNarrativeProposal:
    """Invoke Gemini via shared `src/llm_client.py` to produce structured orchestration output."""
    client = create_genai_client(config, logger)
    clean_schema = strip_unsupported_vertex_schema_keys(
        Layer2OrchestrationAndNarrativeProposal.model_json_schema()
    )
    gen_config = types.GenerateContentConfig(
        temperature=config.ai.temperature,
        max_output_tokens=config.ai.max_output_tokens,
        response_mime_type="application/json",
        response_schema=clean_schema,
    )
    response = client.models.generate_content(
        model=model_name,
        contents=prompt_text,
        config=gen_config,
    )
    if not response or not getattr(response, "text", None):
        raise RuntimeError(
            f"Gemini model '{model_name}' returned empty response for Layer2OrchestrationAndNarrativeProposal."
        )
    return Layer2OrchestrationAndNarrativeProposal.model_validate_json(response.text)


def run_layer2_assurance_workflow(
    incident_intent: str = (
        "Triage L2 enterprise fiber packet loss on circuit CIR-994821 and execute "
        "closed-loop optical DDM recalibration if within SLA/optical guardrails."
    ),
    circuit_id: str = "CIR-994821",
    telemetry_preset: Optional[
        Literal[
            "branch_a_soft_degradation",
            "branch_b_hard_fiber_cut",
            "branch_c_maintenance_lock",
        ]
    ] = None,
    layer3_mode: str = "voicebox_hybrid",
    obo_jwt_map: Optional[Dict[str, str]] = None,
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    root_dir: Optional[Path] = None,
) -> Layer2ExecutionResult:
    """
    Execute the 4-step `SOP-ASSUR-402` Layer 2 Assurance Specialist workflow
    with strict sandbox enforcement and deterministic Python guardrail interception.
    """
    workspace_root = root_dir or get_workspace_root()
    active_config = config or load_config(workspace_root / "config.yaml")
    active_logger = logger or setup_logger(
        active_config, logger_name="telco_agent.layer2", workspace_root=workspace_root
    )

    _verify_layer2_prerequisites(active_config, workspace_root)
    skill_spec, guardrails_spec = load_compiled_skill_and_guardrails(
        active_config, workspace_root
    )

    if telemetry_preset is not None:
        fresh_state = initialize_cqrs_state(active_config, workspace_root).model_copy(
            update={"active_telemetry_preset": telemetry_preset}
        )
        save_cqrs_state(fresh_state, active_config, workspace_root)
        active_preset = telemetry_preset
    else:
        from src.state_manager import load_cqrs_state

        active_preset = load_cqrs_state(active_config, workspace_root).active_telemetry_preset

    scenario_id = _PRESET_TO_SCENARIO[active_preset]
    completed_steps: List[str] = []
    step_traces: List[Layer2ToolCallTrace] = []
    jwt_map = obo_jwt_map or {}

    # ------------------------------------------------------------------
    # STEP 1: Semantic Context Retrieval (`semantic-read-mcp`)
    # ------------------------------------------------------------------
    step1 = validate_step_transition(skill_spec, completed_steps, "STEP_1_SEMANTIC_CONTEXT")
    cat_uri_1 = validate_tool_invocation(
        skill_spec, step1.step_id, "semantic_read_mcp.query_knowledge_fabric"
    )
    semantic_resp = execute_query_knowledge_fabric(
        natural_language_intent=incident_intent,
        target_circuit_id=circuit_id,
        execution_mode=layer3_mode,
        obo_jwt=jwt_map.get("semantic_read"),
        config=active_config,
        logger=active_logger,
        root_dir=workspace_root,
    )
    semantic_ctx = _extract_federated_context(semantic_resp)
    completed_steps.append(step1.step_id)
    step_traces.append(
        Layer2ToolCallTrace(
            step_number=step1.step_number,
            step_id=step1.step_id,
            catalog_primitive_uri=cat_uri_1,
            concrete_mcp_tool="semantic_read_mcp.query_knowledge_fabric",
            status="COMPLETED",
            detail=f"Retrieved 6-graph context for {semantic_ctx.circuit_id} ({semantic_ctx.olt_port_id}, {semantic_ctx.product_sku}).",
        )
    )

    # ------------------------------------------------------------------
    # STEP 2: Un-cached Live Optical DDM Probe (`gnmi-telemetry-mcp`)
    # ------------------------------------------------------------------
    step2 = validate_step_transition(
        skill_spec, completed_steps, "STEP_2_SINGLETON_OPTICAL_PROBE"
    )
    cat_uri_2 = validate_tool_invocation(
        skill_spec, step2.step_id, "gnmi_telemetry_mcp.probe_optical_ddm_telemetry"
    )
    raw_pre_telemetry = execute_probe_optical_ddm_telemetry(
        circuit_id=circuit_id,
        olt_port_id=semantic_ctx.olt_port_id,
        uncached=True,
        obo_jwt=jwt_map.get("gnmi_telemetry"),
        config=active_config,
        logger=active_logger,
        root_dir=workspace_root,
    )
    pre_telemetry = GnmiOpticalTelemetryResponse.model_validate(raw_pre_telemetry)
    completed_steps.append(step2.step_id)
    step_traces.append(
        Layer2ToolCallTrace(
            step_number=step2.step_number,
            step_id=step2.step_id,
            catalog_primitive_uri=cat_uri_2,
            concrete_mcp_tool="gnmi_telemetry_mcp.probe_optical_ddm_telemetry",
            status="COMPLETED",
            detail=f"Rx={pre_telemetry.rx_power_dbm} dBm, loss={pre_telemetry.packet_loss_pct}%, lock={pre_telemetry.maintenance_lock}.",
        )
    )

    # ------------------------------------------------------------------
    # STEP 3: LLM NL Orchestration + Deterministic Guardrail Interceptor
    # ------------------------------------------------------------------
    step3 = validate_step_transition(
        skill_spec, completed_steps, "STEP_3_GUARDRAIL_BRANCH_EXECUTION"
    )
    skill_text = (workspace_root / Path(active_config.layer2_worker_and_sop.active_skill_path)).read_text(
        encoding="utf-8"
    )
    guardrails_text = (
        workspace_root / Path(active_config.layer2_worker_and_sop.active_guardrails_path)
    ).read_text(encoding="utf-8")
    prompt_path = workspace_root / Path(
        active_config.layer2_worker_and_sop.agent_prompt_template_path
    )
    rendered_prompt = _render_agent_prompt(
        template_path=prompt_path,
        circuit_id=circuit_id,
        incident_intent=incident_intent,
        skill_yaml_text=skill_text,
        guardrails_json_text=guardrails_text,
        federated_ctx=semantic_ctx,
        telemetry=pre_telemetry,
    )
    model_used = resolve_model_for_component(active_config, "layer2_assurance_agent")
    llm_proposal = _invoke_layer2_orchestration_llm(
        config=active_config,
        prompt_text=rendered_prompt,
        model_name=model_used,
        logger=active_logger,
    )

    pre_decision = evaluate_pre_execution_guardrails(
        guardrails_spec=guardrails_spec,
        semantic_context=semantic_ctx,
        live_telemetry=pre_telemetry,
    )
    selected_branch = pre_decision.selected_branch

    tmf640_invocations_count = 0
    tmf640_response: Optional[Tmf640ActivationResponse] = None
    tmf621_response: Optional[Tmf621TicketResponse] = None

    if selected_branch == "BRANCH_A_SOFT_OPTICAL_DEGRADATION":
        cat_uri_3 = validate_tool_invocation(
            skill_spec,
            step3.step_id,
            "tmf640_activation_mcp.recalibrate_optical_ddm_bias",
            selected_branch=selected_branch,
            pre_decision=pre_decision,
        )
        raw_act = execute_recalibrate_optical_ddm_bias(
            circuit_id=circuit_id,
            olt_port_id=semantic_ctx.olt_port_id,
            cpe_device_id=semantic_ctx.cpe_asset_id,
            reason=f"SOP-ASSUR-402 {selected_branch}",
            obo_jwt=jwt_map.get("tmf640_activation"),
            config=active_config,
            logger=active_logger,
            root_dir=workspace_root,
        )
        tmf640_response = Tmf640ActivationResponse.model_validate(raw_act)
        tmf640_invocations_count = 1
        step_traces.append(
            Layer2ToolCallTrace(
                step_number=step3.step_number,
                step_id=step3.step_id,
                catalog_primitive_uri=cat_uri_3,
                concrete_mcp_tool="tmf640_activation_mcp.recalibrate_optical_ddm_bias",
                status=tmf640_response.status,
                detail=tmf640_response.explanation,
            )
        )
    elif selected_branch == "BRANCH_B_HARD_FIBER_CUT":
        cat_uri_3 = validate_tool_invocation(
            skill_spec,
            step3.step_id,
            "tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
            selected_branch=selected_branch,
            pre_decision=pre_decision,
        )
        raw_tkt = execute_create_or_update_trouble_ticket(
            circuit_id=circuit_id,
            customer_id=semantic_ctx.customer_id,
            severity="CRITICAL",
            status="OPEN_DISPATCHED",
            resolution_action="P1_CRITICAL_FIELD_DISPATCH",
            summary=llm_proposal.engineering_root_cause_summary,
            affected_resource_id=semantic_ctx.olt_port_id,
            obo_jwt=jwt_map.get("tmf621_trouble_ticket"),
            config=active_config,
            logger=active_logger,
            root_dir=workspace_root,
        )
        tmf621_response = Tmf621TicketResponse.model_validate(raw_tkt)
        step_traces.append(
            Layer2ToolCallTrace(
                step_number=step3.step_number,
                step_id=step3.step_id,
                catalog_primitive_uri=cat_uri_3,
                concrete_mcp_tool="tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
                status=tmf621_response.status,
                detail=f"GR-INV-01 blocked TMF640 (0 invocations); {tmf621_response.explanation}",
            )
        )
    else:
        cat_uri_3 = validate_tool_invocation(
            skill_spec,
            step3.step_id,
            "tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
            selected_branch=selected_branch,
            pre_decision=pre_decision,
        )
        raw_tkt = execute_create_or_update_trouble_ticket(
            circuit_id=circuit_id,
            customer_id=semantic_ctx.customer_id,
            severity="WARNING",
            status="DEFERRED_MAINTENANCE",
            resolution_action="DEFERRED_MAINTENANCE_LOCK",
            summary=llm_proposal.engineering_root_cause_summary,
            affected_resource_id=semantic_ctx.olt_port_id,
            obo_jwt=jwt_map.get("tmf621_trouble_ticket"),
            config=active_config,
            logger=active_logger,
            root_dir=workspace_root,
        )
        tmf621_response = Tmf621TicketResponse.model_validate(raw_tkt)
        step_traces.append(
            Layer2ToolCallTrace(
                step_number=step3.step_number,
                step_id=step3.step_id,
                catalog_primitive_uri=cat_uri_3,
                concrete_mcp_tool="tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
                status=tmf621_response.status,
                detail=f"GR-INV-02 blocked TMF640 (0 invocations); {tmf621_response.explanation}",
            )
        )

    completed_steps.append(step3.step_id)

    # ------------------------------------------------------------------
    # STEP 4: Post-Verification & SHACL-Validated Ticket Commit
    # ------------------------------------------------------------------
    step4 = validate_step_transition(
        skill_spec, completed_steps, "STEP_4_POST_VERIFICATION_COMMIT"
    )
    post_telemetry: Optional[GnmiOpticalTelemetryResponse] = None
    post_decision: Optional[PostExecutionGuardrailDecision] = None

    if selected_branch == "BRANCH_A_SOFT_OPTICAL_DEGRADATION":
        cat_uri_4_gnmi = validate_tool_invocation(
            skill_spec, step4.step_id, "gnmi_telemetry_mcp.probe_optical_ddm_telemetry"
        )
        raw_post = execute_probe_optical_ddm_telemetry(
            circuit_id=circuit_id,
            olt_port_id=semantic_ctx.olt_port_id,
            uncached=True,
            obo_jwt=jwt_map.get("gnmi_telemetry"),
            config=active_config,
            logger=active_logger,
            root_dir=workspace_root,
        )
        post_telemetry = GnmiOpticalTelemetryResponse.model_validate(raw_post)
        post_decision = evaluate_post_execution_guardrail(
            guardrails_spec=guardrails_spec,
            semantic_context=semantic_ctx,
            post_telemetry=post_telemetry,
        )
        if not post_decision.passed:
            raise RuntimeError(
                f"GR-POST-01 post-recalibration check failed: {post_decision.blocking_guardrail_ids}"
            )
        step_traces.append(
            Layer2ToolCallTrace(
                step_number=step4.step_number,
                step_id=step4.step_id,
                catalog_primitive_uri=cat_uri_4_gnmi,
                concrete_mcp_tool="gnmi_telemetry_mcp.probe_optical_ddm_telemetry",
                status="VERIFIED_GR_POST_01",
                detail=f"Post-check Rx={post_telemetry.rx_power_dbm} dBm, loss={post_telemetry.packet_loss_pct}%.",
            )
        )

        cat_uri_4_tkt = validate_tool_invocation(
            skill_spec,
            step4.step_id,
            "tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
        )
        raw_tkt_a = execute_create_or_update_trouble_ticket(
            circuit_id=circuit_id,
            customer_id=semantic_ctx.customer_id,
            severity="MINOR",
            status="RESOLVED_AUTO",
            resolution_action="CLOSED_LOOP_DDM_RECALIBRATED",
            summary=llm_proposal.engineering_root_cause_summary,
            affected_resource_id=semantic_ctx.olt_port_id,
            obo_jwt=jwt_map.get("tmf621_trouble_ticket"),
            config=active_config,
            logger=active_logger,
            root_dir=workspace_root,
        )
        tmf621_response = Tmf621TicketResponse.model_validate(raw_tkt_a)
        step_traces.append(
            Layer2ToolCallTrace(
                step_number=step4.step_number,
                step_id=step4.step_id,
                catalog_primitive_uri=cat_uri_4_tkt,
                concrete_mcp_tool="tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
                status=tmf621_response.status,
                detail=tmf621_response.explanation,
            )
        )
    else:
        step_traces.append(
            Layer2ToolCallTrace(
                step_number=step4.step_number,
                step_id=step4.step_id,
                catalog_primitive_uri=step4.mcp_primitive_uri,
                concrete_mcp_tool="tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
                status="COMMITTED_NO_REMEDIATION",
                detail=f"Branch {selected_branch} completed with 0 TMF640 calls; ticket {tmf621_response.ticket.ticket_id if tmf621_response and tmf621_response.ticket else 'N/A'} pySHACL-verified.",
            )
        )

    completed_steps.append(step4.step_id)
    assert tmf621_response is not None
    if not tmf621_response.persisted or not tmf621_response.shacl_conforms:
        raise RuntimeError(
            f"TMF621 ticket persistence/SHACL validation failed: {tmf621_response.explanation}"
        )

    active_logger.info(
        "Layer 2 Assurance | scenario=%s | branch=%s | tmf640_calls=%d | ticket=%s (%s)",
        scenario_id,
        selected_branch,
        tmf640_invocations_count,
        tmf621_response.ticket.ticket_id if tmf621_response.ticket else "NONE",
        tmf621_response.ticket.status if tmf621_response.ticket else "NONE",
    )
    return Layer2ExecutionResult(
        scenario_id=scenario_id,
        telemetry_preset=active_preset,
        circuit_id=circuit_id,
        model_used=model_used,
        selected_branch=selected_branch,
        llm_proposal=llm_proposal,
        pre_guardrail_decision=pre_decision,
        post_guardrail_decision=post_decision,
        tmf640_invocations_count=tmf640_invocations_count,
        tmf640_response=tmf640_response,
        tmf621_response=tmf621_response,
        pre_telemetry=pre_telemetry,
        post_telemetry=post_telemetry,
        step_traces=step_traces,
        executed_at_utc=utc_now_iso(),
    )
