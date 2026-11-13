# Implementation Plan — `IMP-010`

## 1. Unique Reference ID
`IMP-010` (Step 8 — Southbound Operational Telemetry & CQRS Write MCP Servers: `gnmi_telemetry_mcp.py`, `tmf640_activation_mcp.py`, `tmf621_trouble_ticket_mcp.py`)

## 2. Objective & Scope
Implement the 3 Southbound Operational & CQRS MCP servers using `mcp.server.mcpserver.MCPServer`, strict Pydantic v2 contracts, configurable PyJWT OBO token validation, deterministic telemetry presets with post-recalibration state transitions, safety interlock domain rejections, and pre-commit `pySHACL` validation against `shapes/trouble_ticket_shape.ttl`:
1. **Shared MCP OBO Auth & CQRS State Helpers (`src/mcp_servers/common.py`):**
   - Reusable `validate_obo_jwt(...)` helper enforcing `require_obo_jwt` and per-tool scopes (`telemetry:read`, `activation:write`, `ticket:write`).
   - Reusable atomic CQRS state load/save helpers over `data/cqrs_state/cqrs_runtime_state.json` and `data/cqrs_state/tmf621_ticket_journal.json`.
2. **Southbound gNMI Optical Telemetry MCP Server (`src/mcp_servers/gnmi_telemetry_mcp.py`):**
   - Exposes `probe_optical_ddm_telemetry(circuit_id, olt_port_id=None, uncached=True, obo_jwt=None) -> dict`.
   - Returns exact `GnmiOpticalTelemetryResponse` metrics for `branch_a_soft_degradation`, `branch_b_hard_fiber_cut`, `branch_c_maintenance_lock`, and transitions to recovered post-recalibration telemetry (`-21.4 dBm`, `0.01%` loss, `post_recalibration_verified=True`) when `circuit_recalibrated[circuit_id]` is `True`.
   - Increments `telemetry_probes_count` and records `last_telemetry_probe_utc` without mutating any semantic graph files.
3. **Southbound TMF640 Service Activation MCP Server (`src/mcp_servers/tmf640_activation_mcp.py`):**
   - Exposes `recalibrate_optical_ddm_bias(circuit_id, olt_port_id, cpe_device_id, target_rx_dbm=-21.0, reason=..., obo_jwt=None) -> dict`.
   - Returns structured domain rejection (`Tmf640ActivationResponse` with `executed=False`, `status="REJECTED_SAFETY_INTERLOCK"`, `reason_code="LOS_CRITICAL_CUTOFF_ACTIVE"` / `"MAINTENANCE_WINDOW_LOCK_ACTIVE"`) when preset is `branch_b_hard_fiber_cut` or `branch_c_maintenance_lock`.
   - On valid execution (`branch_a_soft_degradation`), increments `tmf640_activations_count`, appends `Tmf640ActivationRecord`, and sets `circuit_recalibrated[circuit_id] = True`.
4. **Southbound TMF621 Trouble Ticket MCP Server (`src/mcp_servers/tmf621_trouble_ticket_mcp.py`):**
   - Exposes `create_or_update_trouble_ticket(circuit_id, customer_id, severity, status, resolution_action, summary, affected_resource_id=None, external_ticket_id=None, obo_jwt=None) -> dict`.
   - Constructs an in-memory `rdflib.Graph` for `tmf:TroubleTicket` and validates via `pyshacl.validate()` against `shapes/trouble_ticket_shape.ttl` before persisting.
   - When `pySHACL` fails (`conforms == False`), returns structured `Tmf621TicketResponse` (`persisted=False`, `status="REJECTED_SHACL_VIOLATION"`, `shacl_conforms=False`, `explanation=<results_text>`) without mutating disk state.
   - When `pySHACL` passes, persists to `data/cqrs_state/tmf621_ticket_journal.json` and updates `tmf621_tickets_count` / `tickets_created` in `cqrs_runtime_state.json`.
5. **Verification Harness, `DT-00` Reset & Unit Tests:**
   - `scripts/run_step8_mcp_servers_verification.py`: exercises all 3 servers across all 3 presets + `pySHACL` negative test, writes `reports/step8_mcp_cqrs_verification_report.html` (`.md`), and resets `data/cqrs_state/` unless `--keep-state` is passed.
   - `src/state_manager.py`: `DT-00` cleans `tmf621_ticket_journal.json` and `step8_mcp_cqrs_verification_report.*`.
   - `tests/test_step8_southbound_mcp_servers.py`: comprehensive unit tests.

