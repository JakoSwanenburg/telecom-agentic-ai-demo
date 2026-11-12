# Implementation Plan — `IMP-003`: Development Step 1 (Stage 0 Activity 0.3 Lock + `SYS-01` Live State Inspector + `DT-00` Clean-Slate Wipe)

## 1. Unique Reference ID
- **Reference ID:** `IMP-003`
- **Incremental Build Step:** Step 1 of 11 (`ADR-TELCO-UC001-ACT03-V1` Section 10 & `PLAN-TELCO-AGENT-UC1-2026-V2` Section 9)

---

## 2. Objective & Scope

### Objective
Execute Development Step 1 of the 11-step incremental build plan:
1. Install and verify the complete Python W3C verification stack packages in `.venv` (`rdflib`, `pyshacl`, `langgraph`, `fastmcp`, `pydantic`, `pyjwt`, `pyyaml`, `pypdf`, `openpyxl`, `python-docx`, `rapidfuzz`, `google-genai`, `rich`, `pytest`) with zero warnings/deprecations.
2. Extend the existing root `config.yaml` and Pydantic v2 configuration loader (`src/config.py` / `src/config_loader.py`) with the 7 locked component architecture sections (`use_case`, `layer1_orchestrator`, `layer2_worker_and_sop`, `layer3_nl2semantics`, `layer4_compiler_federation`, `track_b_ingestion_and_er`, `cqrs_action_plane`).
3. Verify `data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md` confirms `CFS_ROW_ID=2000` (expired `ETH-1G-SILVER`) and `CFS_ROW_ID=2001` (active `ETH-10G-GOLD`).
4. Create the Southbound MCP Platform Primitive Catalog (`config/mcp_primitives_catalog.json`) and catalog manager (`src/catalog_manager.py`) supporting `enable_tmf621_dispatch_primitive` toggling.
5. Implement Scenario `DT-00` (*Wipe & Reset to Clean Slate*) in `src/state_manager.py` and CLI entrypoint `scripts/reset_demo_state.py`.
6. Implement `SYS-01` (*Live System State Inspector*) in `src/state_inspector.py` and CLI entrypoint `scripts/inspect_demo_state.py`, outputting a rich console table plus `reports/system_state_dashboard.html` and `reports/system_state_dashboard.md`.
7. Implement and pass unit tests in `tests/test_step1_state_and_config.py`.

### Scope Boundaries
- **In Scope**: Step 1 only (Configuration, MCP Primitive Catalog, `DT-00` Clean-Slate Wipe, `SYS-01` State Inspector, and Step 1 unit tests).
- **Out of Scope**: Layers 1–4 execution logic, Track B ingestion (`DT-01a..c`), and SOP compilation (`DT-02a..b`) — reserved for Steps 2–11.

---

## 3. Key Design Decisions

1. **Single Authoritative Root `config.yaml`**:
   - Extend the existing root `config.yaml` with `use_case`, `layer1_orchestrator`, `layer2_worker_and_sop`, `layer3_nl2semantics`, `layer4_compiler_federation`, `track_b_ingestion_and_er`, and `cqrs_action_plane` while retaining existing sections (`project`, `gcp`, `logging`, `paths`, `stage0`, `ai`) so all `IMP-002` tests and scripts remain 100% compatible.
   - Provide `src/config_loader.py` as a clean module re-exporting `load_config`, `get_workspace_root`, and `AppConfig` from `src/config.py`.
2. **Southbound MCP Platform Primitive Catalog (`config/mcp_primitives_catalog.json` & `src/catalog_manager.py`)**:
   - Models the 4 reusable platform primitives (`mcp://semantic-read/query_knowledge_fabric`, `cqrs://singleton-check/probe_resource_state`, `cqrs://transactional-write/execute_governed_mutation`, `cqrs://transactional-write/commit_validated_graph_triples`) and the top-level boolean flag `"enable_tmf621_dispatch_primitive": true`.
   - When `enable_tmf621_dispatch_primitive` is `false` (for `DT-02a`), `TMF621_TROUBLE_TICKET` is marked unavailable in `execute_governed_mutation` and Element 5 of `SYS-01` reports `PARTIAL_GAP (TMF621 Missing)`.
