"""
Southbound FastMCP Server: `gnmi-telemetry-mcp` (Step 8 / IMP-010).

Exposes `probe_optical_ddm_telemetry` for live uncached gNMI optical DDM probes
backed by `data/cqrs_state/cqrs_runtime_state.json` without mutating semantic graphs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer

from src.mcp_servers.common import resolve_mcp_context, save_cqrs_state, utc_now_iso, validate_obo_jwt
from src.models import AppConfig, GnmiOpticalTelemetryResponse
from src.state_manager import load_cqrs_state

mcp = MCPServer("gnmi-telemetry-mcp")

_PRESET_TELEMETRY_METRICS: Dict[str, Dict[str, Any]] = {
    "branch_a_soft_degradation": {
        "rx_power_dbm": -26.1,
        "tx_power_dbm": -1.2,
        "packet_loss_pct": 0.45,
        "jitter_ms": 4.2,
        "ber": 1.4e-5,
        "laser_bias_ma": 42.5,
        "temperature_c": 44.0,
        "los_alarm_active": False,
        "maintenance_lock": False,
        "active_crq_id": None,
        "post_recalibration_verified": False,
    },
    "branch_a_recovered": {
        "rx_power_dbm": -21.4,
        "tx_power_dbm": -1.0,
        "packet_loss_pct": 0.01,
        "jitter_ms": 0.8,
        "ber": 1.0e-12,
        "laser_bias_ma": 36.0,
        "temperature_c": 44.0,
        "los_alarm_active": False,
        "maintenance_lock": False,
        "active_crq_id": None,
        "post_recalibration_verified": True,
    },
    "branch_b_hard_fiber_cut": {
        "rx_power_dbm": -38.5,
        "tx_power_dbm": -1.1,
        "packet_loss_pct": 99.8,
        "jitter_ms": 0.0,
        "ber": 1.0,
        "laser_bias_ma": 45.0,
        "temperature_c": 43.5,
        "los_alarm_active": True,
        "maintenance_lock": False,
        "active_crq_id": None,
        "post_recalibration_verified": False,
    },
    "branch_c_maintenance_lock": {
        "rx_power_dbm": -26.1,
        "tx_power_dbm": -1.2,
        "packet_loss_pct": 0.45,
        "jitter_ms": 4.1,
        "ber": 1.4e-5,
        "laser_bias_ma": 42.5,
        "temperature_c": 44.0,
        "los_alarm_active": False,
        "maintenance_lock": True,
        "active_crq_id": "MAINT-CRQ-88210",
        "post_recalibration_verified": False,
    },
}


def execute_probe_optical_ddm_telemetry(
    circuit_id: str,
    olt_port_id: Optional[str] = None,
    uncached: bool = True,
    obo_jwt: Optional[str] = None,
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    root_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Core implementation for `probe_optical_ddm_telemetry`."""
    if not circuit_id or not circuit_id.strip():
        raise ValueError("circuit_id must be a non-empty string.")

    workspace_root, active_config, active_logger = resolve_mcp_context(
        config=config,
        logger=logger,
        root_dir=root_dir,
        logger_name="telco_agent.mcp.gnmi_telemetry",
    )
    auth = validate_obo_jwt(
        obo_jwt=obo_jwt,
        required_scope=active_config.mcp_servers.gnmi_telemetry.required_obo_scope,
        require_jwt=active_config.mcp_servers.require_obo_jwt,
    )

    state = load_cqrs_state(active_config, workspace_root)
    preset = state.active_telemetry_preset
    recalibrated = bool(state.circuit_recalibrated.get(circuit_id, False))

    profile_key = (
        "branch_a_recovered"
        if preset == "branch_a_soft_degradation" and recalibrated
        else preset
    )
    metrics = _PRESET_TELEMETRY_METRICS[profile_key]

    probed_at = utc_now_iso()
    new_count = state.telemetry_probes_count + 1
    updated_state = state.model_copy(
        update={
            "telemetry_probes_count": new_count,
            "last_telemetry_probe_utc": probed_at,
        }
    )
    save_cqrs_state(updated_state, active_config, workspace_root)

    response = GnmiOpticalTelemetryResponse(
        circuit_id=circuit_id.strip(),
        olt_port_id=olt_port_id.strip() if isinstance(olt_port_id, str) and olt_port_id.strip() else None,
        telemetry_preset=preset,
        probed_at_utc=probed_at,
        uncached_live_probe=bool(uncached),
        telemetry_probes_count=new_count,
        auth=auth,
        **metrics,
    )
    active_logger.info(
        "gnmi_telemetry_mcp | circuit=%s | preset=%s | rx_dbm=%.1f | loss=%.2f%% | post_recal=%s | probes=%d | auth=%s",
        response.circuit_id,
        response.telemetry_preset,
        response.rx_power_dbm,
        response.packet_loss_pct,
        response.post_recalibration_verified,
        response.telemetry_probes_count,
        auth.auth_mode,
    )
    return response.model_dump()


@mcp.tool()
def probe_optical_ddm_telemetry(
    circuit_id: str,
    olt_port_id: Optional[str] = None,
    uncached: bool = True,
    obo_jwt: Optional[str] = None,
) -> Dict[str, Any]:
    """Probe live optical DDM telemetry (rx/tx dBm, loss, jitter, BER, maintenance lock) via gNMI."""
    return execute_probe_optical_ddm_telemetry(
        circuit_id=circuit_id,
        olt_port_id=olt_port_id,
        uncached=uncached,
        obo_jwt=obo_jwt,
    )


if __name__ == "__main__":
    mcp.run()

