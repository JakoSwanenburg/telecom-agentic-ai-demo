"""
Scenario DT-02b: Deterministic Guardrail Evaluator & Adverse Rejection Test Harness.

Evaluates compiled machine-enforceable guardrails (`CompiledGuardrailsSpec`) against
synthetic adverse violation payloads attempting unauthorized `TMF640_SERVICE_ACTIVATION`
(`recalibrate_optical_ddm_bias`) execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.models import (
    AdverseTestCaseResult,
    AdverseTestSuiteResult,
    CompiledGuardrailsSpec,
    MachineGuardrailRule,
)


def _rule_passes(rule: MachineGuardrailRule, payload: Dict[str, Any]) -> bool:
    """Evaluate a single machine guardrail rule against an execution payload."""
    if rule.parameter not in payload:
        return False
    actual = payload[rule.parameter]
    expected = rule.threshold_value
    op = rule.operator

    if op == "==":
        return actual == expected
    if op == "!=":
        return actual != expected

    if isinstance(actual, bool) or isinstance(expected, bool):
        return False

    actual_num = float(actual)
    expected_num = float(expected)
    if op == ">=":
        return actual_num >= expected_num
    if op == "<=":
        return actual_num <= expected_num
    if op == ">":
        return actual_num > expected_num
    if op == "<":
        return actual_num < expected_num
    return False


def evaluate_guardrails_against_payload(
    guardrails: CompiledGuardrailsSpec,
    target_tool: str,
    payload: Dict[str, Any],
) -> Tuple[bool, Optional[str], str]:
    """
    Evaluate all PRE_CONDITION and EXECUTION_INVARIANT rules matching `target_tool`.
    Returns `(blocked, blocking_guardrail_id, reason)`.
    """
    for rule in guardrails.rules:
        if rule.phase not in {"PRE_CONDITION", "EXECUTION_INVARIANT"}:
            continue
        if rule.target_tool not in {target_tool, "*", "all_mutations"}:
            continue
        if not _rule_passes(rule, payload):
            return (
                True,
                rule.guardrail_id,
                (
                    f"Blocked by {rule.guardrail_id} ({rule.phase}): "
                    f"expected {rule.parameter} {rule.operator} {rule.threshold_value}, "
                    f"got {payload.get(rule.parameter)!r}. Action: {rule.blocking_action}"
                ),
            )
    return False, None, "All applicable pre-condition and invariant guardrails passed."


def run_dt02b_adverse_guardrail_tests(
    guardrails: CompiledGuardrailsSpec,
) -> AdverseTestSuiteResult:
    """
    Execute Scenario DT-02b: 3 synthetic adverse violation payloads attempting
    unauthorized `TMF640_SERVICE_ACTIVATION` (`recalibrate_optical_ddm_bias`) calls.
    """
    adverse_cases = [
        {
            "test_id": "ADV-01",
            "test_name": "Critical LOS Hard Fiber Cut Bypass Attempt",
            "target_tool": "TMF640_SERVICE_ACTIVATION",
            "expected_guardrail": "GR-INV-01",
            "payload": {
                "rx_power_dbm": -31.0,
                "maintenance_lock": False,
                "gnmi_uncached_probed": True,
                "post_check_required": True,
            },
        },
        {
            "test_id": "ADV-02",
            "test_name": "Active Maintenance Window Lock Bypass Attempt",
            "target_tool": "TMF640_SERVICE_ACTIVATION",
            "expected_guardrail": "GR-INV-02",
            "payload": {
                "rx_power_dbm": -26.1,
                "maintenance_lock": True,
                "gnmi_uncached_probed": True,
                "post_check_required": True,
            },
        },
        {
            "test_id": "ADV-03",
            "test_name": "Stale / Un-Probed Telemetry Cache Bypass Attempt",
            "target_tool": "TMF640_SERVICE_ACTIVATION",
            "expected_guardrail": "GR-PRE-01",
            "payload": {
                "rx_power_dbm": -26.1,
                "maintenance_lock": False,
                "gnmi_uncached_probed": False,
                "post_check_required": True,
            },
        },
    ]

    results: List[AdverseTestCaseResult] = []
    for case in adverse_cases:
        blocked, blocking_id, reason = evaluate_guardrails_against_payload(
            guardrails=guardrails,
            target_tool=case["target_tool"],
            payload=case["payload"],
        )
        passed = blocked and (blocking_id == case["expected_guardrail"])
        results.append(
            AdverseTestCaseResult(
                test_id=case["test_id"],
                test_name=case["test_name"],
                target_tool=case["target_tool"],
                payload=case["payload"],
                expected_blocking_guardrail_id=case["expected_guardrail"],
                actual_blocked=blocked,
                actual_blocking_guardrail_id=blocking_id,
                reason=reason,
                passed=passed,
            )
        )

    passed_count = sum(1 for r in results if r.passed)
    return AdverseTestSuiteResult(
        executed_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_tests=len(results),
        passed_tests=passed_count,
        all_passed=(passed_count == len(results)),
        cases=results,
    )

