"""
Deterministic Layer 2 Sandbox Enforcer & Pre-/Post-Execution Guardrail Interceptor.

Enforces all 4 mandatory Worker Agent sandbox invariants from `skills/skill_sop_402.yaml`
and `skills/guardrails_sop_402.json` without reading any raw sources or R2RML files.
"""

from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple

import yaml

from src.models import (
    AppConfig,
    CompiledGuardrailsSpec,
    CompiledSkillSpec,
    FederatedCircuitContext,
    GnmiOpticalTelemetryResponse,
    GuardrailRuleEvaluationTrace,
    MachineGuardrailRule,
    PostExecutionGuardrailDecision,
    PreExecutionGuardrailDecision,
    SkillWorkflowStep,
)

_OPERATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}

# Concrete Step 6/8 MCP server functions authorized per generic catalog URI in skill_sop_402.yaml
_STEP_TOOL_DISPATCH_MAP: Dict[str, Dict[str, str]] = {
    "STEP_1_SEMANTIC_CONTEXT": {
        "mcp://semantic-read/query_knowledge_fabric": "semantic_read_mcp.query_knowledge_fabric",
    },
    "STEP_2_SINGLETON_OPTICAL_PROBE": {
        "cqrs://singleton-check/probe_resource_state": "gnmi_telemetry_mcp.probe_optical_ddm_telemetry",
    },
    "STEP_3_GUARDRAIL_BRANCH_EXECUTION": {
        "cqrs://transactional-write/execute_governed_mutation:TMF640": "tmf640_activation_mcp.recalibrate_optical_ddm_bias",
        "cqrs://transactional-write/execute_governed_mutation:TMF621": "tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
    },
    "STEP_4_POST_VERIFICATION_COMMIT": {
        "cqrs://transactional-write/commit_validated_graph_triples:POST_GNMI": "gnmi_telemetry_mcp.probe_optical_ddm_telemetry",
        "cqrs://transactional-write/commit_validated_graph_triples:TMF621": "tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket",
    },
}


def load_compiled_skill_and_guardrails(
    config: AppConfig, workspace_root: Path
) -> Tuple[CompiledSkillSpec, CompiledGuardrailsSpec]:
    """Load and validate the locked Gate 3 skill YAML and guardrails JSON."""
    skill_path = workspace_root / Path(config.layer2_worker_and_sop.active_skill_path)
    guardrails_path = workspace_root / Path(config.layer2_worker_and_sop.active_guardrails_path)

    if not skill_path.exists():
        raise RuntimeError(
            f"Missing compiled Layer 2 skill at {skill_path}. "
            "Run Track A DT-02a/DT-02b (--mode approve) before invoking Layer 2."
        )
    if not guardrails_path.exists():
        raise RuntimeError(
            f"Missing compiled Layer 2 guardrails at {guardrails_path}. "
            "Run Track A DT-02a/DT-02b (--mode approve) before invoking Layer 2."
        )

    skill_raw = yaml.safe_load(skill_path.read_text(encoding="utf-8"))
    guardrails_raw = json.loads(guardrails_path.read_text(encoding="utf-8"))
    return (
        CompiledSkillSpec.model_validate(skill_raw),
        CompiledGuardrailsSpec.model_validate(guardrails_raw),
    )


def validate_step_transition(
    skill_spec: CompiledSkillSpec,
    completed_step_ids: Sequence[str],
    next_step_id: str,
) -> SkillWorkflowStep:
    """
    Invariant 1 — Zero Deviation from Skill Steps.

    Enforces exact ordered execution of `skill_spec.workflow_steps` without skipping,
    reordering, or inventing extra steps.
    """
    ordered_steps = sorted(skill_spec.workflow_steps, key=lambda s: s.step_number)
    known_ids = {s.step_id for s in ordered_steps}
    if next_step_id not in known_ids:
        raise PermissionError(
            f"Unrecognized SOP step '{next_step_id}'; allowed steps: {[s.step_id for s in ordered_steps]}."
        )

    expected_index = len(completed_step_ids)
    if expected_index >= len(ordered_steps):
        raise PermissionError(
            f"SOP workflow already completed ({len(ordered_steps)} steps); cannot transition to '{next_step_id}'."
        )

    expected_step = ordered_steps[expected_index]
    if next_step_id != expected_step.step_id:
        raise PermissionError(
            f"SOP step sequence violation: expected '{expected_step.step_id}' at index {expected_index}, "
            f"but attempted '{next_step_id}'."
        )
    return expected_step


