# Implementation Plan — `IMP-008-R1`

## 1. Unique Reference ID
`IMP-008-R1` (Refinement of Step 6 / `IMP-008`: Layer 3 `NL2Semantics` Pipeline-Generated Stored SPARQL Templates & `DT-00` Lifecycle)

## 2. Objective & Scope
Ensure `data/semantic_store/stored_sparql_templates.yaml` is a **100% pipeline-generated artifact** (derived dynamically from the Use Case Charter, locked SID/eTOM TBox, promoted Named Graph schemas in `knowledge_graph.trig`, and `cmdb_r2rml.ttl` + Layer 4 virtual graph projection) rather than hand-coded, and ensure `DT-00` (`reset_to_clean_slate`) deletes it cleanly during resets.

## 3. Key Design Decisions
1. **Automatic & Opt-In Compilation Hooks:**
   - `scripts/run_dt01c_pdf_bites_gate2.py --mode approve` automatically invokes `compile_stored_sparql_templates()` after Gate 2 graphs are promoted (and copies the generated `stored_sparql_templates.yaml` to `data/golden_reference/stored_sparql_templates.yaml` when `--update-golden-ref` is passed).
   - `scripts/run_rt05_layer3_modes.py` exposes an opt-in `--compile-templates` flag for standalone Layer 3 iteration.
   - `src/layer3/nl2semantics_engine.py` never silently auto-compiles; it fails fast with an explicit `RuntimeError` if `stored_sparql_templates.yaml` is missing when `"voicebox_hybrid"` or `"dual_comparison"` is invoked.
2. **Dynamic Introspection & Verification (`src/layer3/template_compiler.py`):**
   - Introspects `data/raw_sources/uc001_use_case_charter.md`, `data/semantic_store/tbox_sid_etom.ttl`, `data/semantic_store/knowledge_graph.trig`, and `mappings/cmdb_r2rml.ttl` + Layer 4 in-memory `<urn:telco:graph:virtual:ib>` predicates/IRI patterns.
   - Calls Gemini (`layer3_nl2semantics`) via `src/llm_client.py` with Pydantic v2 `StoredSparqlTemplateCatalog` structured output.
   - Validates every generated template via `validate_sparql_ast()` and verifies `tpl_uc001_circuit_assurance_context` executes cleanly against Layer 4 (`execute_readonly_sparql`) returning `CIR-994821` assurance fields before writing `data/semantic_store/stored_sparql_templates.yaml`.
3. **Clean-Slate Wipe (`DT-00`):**
   - `reset_to_clean_slate()` in `src/state_manager.py` deletes `data/semantic_store/stored_sparql_templates.yaml`.

## 4. Step-by-Step Implementation Plan
1. Update `config.yaml` (`layer3_nl2semantics.template_compiler_prompt_path`) and `src/models.py` (`Layer3Nl2SemanticsSettings`, `StoredSparqlTemplate`, `StoredSparqlTemplateCatalog`, `TemplateCompileResult`).
2. Create `prompts/layer3_template_compiler_prompt.md` and `src/layer3/template_compiler.py`.
3. Update `src/layer3/__init__.py`, `src/layer3/nl2semantics_engine.py` (`RuntimeError` fail-fast on missing templates), `src/state_manager.py` (`DT-00` deletion), `scripts/run_dt01c_pdf_bites_gate2.py`, and `scripts/run_rt05_layer3_modes.py`.
4. Update `tests/test_step1_state_and_config.py` and `tests/test_step6_layer3_nl2semantics.py`.
5. Delete the hand-coded `data/semantic_store/stored_sparql_templates.yaml`, run `pytest -v -W error::DeprecationWarning -W error::FutureWarning`, regenerate `stored_sparql_templates.yaml` + `data/golden_reference/stored_sparql_templates.yaml` live, run `scripts/run_rt05_layer3_modes.py --mode dual_comparison --circuit-id CIR-994821`, and run `scripts/inspect_demo_state.py`.

---

## Implementation Summary (Gate 5)

- **Status:** Completed & Verified
- **Files Created:**
  - `prompts/layer3_template_compiler_prompt.md`
  - `src/layer3/template_compiler.py` (`compile_stored_sparql_templates` introspecting `uc001_use_case_charter.md`, `tbox_sid_etom.ttl`, `knowledge_graph.trig`, and R2RML + Layer 4 `virtual:ib`, synthesizing `StoredSparqlTemplateCatalog` via Gemini, validating all templates via `validate_sparql_ast`, and verifying `tpl_uc001_circuit_assurance_context` against Layer 4)
  - `data/semantic_store/stored_sparql_templates.yaml` (deleted hand-coded version and regenerated 100% by `compile_stored_sparql_templates`)
  - `data/golden_reference/stored_sparql_templates.yaml` (golden reference snapshot of the pipeline-generated catalog)
- **Files Modified:**
  - `config.yaml` (added `template_compiler_prompt_path` under `layer3_nl2semantics`)
  - `src/models.py` (added `template_compiler_prompt_path`, `StoredSparqlTemplate`, `StoredSparqlTemplateCatalog`, `TemplateCompileResult`)
  - `src/layer3/__init__.py` (exported `compile_stored_sparql_templates`)
  - `src/layer3/nl2semantics_engine.py` (fail-fast `RuntimeError` when `stored_sparql_templates.yaml` is missing)
  - `src/state_manager.py` (added `stored_sparql_templates.yaml` to `DT-00` `reset_to_clean_slate`)
  - `scripts/run_dt01c_pdf_bites_gate2.py` (auto-compiles templates on `--mode approve`, and updates `data/golden_reference/` when `--update-golden-ref` is set)
  - `scripts/run_rt05_layer3_modes.py` (added `--compile-templates` flag)
  - `tests/test_step1_state_and_config.py` & `tests/test_step6_layer3_nl2semantics.py` (added `DT-00` deletion, fail-fast `RuntimeError`, and `compile_stored_sparql_templates` tests)
  - `README.md` (documented `--compile-templates` and `DT-01c --mode approve` auto-compilation)
- **Deviations (Gate 4):** None.
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **40 passed** in 4.72s (0 failures, 0 `DeprecationWarning`, 0 `FutureWarning`).
  - Live `.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --compile-templates --mode dual_comparison --circuit-id CIR-994821`:
    - Compiled **3** AST-validated SPARQL templates (`verified rows=1`) via `gemini-3.8-flash` into `data/semantic_store/stored_sparql_templates.yaml`.
    - **Voicebox Hybrid**: `template=tpl_uc001_circuit_assurance_context`, `ast_passed=True`, `rows=1`, `latency_ms=9681.15`, `0` missing fields.
    - **Zero-Shot Shadow**: `ast_passed=True`, `rows=3`, `latency_ms=91785.43`, `missing_fields=11`.
    - **Zero-Copy Invariant**: `On-Disk virtual:ib Triples After: 0`.
  - `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: All Track B & Layer 3/CQRS elements verified in expected promoted/active states.

