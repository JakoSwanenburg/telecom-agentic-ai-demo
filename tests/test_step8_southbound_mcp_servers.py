"""
Unit tests for Step 8 (IMP-010): Southbound Operational Telemetry & CQRS Write MCP Servers.
"""

from __future__ import annotations

import shutil
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from rdflib import Dataset, URIRef

from src.config import get_workspace_root, load_config
from src.logger import setup_logger
from src.mcp_servers.common import resolve_ticket_journal_path, save_cqrs_state
from src.mcp_servers.gnmi_telemetry_mcp import execute_probe_optical_ddm_telemetry
from src.mcp_servers.tmf621_trouble_ticket_mcp import execute_create_or_update_trouble_ticket
from src.mcp_servers.tmf640_activation_mcp import execute_recalibrate_optical_ddm_bias
from src.state_manager import initialize_cqrs_state, load_cqrs_state, reset_to_clean_slate


def _make_jwt(sub: str, scopes: str, exp_delta_seconds: int = 300) -> str:
    exp = datetime.now(timezone.utc) + timedelta(seconds=exp_delta_seconds)
    return jwt.encode(
        {"sub": sub, "scp": scopes, "exp": int(exp.timestamp())},
        "test-secret-key-at-least-32-bytes-long-for-hs256",
        algorithm="HS256",
    )


def _prepare_isolated_workspace(tmp_path: Path) -> Path:
    root = get_workspace_root()
    (tmp_path / "shapes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "cqrs_state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "semantic_store").mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "config.yaml", tmp_path / "config.yaml")
    shutil.copy2(
        root / "shapes" / "trouble_ticket_shape.ttl",
        tmp_path / "shapes" / "trouble_ticket_shape.ttl",
    )
    shutil.copy2(
        root / "config" / "mcp_primitives_catalog.json",
        tmp_path / "config" / "mcp_primitives_catalog.json",
    )
    return tmp_path