def validate_tool_invocation(
    skill_spec: CompiledSkillSpec,
    step_id: str,
    concrete_tool_name: str,
    selected_branch: Optional[str] = None,
    pre_decision: Optional[PreExecutionGuardrailDecision] = None,
) -> str:
    """
    Invariant 2 — Closed-World Tool Whitelist.

    Verifies that `concrete_tool_name` is authorized by `skill_sop_402.yaml` for `step_id`
    and blocks `tmf640_activation_mcp` outside Branch A with passing pre-execution guardrails.
    Returns the bound catalog primitive URI from `skill_spec.bound_mcp_primitives`.
    """
    step_map = {s.step_id: s for s in skill_spec.workflow_steps}
    if step_id not in step_map:
        raise PermissionError(f"Cannot invoke tool in unknown SOP step '{step_id}'.")

    step = step_map[step_id]
    catalog_uri = step.mcp_primitive_uri
    if catalog_uri not in set(skill_spec.bound_mcp_primitives):
        raise PermissionError(
            f"Catalog primitive '{catalog_uri}' on step '{step_id}' is not in bound_mcp_primitives."
        )

    allowed_concrete: List[str] = []
    if step_id == "STEP_1_SEMANTIC_CONTEXT":
        allowed_concrete = [
            _STEP_TOOL_DISPATCH_MAP[step_id]["mcp://semantic-read/query_knowledge_fabric"]
        ]
    elif step_id == "STEP_2_SINGLETON_OPTICAL_PROBE":
        allowed_concrete = [
            _STEP_TOOL_DISPATCH_MAP[step_id]["cqrs://singleton-check/probe_resource_state"]
        ]
    elif step_id == "STEP_3_GUARDRAIL_BRANCH_EXECUTION":
        tmf640_tool = _STEP_TOOL_DISPATCH_MAP[step_id][
            "cqrs://transactional-write/execute_governed_mutation:TMF640"
        ]
        tmf621_tool = _STEP_TOOL_DISPATCH_MAP[step_id][
            "cqrs://transactional-write/execute_governed_mutation:TMF621"
        ]
        if concrete_tool_name == tmf640_tool:
            if (
                selected_branch != "BRANCH_A_SOFT_OPTICAL_DEGRADATION"
                or pre_decision is None
                or not pre_decision.remediation_allowed
            ):
                raise PermissionError(
                    f"Guardrail Interceptor blocked '{tmf640_tool}' in {step_id} "
                    f"(branch={selected_branch}, remediation_allowed={getattr(pre_decision, 'remediation_allowed', False)})."
                )
            allowed_concrete = [tmf640_tool]
        elif concrete_tool_name == tmf621_tool:
            if selected_branch not in ("BRANCH_B_HARD_FIBER_CUT", "BRANCH_C_MAINTENANCE_LOCK"):
                raise PermissionError(
                    f"Tool '{tmf621_tool}' in {step_id} is only authorized for Branch B/C escalation/deferral, not '{selected_branch}'."
                )
            allowed_concrete = [tmf621_tool]
    elif step_id == "STEP_4_POST_VERIFICATION_COMMIT":
        allowed_concrete = [
            _STEP_TOOL_DISPATCH_MAP[step_id][
                "cqrs://transactional-write/commit_validated_graph_triples:POST_GNMI"
            ],
            _STEP_TOOL_DISPATCH_MAP[step_id][
                "cqrs://transactional-write/commit_validated_graph_triples:TMF621"
            ],
        ]

    if concrete_tool_name not in allowed_concrete:
        raise PermissionError(
            f"Closed-world tool whitelist rejected '{concrete_tool_name}' in step '{step_id}'. "
            f"Authorized tools for this step/branch: {allowed_concrete}."
        )
    return catalog_uri


def build_canonical_guardrail_context(
    semantic_context: FederatedCircuitContext,
    live_telemetry: GnmiOpticalTelemetryResponse,
    post_telemetry: Optional[GnmiOpticalTelemetryResponse] = None,
) -> Dict[str, Any]:
    """
    Adapt Step 1 (`FederatedCircuitContext`) and Step 2/4 (`GnmiOpticalTelemetryResponse`)
    into the canonical parameter namespace expected by `skills/guardrails_sop_402.json`.
    """
    post_ok = False
    if post_telemetry is not None:
        post_ok = bool(
            post_telemetry.post_recalibration_verified
            and post_telemetry.rx_power_dbm > semantic_context.rx_optical_power_min_dbm
            and post_telemetry.packet_loss_pct <= semantic_context.max_packet_loss_pct
        )

    return {
        "gnmi_uncached_probed": bool(live_telemetry.uncached_live_probe),
        "uncached_live_probe": bool(live_telemetry.uncached_live_probe),
        "rx_power_dbm": float(live_telemetry.rx_power_dbm),
        "maintenance_lock": bool(live_telemetry.maintenance_lock),
        "packet_loss_pct": float(live_telemetry.packet_loss_pct),
        "post_check_required": post_ok,
        "post_recalibration_verified": bool(
            post_telemetry.post_recalibration_verified if post_telemetry is not None else False
        ),
    }


