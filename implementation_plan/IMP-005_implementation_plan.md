# Implementation Plan — `IMP-005`: Development Step 3 (Scenario `DT-01b` — Prong 2 Multi-Tab Excel Catalog Dynamic Profiler, RML Mapping Generator & Row-Level `pySHACL` Quarantine Gate)

## 1. Unique Reference ID
- **Reference ID:** `IMP-005`
- **Incremental Build Step:** Step 3 of 11 (`ADR-TELCO-UC001-ACT03-V1` Section 6 / Section 10 & `PLAN-TELCO-AGENT-UC1-2026-V2` Section 5)
- **Scenario ID:** `DT-01b` (Stage 2 Activity B3 Part 1)

---

## 2. Objective & Scope

### Objective
Implement a **100% workbook-schema and use-case independent** Prong 2 Excel Catalog Dynamic Profiler, RML Mapping Generator, and deterministic row-level `pySHACL` Quarantine Gate (`DT-01b`):
1. **Fail-Fast Pre-Condition on Step 2 (`DT-01a`)**:
   - Never auto-run `DT-01a`. If `data/semantic_store/tbox_sid_etom.ttl`, `data/semantic_store/knowledge_graph.trig`, or `shapes/service_spec_shape.ttl` are missing, or if `reports/hitl_gate1_ontology_mapping_review.html` is not `LOCKED_APPROVED`, fail fast with an explicit error instructing the operator to run and approve `DT-01a` first.
2. **Shared Multi-Model `google-genai` Client (`src/llm_client.py`)**:
   - Extract the Gemini client factory (`GEMINI_API_KEY` if set, else Vertex AI with `OAuth2Credentials(token=..., quota_project_id=...)`), `gcloud` token resolver, and JSON Schema sanitizer into `src/llm_client.py`.
   - Support **per-component Gemini model selection** via `config.yaml` (`ai.component_models`), allowing each solution component (e.g. `track_b_cmdb_profiler`, `track_b_excel_profiler`, `track_b_pdf_bites`, `layer1_orchestrator`, `layer3_nl2semantics`) to use its own configured Gemini model, falling back to `ai.model_name` if not overridden.
3. **100% Schema & Use-Case Independent Excel Profiler (`src/track_b/s2_excel_shacl_ingestor.py` & `prompts/s2_excel_catalog_profiler_prompt.md`)**:
   - Zero hardcoded worksheet tab names and zero hardcoded Excel column headers in Python code.
   - Dynamically introspect `data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx` using `openpyxl` (all sheet names, merged cell ranges, and first 10 rows per sheet).
   - Pass (1) `data/raw_sources/uc001_use_case_charter.md`, (2) the locked Conceptual TBox (`data/semantic_store/tbox_sid_etom.ttl`), and (3) the dynamic Excel workbook introspection to Gemini (`gemini-3.8-flash` via `src/llm_client.py`, zero heuristic fallback) with strict Pydantic v2 `ExcelCatalogMappingProposal` validation.
   - Autonomously classify tabs (`TARGET_INGEST_TAB` vs. `EXCLUDED_DISTRACTOR_TAB`), detect 1-based `header_row_index` & `data_start_row_index`, map target columns to `tmf:ServiceSpecification` (`urn:telco:catalog:spec:{SKU_Column}`) and TBox properties, exclude internal/finance noise columns (`EXCLUDED_NOISE`), and serialize the declarative mapping to `mappings/excel_catalog_rml.yaml`.
4. **Row-Level RDF Materialization & Deterministic `pySHACL` Quarantine Gate**:
   - Iterate row-by-row over the target worksheet using `mappings/excel_catalog_rml.yaml`.
   - Construct a candidate `rdflib.Graph` per row (aligning literal datatypes with `shapes/service_spec_shape.ttl` and `tbox_sid_etom.ttl`, normalizing booleans and IRI templates) and validate each row individually with `pyshacl.validate()` against `shapes/service_spec_shape.ttl`.
   - Idempotently clear and repopulate `<urn:telco:graph:ref:catalog>` inside `data/semantic_store/knowledge_graph.trig` with the **18 valid B2B SKUs** (including `ETH-10G-GOLD`), while preserving `<urn:telco:graph:tbox:sid-etom>` and keeping `<urn:telco:graph:virtual:ib>` at `0` persisted triples.
   - Block the **2 violating rows** (negative packet loss `-0.5%` and invalid lifecycle `'99_INVALID'`) and write `reports/shacl_quarantine_report.html`, `reports/shacl_quarantine_report.md`, and `reports/shacl_quarantine_summary.json`.
5. **CLI Runner, `SYS-01` Inspector & `DT-00` Reset Integration**:
   - Create `scripts/run_dt01b_excel_quarantine.py` (strictly writing to active working directories; no `--update-golden-ref` flag).
   - Update `src/state_inspector.py` (`SYS-01` Element 3) to read materialized triple counts, valid SKU count, excluded distractor tabs count, and `pySHACL` quarantined row count dynamically.
   - Update `src/state_manager.py` (`DT-00`) to also remove `reports/shacl_quarantine_summary.json` on clean-slate reset.