def test_gnmi_presets_and_tmf640_post_recalibration_transition(tmp_path: Path) -> None:
    ws = _prepare_isolated_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = setup_logger(config, logger_name="test.step8.gnmi", workspace_root=ws)
    initialize_cqrs_state(config, ws)

    # Branch A pre-recalibration
    pre = execute_probe_optical_ddm_telemetry(
        circuit_id="CIR-994821",
        olt_port_id="OLT04-P12",
        uncached=True,
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert pre["rx_power_dbm"] == -26.1
    assert pre["tx_power_dbm"] == -1.2
    assert pre["packet_loss_pct"] == 0.45
    assert pre["jitter_ms"] == 4.2
    assert pre["ber"] == 1.4e-5
    assert pre["maintenance_lock"] is False
    assert pre["post_recalibration_verified"] is False
    assert pre["telemetry_probes_count"] == 1
    assert pre["auth"]["auth_mode"] == "STANDALONE_MCP_BYPASS"

    # Execute TMF640 recalibration
    act = execute_recalibrate_optical_ddm_bias(
        circuit_id="CIR-994821",
        olt_port_id="OLT04-P12",
        cpe_device_id="CPE-ASN-7741",
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert act["executed"] is True
    assert act["status"] == "EXECUTED"
    assert act["tmf640_activations_count"] == 1
    assert act["activation_record"]["activation_id"] == "ACT-640-0001"

    # Branch A post-recalibration
    post = execute_probe_optical_ddm_telemetry(
        circuit_id="CIR-994821",
        olt_port_id="OLT04-P12",
        uncached=True,
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert post["rx_power_dbm"] == -21.4
    assert post["tx_power_dbm"] == -1.0
    assert post["packet_loss_pct"] == 0.01
    assert post["jitter_ms"] == 0.8
    assert post["ber"] == 1.0e-12
    assert post["laser_bias_ma"] == 36.0
    assert post["post_recalibration_verified"] is True

    # Branch B: Hard fiber cut + safety interlock rejection
    state_b = load_cqrs_state(config, ws).model_copy(
        update={"active_telemetry_preset": "branch_b_hard_fiber_cut"}
    )
    save_cqrs_state(state_b, config, ws)

    probe_b = execute_probe_optical_ddm_telemetry(
        circuit_id="CIR-994821", config=config, logger=logger, root_dir=ws
    )
    assert probe_b["rx_power_dbm"] == -38.5
    assert probe_b["packet_loss_pct"] == 99.8
    assert probe_b["los_alarm_active"] is True

    act_b = execute_recalibrate_optical_ddm_bias(
        circuit_id="CIR-994821",
        olt_port_id="OLT04-P12",
        cpe_device_id="CPE-ASN-7741",
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert act_b["executed"] is False
    assert act_b["status"] == "REJECTED_SAFETY_INTERLOCK"
    assert act_b["reason_code"] == "LOS_CRITICAL_CUTOFF_ACTIVE"
    assert act_b["tmf640_activations_count"] == 1

    # Branch C: Maintenance lock + safety interlock rejection
    state_c = load_cqrs_state(config, ws).model_copy(
        update={"active_telemetry_preset": "branch_c_maintenance_lock"}
    )
    save_cqrs_state(state_c, config, ws)

    probe_c = execute_probe_optical_ddm_telemetry(
        circuit_id="CIR-994821", config=config, logger=logger, root_dir=ws
    )
    assert probe_c["maintenance_lock"] is True
    assert probe_c["active_crq_id"] == "MAINT-CRQ-88210"
    assert probe_c["rx_power_dbm"] == -26.1

    act_c = execute_recalibrate_optical_ddm_bias(
        circuit_id="CIR-994821",
        olt_port_id="OLT04-P12",
        cpe_device_id="CPE-ASN-7741",
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert act_c["executed"] is False
    assert act_c["status"] == "REJECTED_SAFETY_INTERLOCK"
    assert act_c["reason_code"] == "MAINTENANCE_WINDOW_LOCK_ACTIVE"
    assert act_c["tmf640_activations_count"] == 1


def test_tmf621_pyshacl_accepts_valid_and_rejects_invalid_tickets(tmp_path: Path) -> None:
    ws = _prepare_isolated_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = setup_logger(config, logger_name="test.step8.tmf621", workspace_root=ws)
    initialize_cqrs_state(config, ws)

    for severity, status in [
        ("MINOR", "RESOLVED_AUTO"),
        ("CRITICAL", "P1_CRITICAL_FIELD_DISPATCH"),
        ("WARNING", "DEFERRED_MAINTENANCE_LOCK"),
    ]:
        res = execute_create_or_update_trouble_ticket(
            circuit_id="CIR-994821",
            customer_id="CUST-ENT-409",
            severity=severity,
            status=status,
            resolution_action="TEST_ACTION",
            summary=f"Ticket for {status}",
            affected_resource_id="OLT04-P12",
            config=config,
            logger=logger,
            root_dir=ws,
        )
        assert res["persisted"] is True
        assert res["status"] == "CREATED"
        assert res["shacl_conforms"] is True

    assert load_cqrs_state(config, ws).tmf621_tickets_count == 3

    # Negative test 1: invalid severity
    bad_sev = execute_create_or_update_trouble_ticket(
        circuit_id="CIR-994821",
        customer_id="CUST-ENT-409",
        severity="BOGUS_SEVERITY",
        status="RESOLVED_AUTO",
        resolution_action="NONE",
        summary="Should fail pySHACL severity constraint",
        affected_resource_id="OLT04-P12",
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert bad_sev["persisted"] is False
    assert bad_sev["status"] == "REJECTED_SHACL_VIOLATION"
    assert bad_sev["shacl_conforms"] is False

    # Negative test 2: missing affected_resource_id (no hidden fallback)
    missing_res = execute_create_or_update_trouble_ticket(
        circuit_id="CIR-994821",
        customer_id="CUST-ENT-409",
        severity="MINOR",
        status="RESOLVED_AUTO",
        resolution_action="NONE",
        summary="Should fail pySHACL minCount on affectedResource",
        affected_resource_id=None,
        config=config,
        logger=logger,
        root_dir=ws,
    )
    assert missing_res["persisted"] is False
    assert missing_res["status"] == "REJECTED_SHACL_VIOLATION"
    assert missing_res["shacl_conforms"] is False
    assert load_cqrs_state(config, ws).tmf621_tickets_count == 3


def test_obo_jwt_scope_enforcement_across_all_three_servers(tmp_path: Path) -> None:
    ws = _prepare_isolated_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    strict_mcp = config.mcp_servers.model_copy(update={"require_obo_jwt": True})
    strict_config = config.model_copy(update={"mcp_servers": strict_mcp})
    logger = setup_logger(strict_config, logger_name="test.step8.jwt", workspace_root=ws)
    initialize_cqrs_state(strict_config, ws)

    expired_jwt = _make_jwt("agent-layer2", "telemetry:read activation:write ticket:write", -60)
    wrong_scope_jwt = _make_jwt("agent-layer2", "semantic:read", 300)
    valid_jwt = _make_jwt("agent-layer2", "telemetry:read activation:write ticket:write", 300)

    # Missing token fails fast when require_obo_jwt=True
    with pytest.raises(PermissionError, match="Missing mandatory OBO JWT"):
        execute_probe_optical_ddm_telemetry(
            circuit_id="CIR-994821", config=strict_config, logger=logger, root_dir=ws
        )

    # Wrong scope fails fast on all 3 servers
    with pytest.raises(PermissionError, match="telemetry:read"):
        execute_probe_optical_ddm_telemetry(
            circuit_id="CIR-994821", obo_jwt=wrong_scope_jwt, config=strict_config, logger=logger, root_dir=ws
        )
    with pytest.raises(PermissionError, match="activation:write"):
        execute_recalibrate_optical_ddm_bias(
            circuit_id="CIR-994821",
            olt_port_id="OLT04-P12",
            cpe_device_id="CPE-ASN-7741",
            obo_jwt=wrong_scope_jwt,
            config=strict_config,
            logger=logger,
            root_dir=ws,
        )
    with pytest.raises(PermissionError, match="ticket:write"):
        execute_create_or_update_trouble_ticket(
            circuit_id="CIR-994821",
            customer_id="CUST-ENT-409",
            severity="MINOR",
            status="RESOLVED_AUTO",
            resolution_action="TEST",
            summary="Test",
            affected_resource_id="OLT04-P12",
            obo_jwt=wrong_scope_jwt,
            config=strict_config,
            logger=logger,
            root_dir=ws,
        )

    # Expired token fails fast
    with pytest.raises(PermissionError, match="expired"):
        execute_probe_optical_ddm_telemetry(
            circuit_id="CIR-994821", obo_jwt=expired_jwt, config=strict_config, logger=logger, root_dir=ws
        )

    # Valid OBO JWT succeeds on all 3 servers
    res_g = execute_probe_optical_ddm_telemetry(
        circuit_id="CIR-994821", obo_jwt=valid_jwt, config=strict_config, logger=logger, root_dir=ws
    )
    assert res_g["auth"]["obo_jwt_verified"] is True
    assert res_g["auth"]["obo_subject"] == "agent-layer2"

    res_a = execute_recalibrate_optical_ddm_bias(
        circuit_id="CIR-994821",
        olt_port_id="OLT04-P12",
        cpe_device_id="CPE-ASN-7741",
        obo_jwt=valid_jwt,
        config=strict_config,
        logger=logger,
        root_dir=ws,
    )
    assert res_a["auth"]["obo_jwt_verified"] is True

    res_t = execute_create_or_update_trouble_ticket(
        circuit_id="CIR-994821",
        customer_id="CUST-ENT-409",
        severity="MINOR",
        status="RESOLVED_AUTO",
        resolution_action="TEST",
        summary="Test",
        affected_resource_id="OLT04-P12",
        obo_jwt=valid_jwt,
        config=strict_config,
        logger=logger,
        root_dir=ws,
    )
    assert res_t["auth"]["obo_jwt_verified"] is True


def test_virtual_ib_graph_remains_zero_triples_and_dt00_cleans_step8_artifacts(tmp_path: Path) -> None:
    root = get_workspace_root()
    trig_path = root / "data" / "semantic_store" / "knowledge_graph.trig"
    if trig_path.exists():
        ds = Dataset()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
            ds.parse(str(trig_path), format="trig")
            virtual_graph = ds.graph(URIRef("urn:telco:graph:virtual:ib"))
            assert len(virtual_graph) == 0

    ws = _prepare_isolated_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = setup_logger(config, logger_name="test.step8.dt00", workspace_root=ws)
    initialize_cqrs_state(config, ws)

    execute_create_or_update_trouble_ticket(
        circuit_id="CIR-994821",
        customer_id="CUST-ENT-409",
        severity="MINOR",
        status="RESOLVED_AUTO",
        resolution_action="TEST",
        summary="To be wiped by DT-00",
        affected_resource_id="OLT04-P12",
        config=config,
        logger=logger,
        root_dir=ws,
    )
    journal_path = resolve_ticket_journal_path(config, ws)
    assert journal_path.exists()

    report_html = ws / Path(config.cqrs_action_plane.step8_verification_report_path)
    report_html.parent.mkdir(parents=True, exist_ok=True)
    report_html.write_text("<html></html>", encoding="utf-8")
    report_html.with_suffix(".md").write_text("# report", encoding="utf-8")

    reset_to_clean_slate(config, logger, workspace_root=ws)
    assert not journal_path.exists()
    assert not report_html.exists()
    assert not report_html.with_suffix(".md").exists()
