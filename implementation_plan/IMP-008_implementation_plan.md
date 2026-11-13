# Implementation Plan: `IMP-008` — Development Step 6 (Stage 1/2 — Layer 3: `NL2Semantics` Dual Shadow Comparison Engine, Static `rdflib` AST Security Gatekeeper & Southbound `semantic-read-mcp` Server — Scenario `RT-05`)

## 1. Unique Reference ID
`IMP-008`

## 2. Objective & Scope
Implement **Development Step 6 (Stage 1/2 — Layer 3 + `semantic-read-mcp` + Scenario `RT-05`)** inside `d:/Telecom Agentic AI Demo/` strictly scoped to:
1. **Fail-Fast Prerequisite Check:** Verify Track B & Layer 4 prerequisites via `validate_layer4_prerequisites` (never auto-run Track B scripts).
2. **Stored Verified SPARQL Template Catalog & Externalized Prompts:**
   - `data/semantic_store/stored_sparql_templates.yaml` (containing `tpl_uc001_circuit_assurance_context` and additional verified read-only templates).
   - `prompts/layer3_voicebox_hybrid_prompt.md` (TBox pruning + verified template matching + parameter extraction; zero access to `cmdb_r2rml.ttl` or SQLite).
   - `prompts/layer3_zero_shot_sparql_prompt.md` (raw SPARQL synthesis from `tbox_sid_etom.ttl` + Named Graph IRIs only; zero access to `stored_sparql_templates.yaml` or `cmdb_r2rml.ttl`).
3. **Static `rdflib` AST Security Gatekeeper (`src/layer3/__init__.py`, `src/layer3/ast_gatekeeper.py`):**
   - `validate_sparql_ast(query_text, tbox_path, trig_path=None) -> SparqlAstAuditResult`:
     * Block SPARQL UPDATE/mutation keywords (`INSERT`, `DELETE`, `DROP`, `CLEAR`, `LOAD`, `CREATE`, `MOVE`, `COPY`, `ADD`).
     * Detect physical SQL table/column leakage via generic regex (`\bT_[A-Z0-9_]+\b`, `\bPRAGMA\b`, `\bSQLITE_MASTER\b`, `\bROWID\b`, `_SURR_ID\b`, `_ROW_ID\b`) AND closed-vocabulary TBox check against `tbox_sid_etom.ttl` (plus promoted `knowledge_graph.trig` vocabulary and `telco:cpeModelSku` runtime projection).
     * Parse and translate via `rdflib.plugins.sparql.parser.parseQuery` & `rdflib.plugins.sparql.algebra.translateQuery`, verifying a read-only query AST (`SelectQuery`, `AskQuery`, `ConstructQuery`, `DescribeQuery`) and recording algebra node types, referenced `GRAPH` URIs, projected variables, and `ast_valid`.
4. **Layer 3 `NL2Semantics` Engine (`src/layer3/nl2semantics_engine.py`):**
   - Support `"voicebox_hybrid"`, `"zero_shot_llm"`, and `"dual_comparison"` (default), configurable via `config.yaml` (`layer3_nl2semantics.execution_mode`), `LAYER3_EXECUTION_MODE` env var, or runtime `execution_mode` argument.
   - Use `src/llm_client.py` (`resolve_model_for_component(config, "layer3_nl2semantics")`, zero heuristic fallback).
   - Capture zero-shot AST failures, syntax errors, or 0-row/partial results cleanly inside `Layer3DualComparisonResult` as empirical comparison evidence while `"voicebox_hybrid"` provides the authoritative `FederatedCircuitContext` and `FiveChallengeProofTable`.
   - Render `reports/rt05_layer3_nl2semantics_comparison.html` and `.md`.
5. **Southbound FastMCP Server (`src/mcp_servers/__init__.py`, `src/mcp_servers/semantic_read_mcp.py`) & CLI (`scripts/run_rt05_layer3_modes.py`):**
   - Expose `query_knowledge_fabric(natural_language_intent, target_circuit_id=None, execution_mode=None, obo_jwt=None) -> dict` via `FastMCP("semantic-read-mcp")`, with configurable `require_obo_jwt` / `required_obo_scope` (`"semantic:read"`) and `PyJWT` payload validation when `obo_jwt` is supplied.
   - Update `DT-00` (`src/state_manager.py`) to clean `reports/rt05_layer3_nl2semantics_comparison.*`.

---

## 3. Key Design Decisions (Locked in Gate 1)
1. **Zero-Shot Imperfection Handling:** Neither `"dual_comparison"` nor `"zero_shot_llm"` aborts if the zero-shot query fails AST validation, syntax parsing, or returns 0/partial rows; all diagnostics are recorded in `ZeroShotExecutionResult` inside `Layer3DualComparisonResult`.
2. **Configurable `obo_jwt` Verification:** `config.yaml` (`layer3_nl2semantics`) adds `require_obo_jwt: false` and `required_obo_scope: "semantic:read"`. When `obo_jwt` is provided, `PyJWT` decodes and validates `sub`, `scp`/`scope`, and `exp` (failing fast with `PermissionError` on invalid/expired/insufficient scope); when `obo_jwt is None`, `require_obo_jwt=True` raises `PermissionError` while `False` records `STANDALONE_RT05_BYPASS`.
3. **Zero Hardcoding & Closed-Vocabulary SQL Leakage Detection:** `src/layer3/` contains zero hardcoded physical SQL table/column names and enforces generic SQL regex + closed-vocabulary TBox checks.

---

## 4. Step-by-Step Implementation Plan

