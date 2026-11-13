"""
Southbound FastMCP Server: `tmf640-activation-mcp` (Step 8 / IMP-010).

Exposes `recalibrate_optical_ddm_bias` with deterministic hardware safety interlocks
against critical LOS cutoffs (`branch_b_hard_fiber_cut`) and active maintenance locks
(`branch_c_maintenance_lock`).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer

from src.mcp_servers.common import resolve_mcp_context, save_cqrs_state, utc_now_iso, validate_obo_jwt
from src.models import (
    AppConfig,
    Tmf640ActivationRecord,
    Tmf640ActivationResponse,
)
from src.state_manager import load_cqrs_state

mcp = MCPServer("tmf640-activation-mcp")


def execute_recalibrate_optical_ddm_bias(
    circuit_id: str,
    olt_port_id: str,
    cpe_device_id: str,
    target_rx_dbm: float = -21.0,
    reason: str = "SOP-ASSUR-402 Soft Attenuation Recalibration",
    obo_jwt: Optional[str] = None,
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    root_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Core implementation for `recalibrate_optical_ddm_bias`."""
    for field_name, val in (
        ("circuit_id", circuit_id),
        ("olt_port_id", olt_port_id),
        ("cpe_device_id", cpe_device_id),
        ("reason", reason),
    ):
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{field_name} must be a non-empty string.")

    workspace_root, active_config, active_logger = resolve_mcp_context(
        config=config,
        logger=logger,
        root_dir=root_dir,
        logger_name="telco_agent.mcp.tmf640_activation",
    )
    auth = validate_obo_jwt(
        obo_jwt=obo_jwt,
        required_scope=active_config.mcp_servers.tmf640_activation.required_obo_scope,
        require_jwt=active_config.mcp_servers.require_obo_jwt,
    )

    state = load_cqrs_state(active_config, workspace_root)
    preset = state.active_telemetry_preset
    clean_circuit = circuit_id.strip()
    clean_olt = olt_port_id.strip()
    clean_cpe = cpe_device_id.strip()

    if preset == "branch_b_hard_fiber_cut":
        explanation = (
            f"Safety interlock refused DDM bias recalibration on {clean_circuit} ({clean_olt}): "
            "active optical Rx power (-38.5 dBm) is below critical LOS cutoff (-27.5 dBm) under "
            "preset 'branch_b_hard_fiber_cut'. Hardware state was not modified."
        )
        active_logger.warning("tmf640_activation_mcp | %s", explanation)
        return Tmf640ActivationResponse(
            executed=False,
            status="REJECTED_SAFETY_INTERLOCK",
            reason_code="LOS_CRITICAL_CUTOFF_ACTIVE",
            explanation=explanation,
            circuit_id=clean_circuit,
            olt_port_id=clean_olt,
            cpe_device_id=clean_cpe,
            telemetry_preset=preset,
            activation_record=None,
            tmf640_activations_count=state.tmf640_activations_count,
            auth=auth,
        ).model_dump()

    if preset == "branch_c_maintenance_lock":
        explanation = (
            f"Safety interlock refused DDM bias recalibration on {clean_circuit} ({clean_olt}): "
            "active maintenance window lock (MAINT-CRQ-88210) is engaged under preset "
            "'branch_c_maintenance_lock'. Hardware state was not modified."
        )
        active_logger.warning("tmf640_activation_mcp | %s", explanation)
        return Tmf640ActivationResponse(
            executed=False,
            status="REJECTED_SAFETY_INTERLOCK",
            reason_code="MAINTENANCE_WINDOW_LOCK_ACTIVE",
            explanation=explanation,
            circuit_id=clean_circuit,
            olt_port_id=clean_olt,
            cpe_device_id=clean_cpe,
            telemetry_preset=preset,
            activation_record=None,
            tmf640_activations_count=state.tmf640_activations_count,
            auth=auth,
        ).model_dump()

    new_count = state.tmf640_activations_count + 1
    activation_record = Tmf640ActivationRecord(
        activation_id=f"ACT-640-{new_count:04d}",
        executed_at_utc=utc_now_iso(),
        circuit_id=clean_circuit,
        olt_port_id=clean_olt,
        cpe_device_id=clean_cpe,
        pre_rx_power_dbm=-26.1,
        target_rx_dbm=float(target_rx_dbm),
        post_rx_power_dbm=-21.4,
        pre_laser_bias_ma=42.5,
        post_laser_bias_ma=36.0,
        reason=reason.strip(),
    )
    updated_recal_map = dict(state.circuit_recalibrated)
    updated_recal_map[clean_circuit] = True
    updated_records = list(state.recalibration_executions) + [activation_record]

    updated_state = state.model_copy(
        update={
            "tmf640_activations_count": new_count,
            "recalibration_executions": updated_records,
            "circuit_recalibrated": updated_recal_map,
        }
    )
    save_cqrs_state(updated_state, active_config, workspace_root)

    explanation = (
        f"Executed TMF640 optical DDM bias recalibration {activation_record.activation_id} on "
        f"{clean_circuit} ({clean_olt} -> {clean_cpe}); Rx power restored from -26.1 dBm to -21.4 dBm."
    )
    active_logger.info(
        "tmf640_activation_mcp | %s | activations=%d | auth=%s",
        explanation,
        new_count,
        auth.auth_mode,
    )
    return Tmf640ActivationResponse(
        executed=True,
        status="EXECUTED",
        reason_code=None,
        explanation=explanation,
        circuit_id=clean_circuit,
        olt_port_id=clean_olt,
        cpe_device_id=clean_cpe,
        telemetry_preset=preset,
        activation_record=activation_record,
        tmf640_activations_count=new_count,
        auth=auth,
    ).model_dump()


@mcp.tool()
def recalibrate_optical_ddm_bias(
    circuit_id: str,
    olt_port_id: str,
    cpe_device_id: str,
    target_rx_dbm: float = -21.0,
    reason: str = "SOP-ASSUR-402 Soft Attenuation Recalibration",
    obo_jwt: Optional[str] = None,
) -> Dict[str, Any]:
    """Recalibrate optical DDM laser bias on an OLT/CPE pair via TMF640 Service Activation."""
    return execute_recalibrate_optical_ddm_bias(
        circuit_id=circuit_id,
        olt_port_id=olt_port_id,
        cpe_device_id=cpe_device_id,
        target_rx_dbm=target_rx_dbm,
        reason=reason,
        obo_jwt=obo_jwt,
    )


if __name__ == "__main__":
    mcp.run()