---

## 3. Key Design Decisions

1. **Shared Multi-Model Client (`src/llm_client.py`)**:
   - `AiSettings` in `src/models.py` and `ai:` in `config.yaml` gain `component_models: Dict[str, str]` so each component resolves its own Gemini model via `resolve_model_for_component(config, component_name)`.
   - Both `s1_cmdb_tbox_profiler.py` and `s2_excel_shacl_ingestor.py` use `src/llm_client.py` (zero duplicate client/schema-sanitization logic).
2. **Configuration & Dynamic `SYS-01` Accounting**:
   - Add `excel_profiler_prompt_template_path` and `shacl_quarantine_summary_path` under `track_b_ingestion_and_er` in `config.yaml` and `TrackBIngestionAndErSettings` in `src/models.py`.
   - `SYS-01` Element 3 reads `shacl_quarantine_summary.json` when present (falling back to graph inspection if absent) instead of hardcoded `18`/`2` constants.
3. **SHACL-Aligned Datatype & Value Normalization**:
   - Inspect `shapes/service_spec_shape.ttl` for `sh:datatype` constraints (`xsd:double` for `telco:maxPacketLossPct` and `telco:availabilityTargetPct`, `xsd:string` for `tmf:skuCode` and `telco:lifecycleStatus`) and normalize boolean values (`YES`/`TRUE`/`1` $\rightarrow$ `xsd:boolean`) and IRI templates (`urn:telco:catalog:spec:{col}`) cleanly.
4. **No `--update-golden-ref` in `DT-01b`**:
   - Per Gate 1 decision, `DT-01b` writes strictly to `mappings/excel_catalog_rml.yaml`, `data/semantic_store/knowledge_graph.trig`, and `reports/shacl_quarantine_report.*` / `shacl_quarantine_summary.json`. `data/golden_reference/` is untouched.

---

## 4. Step-by-Step Implementation Plan

### Step 1: Configuration, Models & Shared Multi-Model LLM Client
- Update `config.yaml` (`ai.component_models`, `track_b_ingestion_and_er.excel_profiler_prompt_template_path`, `track_b_ingestion_and_er.shacl_quarantine_summary_path`).
- Update `src/models.py` (`AiSettings`, `TrackBIngestionAndErSettings`, and Step 3 Pydantic v2 models: `ExcelSheetIntrospection`, `ExcelWorkbookIntrospection`, `ExcelColumnMappingSpec`, `ExcelWorksheetClassification`, `ExcelCatalogMappingProposal`, `QuarantinedRowRecord`, `PromotedSkuSummary`, `Dt01bExecutionResult`).
- Create `src/llm_client.py` and refactor `src/track_b/s1_cmdb_tbox_profiler.py` to import `create_genai_client`, `resolve_model_for_component`, and `strip_unsupported_vertex_schema_keys` from `src/llm_client.py`.

### Step 2: Externalized Prompt & Prong 2 Excel Profiler + `pySHACL` Quarantine Engine
- Create `prompts/s2_excel_catalog_profiler_prompt.md`.
- Create `src/track_b/s2_excel_shacl_ingestor.py` implementing:
  - `verify_dt01a_prerequisites(config, root_dir)` (fail-fast check)
  - `introspect_excel_workbook(excel_path)` (`openpyxl` dynamic introspection)
  - `generate_excel_mapping_proposal_via_llm(...)` (via `src/llm_client.py`)
  - `write_excel_rml_yaml(proposal, rml_yaml_path)`
  - `materialize_and_quarantine_excel_rows(...)` (`rdflib` + `pyshacl.validate()`)
  - `update_trig_catalog_graph(...)` (idempotent `<urn:telco:graph:ref:catalog>` update in `knowledge_graph.trig`)
  - `write_quarantine_reports(...)` (`reports/shacl_quarantine_report.html`, `.md`, and `shacl_quarantine_summary.json`)
  - `run_dt01b_excel_quarantine(...)`

### Step 3: CLI Runner, `SYS-01` Inspector & `DT-00` Reset Integration
- Create `scripts/run_dt01b_excel_quarantine.py`.
- Update `src/state_inspector.py` (`_inspect_element_3_excel_catalog`) to report dynamic materialized triple count, valid B2B SKUs, excluded distractor tabs, and quarantined rows.
- Update `src/state_manager.py` (`reset_to_clean_slate`) to also delete `shacl_quarantine_summary.json`.