## 3. Key Design Decisions (Locked)
- **Structured `config.yaml`:**
  - `cqrs_action_plane`: shared CQRS state, `ticket_journal_path`, preset, rate/mutex settings, and `step8_verification_report_path`.
  - `mcp_servers`: `require_obo_jwt: false`, `gnmi_telemetry.required_obo_scope: "telemetry:read"`, `tmf640_activation.required_obo_scope: "activation:write"`, `tmf621_trouble_ticket.required_obo_scope: "ticket:write"`, `tmf621_trouble_ticket.shacl_shape_path: "shapes/trouble_ticket_shape.ttl"`.
- **100% Deterministic Tool Behavior:** `tmf621_trouble_ticket_mcp.py` requires explicit `affected_resource_id` (no hidden lookup or fallback URI) and lets `pySHACL` fail deterministically if missing/invalid.
- **Structured Domain Rejections:** Safety interlocks and `pySHACL` violations return structured Pydantic responses (`REJECTED_SAFETY_INTERLOCK`, `REJECTED_SHACL_VIOLATION`), reserving `PermissionError` strictly for `obo_jwt` auth failures.

## 4. Step-by-Step Implementation Plan
1. Update `config.yaml` (`cqrs_action_plane` + `mcp_servers`) and `src/models.py` (`CqrsActionPlaneSettings`, `McpServersSettings`, `AppConfig`, `CqrsRuntimeState`, Step 8 response/record models).
2. Create `src/mcp_servers/common.py` and refactor/share OBO JWT validation cleanly across `src/mcp_servers/`.
3. Implement `src/mcp_servers/gnmi_telemetry_mcp.py`, `src/mcp_servers/tmf640_activation_mcp.py`, and `src/mcp_servers/tmf621_trouble_ticket_mcp.py`.
4. Update `src/state_manager.py` (`DT-00` cleanup) and `README.md`.
5. Create `scripts/run_step8_mcp_servers_verification.py` and `tests/test_step8_southbound_mcp_servers.py`.
6. Run `pytest -v -W error::DeprecationWarning -W error::FutureWarning`, `scripts/run_step8_mcp_servers_verification.py`, and `scripts/inspect_demo_state.py`.

---

## Implementation Summary (Gate 5)

- **Status:** Completed & Verified
- **Files Created:**
  - `src/mcp_servers/common.py` (`validate_obo_jwt`, `resolve_mcp_context`, atomic `save_cqrs_state`, `load_ticket_journal`, `save_ticket_journal`)
  - `src/mcp_servers/gnmi_telemetry_mcp.py` (`MCPServer("gnmi-telemetry-mcp")`, `probe_optical_ddm_telemetry`)
  - `src/mcp_servers/tmf640_activation_mcp.py` (`MCPServer("tmf640-activation-mcp")`, `recalibrate_optical_ddm_bias` with `REJECTED_SAFETY_INTERLOCK` domain rejections)
  - `src/mcp_servers/tmf621_trouble_ticket_mcp.py` (`MCPServer("tmf621-trouble-ticket-mcp")`, `create_or_update_trouble_ticket` with pre-commit `pySHACL` validation against `shapes/trouble_ticket_shape.ttl`)
  - `scripts/run_step8_mcp_servers_verification.py`
  - `tests/test_step8_southbound_mcp_servers.py`
  - `reports/step8_mcp_cqrs_verification_report.html` & `.md`
- **Files Modified:**
  - `config.yaml` (updated `cqrs_action_plane`, added dedicated `mcp_servers` section)
  - `src/models.py` (`CqrsActionPlaneSettings`, `McpServersSettings`, `AppConfig`, `CqrsRuntimeState`, Step 8 Pydantic v2 response/journal models)
  - `src/mcp_servers/semantic_read_mcp.py` (refactored `_validate_obo_jwt` to reuse `src.mcp_servers.common.validate_obo_jwt`)
  - `src/state_manager.py` (`DT-00` cleans `tmf621_ticket_journal.json` and `step8_mcp_cqrs_verification_report.*`)
  - `README.md` (added Step 8 verification instructions)
- **Deviations (Gate 4):** None.
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **47 passed** (0 failures, 0 `DeprecationWarning`, 0 `FutureWarning`).
  - `.\.venv\Scripts\python.exe scripts\run_step8_mcp_servers_verification.py`: **11/11 checks passed** across `branch_a_soft_degradation`, `branch_b_hard_fiber_cut`, `branch_c_maintenance_lock`, and `pySHACL` negative validation (`State Reset: True`).
  - `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: All 7 `SYS-01` elements verified (`Element 2: BOUND_ZERO_COPY` with `0` persisted triples, `Element 6: VERIFIED_LOCKED`, `Element 7: ACTIVE_PRESET` with `branch_a_soft_degradation`, `0` locks, `3/3` tokens).