### Step 1: Config, Env Override & Pydantic v2 Models (`config.yaml`, `src/config_loader.py`, `src/models.py`)
- Update `config.yaml` (`layer3_nl2semantics`) with `stored_sparql_templates_path`, `voicebox_prompt_template_path`, `zero_shot_prompt_template_path`, `rt05_comparison_report_path`, `require_obo_jwt: false`, `required_obo_scope: "semantic:read"`.
- Update `src/config_loader.py` to support `LAYER3_EXECUTION_MODE` environment variable override.
- Update `src/models.py` (`Layer3Nl2SemanticsSettings` + Step 6 models: `SparqlAstAuditResult`, `VoiceboxHybridSelectionProposal`, `ZeroShotSparqlProposal`, `VoiceboxExecutionResult`, `ZeroShotExecutionResult`, `Layer3DualComparisonResult`).

### Step 2: Stored Templates, Prompts & Static `rdflib` AST Gatekeeper
- Create `data/semantic_store/stored_sparql_templates.yaml`.
- Create `prompts/layer3_voicebox_hybrid_prompt.md` and `prompts/layer3_zero_shot_sparql_prompt.md`.
- Create `src/layer3/__init__.py` and `src/layer3/ast_gatekeeper.py`.

### Step 3: Layer 3 `NL2Semantics` Engine, `semantic_read_mcp.py`, CLI & `DT-00`
- Create `src/layer3/nl2semantics_engine.py`.
- Create `src/mcp_servers/__init__.py` and `src/mcp_servers/semantic_read_mcp.py`.
- Create `scripts/run_rt05_layer3_modes.py`.
- Update `src/state_manager.py` (`reset_to_clean_slate`) to clean `reports/rt05_layer3_nl2semantics_comparison.*`.

### Step 4: Unit Tests, Docs & Live Verification (`tests/test_step6_layer3_nl2semantics.py`, `README.md`)
- Write unit tests covering zero SQL/R2RML leakage in `src/layer3/`, AST gatekeeper rejection/acceptance, all 3 execution modes, `obo_jwt` validation & `PermissionError` enforcement, `semantic_read_mcp.py`, and `0` persisted triples in `<urn:telco:graph:virtual:ib>`.
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py` and `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`.
- Update `README.md` and append Gate 5 Implementation Summary to `implementation_plan/IMP-008_implementation_plan.md`.

---

## Implementation Summary (Gate 5)

- **Status:** Completed & Verified
- **Files Created:**
  - `data/semantic_store/stored_sparql_templates.yaml` (`tpl_uc001_circuit_assurance_context`, `tpl_uc002_catalog_sku_lookup`, `tpl_uc003_doc_lifecycle_audit`)
  - `prompts/layer3_voicebox_hybrid_prompt.md`
  - `prompts/layer3_zero_shot_sparql_prompt.md`
  - `src/layer3/__init__.py`
  - `src/layer3/ast_gatekeeper.py` (`validate_sparql_ast` with `rdflib` parser/algebra checks, mutation keyword blocking, generic SQL leakage regex detection, and closed-vocabulary TBox + TriG validation)
  - `src/layer3/nl2semantics_engine.py` (`run_layer3_nl2semantics` supporting `dual_comparison`, `voicebox_hybrid`, and `zero_shot_llm` via `src/llm_client.py` + `reports/rt05_layer3_nl2semantics_comparison.html`/`.md`)
  - `src/mcp_servers/__init__.py`
  - `src/mcp_servers/semantic_read_mcp.py` (`MCPServer("semantic-read-mcp")` exposing `query_knowledge_fabric` with configurable `PyJWT` `obo_jwt` scope verification)
  - `scripts/run_rt05_layer3_modes.py`
  - `tests/test_step6_layer3_nl2semantics.py`
- **Files Modified:**
  - `config.yaml` (added `stored_sparql_templates_path`, `voicebox_prompt_template_path`, `zero_shot_prompt_template_path`, `rt05_comparison_report_path`, `require_obo_jwt`, `required_obo_scope` under `layer3_nl2semantics`)
  - `src/models.py` (extended `Layer3Nl2SemanticsSettings` and added Step 6 Pydantic v2 models)
  - `src/state_manager.py` (updated `reset_to_clean_slate` to clean `reports/rt05_layer3_nl2semantics_comparison.*`)
  - `README.md` (added Scenario `RT-05` & `semantic-read-mcp` execution instructions)
- **Deviations (Gate 4):** None. Note: `mcp` v2.x in `.venv` uses `MCPServer` (`from mcp.server.mcpserver import MCPServer`) rather than v1 `FastMCP`.
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **39 passed** in 5.06s (0 failures, 0 `DeprecationWarning`, 0 `FutureWarning`).
  - Live `.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --mode dual_comparison --circuit-id CIR-994821` (`gemini-3.8-flash` on Vertex AI):
    - **Voicebox Hybrid (`Option 3C`)**: `template=tpl_uc001_circuit_assurance_context`, `ast_passed=True`, `rows=1`, `latency_ms=8146.29`, `0` missing fields.
    - **Zero-Shot Shadow**: `ast_passed=True`, `rows=0`, `latency_ms=34658.39`, `missing_fields=13`.
    - **Zero-Copy Invariant**: `On-Disk virtual:ib Triples After: 0`.
  - `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: Elements 1–5 & 7 verified in expected promoted/active states (`LOCKED_APPROVED`, `BOUND_ZERO_COPY`, `LOADED_WITH_QUARANTINE`, `PROMOTED`, `COMPLETE`, `ACTIVE_PRESET`).

