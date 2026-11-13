# Implementation Plan — `IMP-011`

## 1. Unique Reference ID
`IMP-011` (Step 9 — Stage 3: Layer 2 Skill-Governed Assurance Specialist Agent, Strict Skill/Tool/Source Sandbox, Pre-Execution Guardrail Interceptor & Runtime Scenarios `RT-01` Branch A, `RT-02` Branch B, `RT-03` Branch C)

## 2. Objective & Scope
Implement the Layer 2 Skill-Governed Assurance Specialist Agent (`src/layer2/`) that executes `SOP-ASSUR-402` (`UC-001`) strictly inside the compiled `skills/skill_sop_402.yaml` and `skills/guardrails_sop_402.json` sandbox, with deterministic Python guardrail interception, Gemini-driven NL orchestration & grounded engineering narrative synthesis (`src/llm_client.py`), and end-to-end verification across `RT-01`, `RT-02`, and `RT-03`:
1. **Fail-Fast Prerequisites:** Verify Track B (`tbox_sid_etom.ttl`, `knowledge_graph.trig` with `0` persisted `virtual:ib` triples, `cmdb_r2rml.ttl`, `stored_sparql_templates.yaml`) and Track A (`skills/skill_sop_402.yaml`, `skills/guardrails_sop_402.json` — `SYS-01` Element 6 `VERIFIED_LOCKED`).
2. **Strict Layer 2 Sandbox & Guardrail Interceptor (`src/layer2/guardrail_interceptor.py`):**
   - **Invariant 1 (`validate_step_transition`):** Enforce exact ordered execution of `workflow_steps` from `skills/skill_sop_402.yaml` (no skipping, reordering, or extra steps).
   - **Invariant 2 (`validate_tool_invocation`):** Enforce closed-world tool whitelist from `skills/skill_sop_402.yaml` (`bound_mcp_primitives`, per-step `mcp_primitive_uri`, and `branch_routing`), mapping generic catalog URIs to Step 6/8 concrete MCP server functions and deterministically rejecting (`PermissionError`) any unbound tool or `tmf640_activation_mcp` invocation outside Branch A Step 3.
   - **Invariant 3 (Zero Unspecified External Sources):** `src/layer2/` has zero imports or file reads of `data/raw_sources/` or `mappings/cmdb_r2rml.ttl`.
   - **Invariant 4 (`evaluate_pre_execution_guardrails` & `evaluate_post_execution_guardrail`):** Build a Canonical Guardrail Evaluation Context from Step 1 (`FederatedCircuitContext`) and Step 2/4 (`GnmiOpticalTelemetryResponse`) outputs, dynamically evaluate `skills/guardrails_sop_402.json` (`GR-PRE-01`, `GR-INV-01`, `GR-INV-02`, `GR-POST-01`), and deterministically gate `tmf640` / `tmf621` execution.
3. **Skill-Governed Assurance Specialist Agent (`src/layer2/assurance_specialist_agent.py` & `prompts/layer2_assurance_agent_prompt.md`):**
   - Orchestrate Steps 1–4 across `RT-01` (`branch_a_soft_degradation`), `RT-02` (`branch_b_hard_fiber_cut`), and `RT-03` (`branch_c_maintenance_lock`) using `resolve_model_for_component(config, "layer2_assurance_agent")` (`gemini-3.8-flash`) via `src/llm_client.py` (zero heuristic fallback) to produce `Layer2OrchestrationAndNarrativeProposal`, gated by Python `guardrail_interceptor.py`.
4. **CLI Runner & `DT-00` Reset:**
   - `scripts/run_rt01_rt03_layer2_branches.py` (`--scenario {RT-01,RT-02,RT-03,all}`, `--circuit-id`, `--keep-state`) resetting CQRS state cleanly before each branch and back to `branch_a_soft_degradation` at the end unless `--keep-state` is passed, writing `reports/rt01_rt03_layer2_execution_report.html` (`.md`).
   - Update `DT-00` (`src/state_manager.py`) to remove `reports/rt01_rt03_layer2_execution_report.*`.