def _evaluate_rule(
    rule: MachineGuardrailRule, context: Dict[str, Any]
) -> GuardrailRuleEvaluationTrace:
    """Evaluate a single `MachineGuardrailRule` against `context`."""
    op_fn = _OPERATORS.get(rule.operator)
    if op_fn is None:
        raise ValueError(
            f"Unsupported guardrail operator '{rule.operator}' on {rule.guardrail_id}."
        )

    if rule.parameter not in context:
        raise ValueError(
            f"Canonical guardrail context missing parameter '{rule.parameter}' for {rule.guardrail_id}."
        )

    actual = context[rule.parameter]
    passed = bool(op_fn(actual, rule.threshold_value))
    return GuardrailRuleEvaluationTrace(
        guardrail_id=rule.guardrail_id,
        phase=rule.phase,
        parameter=rule.parameter,
        actual_value=actual,
        operator=rule.operator,
        threshold_value=rule.threshold_value,
        passed=passed,
        blocking_action=rule.blocking_action,
    )


def evaluate_pre_execution_guardrails(
    guardrails_spec: CompiledGuardrailsSpec,
    semantic_context: FederatedCircuitContext,
    live_telemetry: GnmiOpticalTelemetryResponse,
) -> PreExecutionGuardrailDecision:
    """
    Invariant 4a — Deterministic Pre-Execution Guardrail Gate (`GR-PRE-01`, `GR-INV-01`, `GR-INV-02`).
    """
    canonical_context = build_canonical_guardrail_context(
        semantic_context=semantic_context,
        live_telemetry=live_telemetry,
    )
    pre_rules = [
        r for r in guardrails_spec.rules if r.phase in ("PRE_CONDITION", "EXECUTION_INVARIANT")
    ]
    traces = [_evaluate_rule(rule, canonical_context) for rule in pre_rules]
    blocking_ids = [t.guardrail_id for t in traces if not t.passed]

    selected_branch: Literal[
        "BRANCH_A_SOFT_OPTICAL_DEGRADATION",
        "BRANCH_B_HARD_FIBER_CUT",
        "BRANCH_C_MAINTENANCE_LOCK",
    ]
    if "GR-INV-01" in blocking_ids:
        selected_branch = "BRANCH_B_HARD_FIBER_CUT"
    elif "GR-INV-02" in blocking_ids:
        selected_branch = "BRANCH_C_MAINTENANCE_LOCK"
    else:
        selected_branch = "BRANCH_A_SOFT_OPTICAL_DEGRADATION"

    return PreExecutionGuardrailDecision(
        remediation_allowed=(len(blocking_ids) == 0),
        selected_branch=selected_branch,
        blocking_guardrail_ids=blocking_ids,
        evaluation_trace=traces,
        canonical_context=canonical_context,
    )


def evaluate_post_execution_guardrail(
    guardrails_spec: CompiledGuardrailsSpec,
    semantic_context: FederatedCircuitContext,
    post_telemetry: GnmiOpticalTelemetryResponse,
) -> PostExecutionGuardrailDecision:
    """
    Invariant 4b — Deterministic Post-Execution Guardrail Gate (`GR-POST-01`).
    """
    canonical_context = build_canonical_guardrail_context(
        semantic_context=semantic_context,
        live_telemetry=post_telemetry,
        post_telemetry=post_telemetry,
    )
    post_rules = [r for r in guardrails_spec.rules if r.phase == "POST_CONDITION"]
    traces = [_evaluate_rule(rule, canonical_context) for rule in post_rules]
    blocking_ids = [t.guardrail_id for t in traces if not t.passed]

    return PostExecutionGuardrailDecision(
        passed=(len(blocking_ids) == 0),
        blocking_guardrail_ids=blocking_ids,
        evaluation_trace=traces,
        post_rx_power_dbm=float(post_telemetry.rx_power_dbm),
        post_packet_loss_pct=float(post_telemetry.packet_loss_pct),
        post_recalibration_verified=bool(post_telemetry.post_recalibration_verified),
    )

