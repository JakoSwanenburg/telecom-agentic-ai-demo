# Implementation Plan — `IMP-009`

## 1. Unique Reference ID
`IMP-009` (Step 7 — Track A `DT-02a` SOP-to-Skill Compiler, `DT-02b` Adverse Guardrail Test Harness & Two-Phase Mandatory HITL Gate 3 Lock)

## 2. Objective & Scope
Implement Track A (`src/track_a/`) to dynamically introspect `SOP_NOC_Master_Assurance_Runbook_v2026.md`, `uc001_use_case_charter.md`, `tbox_sid_etom.ttl`, and `config/mcp_primitives_catalog.json`:
1. Detect `PARTIAL_GAP` MCP catalog states (`enable_tmf621_dispatch_primitive` / disabled primitives), write a complete Functional Tool Specification to `reports/missing_primitive_spec.json` + gap diagnostic in `reports/hitl_sop_skill_review.html` (`.md`), and fail fast with `RuntimeError`.
2. When the MCP catalog is `COMPLETE`, invoke Gemini (`track_a_sop_compiler`) via `src/llm_client.py` (zero heuristic fallback) to compile `skills/skill_sop_402.yaml` and `skills/guardrails_sop_402.json`, staged in `skills/gate3_candidate_sop_402.json` during `--mode candidate` and materialized upon `--mode approve`.
3. Execute `DT-02b` adverse guardrail tests (`ADV-01`, `ADV-02`, `ADV-03`) against the compiled guardrails (`GR-PRE-01`, `GR-INV-01`, `GR-INV-02`, `GR-POST-01`), requiring `3/3` deterministic blocks before Gate 3 approval.
4. Update `SYS-01` Element 6 (`EMPTY` -> `CANDIDATE_COMPILED (Awaiting HITL Gate 3)` -> `VERIFIED_LOCKED`) and `DT-00` cleanup.

## 3. Key Design Decisions
- **Track A / Track B Separation:** Stage Gate 3 candidate in `skills/gate3_candidate_sop_402.json` (never in `data/semantic_store/`).
- **Paths in `config.yaml` (`layer2_worker_and_sop`):** Keep `skills/skill_sop_402.yaml`, `skills/guardrails_sop_402.json`, `reports/hitl_sop_skill_review.html`, `reports/missing_primitive_spec.json`, and add `gate3_candidate_proposal_path: "skills/gate3_candidate_sop_402.json"` and `sop_compiler_prompt_template_path: "prompts/track_a_sop_compiler_prompt.md"`.
- **100% Document-Independent Python Code:** Zero hardcoded SOP procedure IDs, optical dBm numbers, or distractor section titles in `src/track_a/sop_to_skill_compiler.py`.

## 4. Step-by-Step Implementation Plan
1. Update `config.yaml` and `src/models.py` (`Layer2WorkerAndSopSettings` + Step 7 Pydantic v2 models).
2. Create `prompts/track_a_sop_compiler_prompt.md`.
3. Create `src/track_a/__init__.py`, `src/track_a/adverse_test_harness.py`, and `src/track_a/sop_to_skill_compiler.py`.
4. Update `src/state_inspector.py` (Element 6: `EMPTY`, `CANDIDATE_COMPILED (Awaiting HITL Gate 3)`, `VERIFIED_LOCKED`), `src/state_manager.py` (`DT-00` cleanup), and `scripts/run_dt02_sop_skill_compiler.py`.
5. Create `tests/test_step7_dt02_sop_skill_compiler.py`, update `tests/test_step1_state_and_config.py` (`REMOVED` -> `EMPTY`), run `pytest -v -W error::DeprecationWarning -W error::FutureWarning`, and execute `--mode candidate` + `inspect_demo_state.py`.

---

## Implementation Summary (Gate 5)

- **Status:** Completed & Verified (HITL Gate 3 APPROVED — `VERIFIED_LOCKED`)
- **Files Created:**
  - `prompts/track_a_sop_compiler_prompt.md`
  - `src/track_a/__init__.py`
  - `src/track_a/adverse_test_harness.py` (`evaluate_guardrails_against_payload`, `run_dt02b_adverse_guardrail_tests` for `ADV-01`, `ADV-02`, `ADV-03`)
  - `src/track_a/sop_to_skill_compiler.py` (`run_dt02_sop_skill_compiler` with `PARTIAL_GAP` functional spec emitter + Two-Phase HITL Gate 3)
  - `scripts/run_dt02_sop_skill_compiler.py`
  - `tests/test_step7_dt02_sop_skill_compiler.py`
  - `skills/gate3_candidate_sop_402.json`, `skills/skill_sop_402.yaml`, `skills/guardrails_sop_402.json`, `reports/hitl_sop_skill_review.html`, `reports/hitl_sop_skill_review.md`
  - `data/golden_reference/skill_sop_402.yaml`, `data/golden_reference/guardrails_sop_402.json`
- **Files Modified:**
  - `config.yaml` (`gate3_candidate_proposal_path`, `sop_compiler_prompt_template_path` under `layer2_worker_and_sop`)
  - `src/models.py` (`Layer2WorkerAndSopSettings` + Step 7 Pydantic v2 models)
  - `src/state_inspector.py` (Element 6: `EMPTY` -> `CANDIDATE_COMPILED (Awaiting HITL Gate 3)` -> `VERIFIED_LOCKED`)
  - `src/state_manager.py` (`DT-00` cleans `skills/gate3_candidate_sop_402.json` and `reports/hitl_sop_skill_review.md`)
  - `tests/test_step1_state_and_config.py` (updated Element 6 baseline/final states to `EMPTY` / `VERIFIED_LOCKED`)
  - `README.md` (added Step 7 `DT-02a` / `DT-02b` execution instructions)
- **Deviations (Gate 4):** None (resolved missing `golden_reference_dir` attribute lookup in `sop_to_skill_compiler.py` to use `workspace_root / "data" / "golden_reference"`).
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **43 passed** (0 failures, 0 `DeprecationWarning`, 0 `FutureWarning`).
  - Live `.\.venv\Scripts\python.exe scripts\run_dt02_sop_skill_compiler.py --mode approve --update-golden-ref`: `DT-02b Adverse Proof: 3/3 PASSED`, `SYS-01 Element 6 State: VERIFIED_LOCKED`, materialized `skills/skill_sop_402.yaml` & `skills/guardrails_sop_402.json`, updated `reports/hitl_sop_skill_review.html`/`.md`, and snapshotted both artifacts into `data/golden_reference/`.
  - `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: All 7 `SYS-01` elements verified in expected Design-Time states, with Element 6 at `VERIFIED_LOCKED` (`Compiled steps: 4 | Active guardrails: 4 | DT-02b Adverse Proof: 3/3 PASSED`).