## 3. Key Design Decisions (Locked)
- **Catalog URI -> Concrete MCP Server Mapping:** Enforced in `guardrail_interceptor.py` directly from `skill_sop_402.yaml` (`STEP_1` -> `semantic_read_mcp.query_knowledge_fabric`, `STEP_2` -> `gnmi_telemetry_mcp.probe_optical_ddm_telemetry`, `STEP_3` -> `tmf640_activation_mcp.recalibrate_optical_ddm_bias` [Branch A only] or `tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket` [Branch B/C], `STEP_4` -> post-check `gnmi_telemetry_mcp` + `tmf621_trouble_ticket_mcp`).
- **Canonical Guardrail Evaluation Context:** Layer 2 normalizes MCP tool output fields (`uncached_live_probe` -> `gnmi_uncached_probed`, `post_recalibration_verified` + optical/loss SLA thresholds -> `post_check_required`) without modifying locked Gate 3 files or Step 8 MCP contracts.
- **Clean State Between Scenarios:** `run_rt01_rt03_layer2_branches.py` resets `cqrs_runtime_state.json` before each scenario and restores clean `branch_a_soft_degradation` at completion unless `--keep-state` is passed.

## 4. Step-by-Step Implementation Plan
1. Update `config.yaml` (`ai.component_models.layer2_assurance_agent`, `layer2_worker_and_sop.agent_prompt_template_path`, `layer2_worker_and_sop.runtime_branches_report_path`) and `src/models.py` (`Layer2WorkerAndSopSettings` + Step 9 Pydantic v2 models).
2. Create `prompts/layer2_assurance_agent_prompt.md`.
3. Create `src/layer2/__init__.py`, `src/layer2/guardrail_interceptor.py`, and `src/layer2/assurance_specialist_agent.py`.
4. Update `src/state_manager.py` (`DT-00` cleanup) and `README.md`.
5. Create `scripts/run_rt01_rt03_layer2_branches.py` and `tests/test_step9_layer2_assurance_agent.py`.
6. Run `pytest -v -W error::DeprecationWarning -W error::FutureWarning`, `scripts/run_rt01_rt03_layer2_branches.py --scenario all`, and `scripts/inspect_demo_state.py`.

---

## Implementation Summary (Gate 5)

- **Status:** Completed & Verified
- **Files Created:**
  - `prompts/layer2_assurance_agent_prompt.md`
  - `src/layer2/__init__.py`
  - `src/layer2/guardrail_interceptor.py` (`load_compiled_skill_and_guardrails`, `validate_step_transition`, `validate_tool_invocation`, `build_canonical_guardrail_context`, `evaluate_pre_execution_guardrails`, `evaluate_post_execution_guardrail`)
  - `src/layer2/assurance_specialist_agent.py` (`run_layer2_assurance_workflow` with fail-fast Track A/B prerequisites, Gemini `layer2_assurance_agent` orchestration, and deterministic guardrail gating)
  - `scripts/run_rt01_rt03_layer2_branches.py`
  - `tests/test_step9_layer2_assurance_agent.py`
  - `reports/rt01_rt03_layer2_execution_report.html` & `.md`
- **Files Modified:**
  - `config.yaml` (`ai.component_models.layer2_assurance_agent`, `layer2_worker_and_sop.agent_prompt_template_path`, `layer2_worker_and_sop.runtime_branches_report_path`)
  - `src/models.py` (`Layer2WorkerAndSopSettings` + Step 9 Pydantic v2 models)
  - `src/state_manager.py` (`DT-00` cleans `reports/rt01_rt03_layer2_execution_report.*`)
  - `README.md` (added Step 9 execution instructions)
- **Deviations (Gate 4):** None.
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **51 passed** (0 failures, 0 `DeprecationWarning`, 0 `FutureWarning`).
  - Live `.\.venv\Scripts\python.exe scripts\run_rt01_rt03_layer2_branches.py --scenario all`:
    - `RT-01` (`branch_a_soft_degradation`): `BRANCH_A_SOFT_OPTICAL_DEGRADATION`, `tmf640_calls=1` (`ACT-640-0001`), post-check `-21.4 dBm` / `0.01%` loss (`GR-POST-01` passed), `TT-621-0001` (`MINOR / RESOLVED_AUTO`, `pySHACL conforms=True`).
    - `RT-02` (`branch_b_hard_fiber_cut`): `BRANCH_B_HARD_FIBER_CUT`, `GR-INV-01` blocked `tmf640` (`0` calls), `TT-621-0002` (`CRITICAL / OPEN_DISPATCHED`, `pySHACL conforms=True`).
    - `RT-03` (`branch_c_maintenance_lock`): `BRANCH_C_MAINTENANCE_LOCK`, `GR-INV-02` blocked `tmf640` (`0` calls), `TT-621-0003` (`WARNING / DEFERRED_MAINTENANCE`, `pySHACL conforms=True`).
  - `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: All 7 `SYS-01` elements verified (`Element 2: BOUND_ZERO_COPY` with `0` persisted triples, `Element 6: VERIFIED_LOCKED`, `Element 7: ACTIVE_PRESET` with `branch_a_soft_degradation`, `0` locks, `3/3` tokens).