### Step 4: Unit Tests & Live Verification (`tests/test_step3_dt01b_excel_quarantine.py`)
- Write `tests/test_step3_dt01b_excel_quarantine.py` verifying:
  1. Zero hardcoded worksheet tab names or column headers exist in `src/track_b/s2_excel_shacl_ingestor.py`.
  2. Fail-fast error when Step 2 (`DT-01a`) artifacts are missing or not `LOCKED_APPROVED`.
  3. Dynamic `openpyxl` introspection of all 3 worksheets (merged banners, row 5 headers, row 6+ data).
  4. End-to-end `DT-01b` execution loading `18` valid `tmf:ServiceSpecification` instances (including `ETH-10G-GOLD` with `maxPacketLossPct = 0.1` and `autoRemediationAllowed = true`) into `<urn:telco:graph:ref:catalog>`, keeping `<urn:telco:graph:virtual:ib>` at `0` triples, quarantining the `2` dirty rows via `pySHACL`, and transitioning `SYS-01` Element 3 to `LOADED_WITH_QUARANTINE`.
  5. `DT-00` reset clears Step 3 artifacts and returns Element 3 to `EMPTY`.
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\run_dt01b_excel_quarantine.py` and `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`.

---

## Gate 4 Approved Deviation
During implementation, inspection of `Telco_Master_Product_SLA_Catalog_2026.xlsx` and `shapes/service_spec_shape.ttl` revealed a schema mismatch where `B2B_Enterprise_SLA_Matrix` had no availability percentage column while `service_spec_shape.ttl` required `sh:minCount 1` on `telco:availabilityTargetPct`, and used ERP shadow lifecycle/boolean flags (`10_PROD`, `20_PILOT`, `YES`, `NO`) vs. canonical RDF values. With explicit user approval:
1. Updated `shapes/service_spec_shape.ttl`, `data/golden_reference/service_spec_shape.ttl`, and `data/semantic_store/gate1_candidate_proposal.json` so `telco:availabilityTargetPct`, `telco:slaCreditCapPct`, and `telco:minContractMonths` are optional (`sh:minCount 0`), `telco:autoRemediationAllowed` requires `xsd:boolean`, and `telco:lifecycleStatus` validates `sh:in ( "ACTIVE" "PILOT" "DEPRECATED" )`.
2. Added declarative `value_map` (`ExcelValueMapEntry`) support in `ExcelColumnMappingSpec` and `prompts/s2_excel_catalog_profiler_prompt.md` so valid codes (`10_PROD` -> `ACTIVE`, `20_PILOT` -> `PILOT`, `YES` -> `true`, `NO` -> `false`) translate deterministically while unmapped/dirty codes (`99_INVALID`, `99_OBS_SHADOW`, `MAYBE_LEGACY`, `UNKNOWN`) pass through raw and are quarantined by `pySHACL`.
3. Aligned `DEFAULT_PREFIXES["telco"]` in `src/track_b/s2_excel_shacl_ingestor.py` to `http://telco.enterprise.org/ontology/`.

---

## Implementation Summary
- **Shared Multi-Model LLM Client (`src/llm_client.py`)**: Extracted `create_genai_client`, `resolve_gcloud_access_token`, `strip_unsupported_vertex_schema_keys`, and `resolve_model_for_component(config, component_name)`, backed by `config.yaml` `ai.component_models` (`AiSettings.component_models`). Refactored `src/track_b/s1_cmdb_tbox_profiler.py` to use `src/llm_client.py`.
- **100% Schema-Independent Excel Profiler & `pySHACL` Quarantine Gate**:
  - Created `prompts/s2_excel_catalog_profiler_prompt.md` and `src/track_b/s2_excel_shacl_ingestor.py` with zero hardcoded worksheet tab names or column headers.
  - Added Step 3 Pydantic v2 models (`ExcelSheetIntrospection`, `ExcelWorkbookIntrospection`, `ExcelWorksheetClassification`, `ExcelValueMapEntry`, `ExcelColumnMappingSpec`, `ExcelCatalogMappingProposal`, `QuarantinedRowRecord`, `PromotedSkuSummary`, `ShaclQuarantineSummary`, `Dt01bExecutionResult`) in `src/models.py`.
  - Created CLI runner `scripts/run_dt01b_excel_quarantine.py` (no `--update-golden-ref` flag per Gate 2 decision).
  - Updated `src/state_inspector.py` (`_inspect_element_3_excel_catalog`) and `src/state_manager.py` (`reset_to_clean_slate` cleaning `shacl_quarantine_summary.json`).
- **Verification Results**:
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **22 passed** (0 DeprecationWarnings, 0 FutureWarnings).
  - Live `.\.venv\Scripts\python.exe scripts\run_dt01b_excel_quarantine.py` (`gemini-3.8-flash` on Vertex AI):
    - Target worksheet selected: `B2B_Enterprise_SLA_Matrix` (2 distractor tabs excluded)
    - Valid B2B SKUs promoted into `<urn:telco:graph:ref:catalog>`: **18** (`198` materialized triples; `<urn:telco:graph:virtual:ib>` = `0` triples)
    - Quarantined dirty rows: **2** (`DARK-FIBER-METRO-X` at row 24, `SDWAN-LEGACY-99` at row 25), each deterministically failing all 3 constraints (`telco:maxPacketLossPct` range, `telco:autoRemediationAllowed` `xsd:boolean`, `telco:lifecycleStatus` `sh:in`)
  - Live `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: Element 3 reported `LOADED_WITH_QUARANTINE` (`Materialized triples: 198 | Valid B2B SKUs loaded: 18 | Excluded distractor tabs: 2 | pySHACL quarantined rows: 2`).