3. **`DT-00` Clean-Slate Wipe (`src/state_manager.py` & `scripts/reset_demo_state.py`)**:
   - Preserves `data/raw_sources/` and `data/golden_reference/` untouched.
   - Deletes generated semantic store & mapping files (`data/semantic_store/knowledge_graph.trig`, `data/semantic_store/tbox_sid_etom.ttl`, `mappings/cmdb_r2rml.ttl`, `mappings/excel_catalog_rml.yaml`, `shapes/*.ttl`), compiled skills (`skills/skill_sop_402.yaml`, `skills/guardrails_sop_402.json`), and build/HITL reports (`reports/hitl_*.html`, `reports/shacl_quarantine_report.html`, `reports/missing_primitive_spec.json`).
   - Resets `data/cqrs_state/cqrs_runtime_state.json` to 0 active mutex locks and `3/3` token-bucket tokens.
   - Supports CLI argument `--set-catalog-gap` (`true` sets `enable_tmf621_dispatch_primitive = false`; `false` sets `enable_tmf621_dispatch_primitive = true`).
4. **`SYS-01` Live System State Inspector (`src/state_inspector.py` & `scripts/inspect_demo_state.py`)**:
   - Inspects all 7 architectural elements and outputs:
     - Rich formatted console table
     - `reports/system_state_dashboard.html`
     - `reports/system_state_dashboard.md`

---

## 4. Step-by-Step Implementation Plan

### Step 1: Update `requirements.txt` & Install Packages in `.venv`
- Add `rdflib`, `pyshacl`, `langgraph`, `fastmcp`, `pyjwt`, `pypdf`, `rapidfuzz`, `google-genai`, and `rich` to `requirements.txt` and install via `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.

### Step 2: Extend `config.yaml`, `src/models.py`, `src/config.py`, and Create `src/config_loader.py`
- Update `config.yaml` with the 7 Step 1 sections (`use_case`, `layer1_orchestrator`, `layer2_worker_and_sop`, `layer3_nl2semantics`, `layer4_compiler_federation`, `track_b_ingestion_and_er`, `cqrs_action_plane`).
- Add corresponding Pydantic v2 models to `src/models.py` (plus models for the MCP Catalog, CQRS runtime state, and `SYS-01` State Inspector).
- Support environment variable overrides for `LAYER3_EXECUTION_MODE` and `CQRS_TELEMETRY_PRESET` in `src/config.py`.
- Create `src/config_loader.py`.

### Step 3: Create `config/mcp_primitives_catalog.json` & `src/catalog_manager.py`
- Author `config/mcp_primitives_catalog.json` with all 4 platform primitives and `"enable_tmf621_dispatch_primitive": true`.
- Author `src/catalog_manager.py` with `load_catalog()`, `save_catalog()`, `set_tmf621_primitive_enabled()`, and `get_supported_protocols()`.

### Step 4: Implement `DT-00` in `src/state_manager.py` & `scripts/reset_demo_state.py`
- Author `src/state_manager.py` implementing `reset_to_clean_slate()` and `initialize_cqrs_state()`.
- Author `scripts/reset_demo_state.py` supporting `--set-catalog-gap`.

### Step 5: Implement `SYS-01` in `src/state_inspector.py` & `scripts/inspect_demo_state.py`
- Author `src/state_inspector.py` inspecting all 7 elements, rendering a `rich` console table, and writing `reports/system_state_dashboard.html` and `reports/system_state_dashboard.md`.
- Author `scripts/inspect_demo_state.py`.

### Step 6: Unit Tests, Execution & Documentation (`Gate 5`)
- Create `tests/test_step1_state_and_config.py`.
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\reset_demo_state.py` followed by `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`.
- Update `README.md` and append the Gate 5 **Implementation Summary** to `implementation_plan/IMP-003_implementation_plan.md`.

---

## 5. Implementation Summary (Gate 5)

### What Was Built
1. **Python W3C & Agentic AI Stack Dependencies (`requirements.txt` & `.venv`)**:
   - Verified and installed all 14 required packages in `.venv` (`rdflib==7.6.0`, `pyshacl==0.40.2`, `langgraph==1.2.20`, `fastmcp==4.1.8`, `pydantic==2.14.3`, `pyjwt==2.15.1`, `pyyaml==6.0.3`, `pypdf==7.0.1`, `openpyxl==3.1.5`, `python-docx==1.2.0`, `rapidfuzz==3.14.6`, `google-genai==3.2.0`, `rich==15.0.0`, `pytest==9.2.0`).
2. **Master Configuration (`config.yaml`) & Pydantic v2 Loader (`src/models.py`, `src/config.py`, `src/config_loader.py`)**:
   - Extended root `config.yaml` with `use_case`, `layer1_orchestrator` (`Option 1D`), `layer2_worker_and_sop` (`Option 2.1D-Catalog` + `Option 2.2A`), `layer3_nl2semantics` (`Option 3C-Dual`), `layer4_compiler_federation` (`Option 4A`), `track_b_ingestion_and_er` (`Option 5A-HITL`), and `cqrs_action_plane` (`Option 6A-Generic`).
   - Added strict Pydantic v2 models (`ConfigDict(extra="forbid", frozen=True)`) and environment variable overrides (`LAYER1_TRANSPORT_MODE`, `LAYER3_EXECUTION_MODE`, `CQRS_TELEMETRY_PRESET`).
3. **Stage 0 Artifact Manifest SCD2 Consistency (`data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md`)**:
   - Verified `STAGE0_ARTIFACT_MANIFEST.md` matches the SQLite CMDB ground truth (`CFS_ROW_ID=2000` for expired `ETH-1G-SILVER` and `CFS_ROW_ID=2001` for active `ETH-10G-GOLD`).
4. **Southbound MCP Platform Primitive Catalog (`config/mcp_primitives_catalog.json` & `src/catalog_manager.py`)**:
   - Created `config/mcp_primitives_catalog.json` defining the 4 generic platform primitives (`mcp://semantic-read/query_knowledge_fabric`, `cqrs://singleton-check/probe_resource_state`, `cqrs://transactional-write/execute_governed_mutation`, `cqrs://transactional-write/commit_validated_graph_triples`) and `"enable_tmf621_dispatch_primitive": true`.
   - Implemented `src/catalog_manager.py` to load, validate, query active protocols, and toggle `enable_tmf621_dispatch_primitive` for Scenario `DT-02a` vs. `DT-02b`.
5. **Scenario `DT-00` — Wipe & Reset to Clean Slate (`src/state_manager.py` & `scripts/reset_demo_state.py`)**:
   - Implemented `reset_to_clean_slate()` and CLI script `scripts/reset_demo_state.py` to wipe active semantic store files (`knowledge_graph.trig`, `tbox_sid_etom.ttl`), mappings (`cmdb_r2rml.ttl`, `excel_catalog_rml.yaml`), SHACL shapes (`shapes/*.ttl`), compiled skills (`skill_sop_402.yaml`, `guardrails_sop_402.json`), and build/HITL reports while preserving `data/raw_sources/` (8 Stage 0 files) and `data/golden_reference/` untouched, resetting `data/cqrs_state/cqrs_runtime_state.json` (0 active mutex locks, `3/3` rate-limit tokens), and supporting `--set-catalog-gap`.
6. **`SYS-01` — Live System State Inspector (`src/state_inspector.py` & `scripts/inspect_demo_state.py`)**:
   - Implemented `inspect_system_state()` and CLI script `scripts/inspect_demo_state.py` to inspect all 7 architectural elements, render a rich console table, and generate `reports/system_state_dashboard.html` and `reports/system_state_dashboard.md`.

### Files Created or Modified
- **Modified**:
  - `requirements.txt`
  - `config.yaml`
  - `src/models.py`
  - `src/config.py`
  - `README.md`
  - `implementation_plan/IMP-003_implementation_plan.md`
- **Created**:
  - `config/mcp_primitives_catalog.json`
  - `src/config_loader.py`
  - `src/catalog_manager.py`
  - `src/state_manager.py`
  - `src/state_inspector.py`
  - `scripts/reset_demo_state.py`
  - `scripts/inspect_demo_state.py`
  - `tests/test_step1_state_and_config.py`
  - `data/cqrs_state/cqrs_runtime_state.json`
  - `reports/system_state_dashboard.html`
  - `reports/system_state_dashboard.md`

### Deviations Taken During Gate 4
- None. All components were implemented strictly per the approved `IMP-003` plan.

### Verification Results
- **Unit Test Suite (`pytest -v -W error::DeprecationWarning -W error::FutureWarning`)**: **15 / 15 passed** in `0.74s` with zero deprecation or future warnings.
- **Scenario `DT-00` Execution (`scripts/reset_demo_state.py`)**: Executed cleanly (exit code `0`), preserving all 8 Stage 0 raw source files, resetting `data/cqrs_state/cqrs_runtime_state.json` (`active_locks=0`, `tokens=3/3`), and confirming `enable_tmf621_dispatch_primitive=True`.
- **`SYS-01` Execution (`scripts/inspect_demo_state.py`)**: Executed cleanly (exit code `0`), printing the 7-element Rich console table (`EMPTY`, `UNBOUND`, `EMPTY`, `EMPTY`, `COMPLETE`, `REMOVED`, `ACTIVE_PRESET`) and generating `reports/system_state_dashboard.html` and `reports/system_state_dashboard.md`.


