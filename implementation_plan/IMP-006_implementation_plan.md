# Implementation Plan: `IMP-006` — Development Step 4 (`DT-01c`: Prong 3 PDF BITES Extractor, Fuzzy Entity Resolution & Two-Phase Mandatory HITL Gate 2 Lock)

## 1. Unique Reference ID
`IMP-006`

## 2. Objective & Scope
Implement **Development Step 4 (Stage 2 Activity B3 Part 2 — Scenario `DT-01c`)** inside `d:/Telecom Agentic AI Demo/` strictly scoped to Prong 3 PDF BITES extraction, `rapidfuzz` entity resolution, and the Two-Phase Mandatory HITL Gate 2 workflow:
- **Fail-Fast Prerequisite Check:** Verify `DT-01a` is `LOCKED_APPROVED` (`tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `LOCKED_APPROVED` in `hitl_gate1_ontology_mapping_review.html`). Never auto-run `DT-01a` or `DT-01b`; gracefully handle optional `DT-01b` outputs (`reports/shacl_quarantine_summary.json` / `<urn:telco:graph:ref:catalog>`).
- **100% Document-Independent PDF BITES Extractor & Fuzzy ER (`src/track_b/s3_pdf_bites_er_ingestor.py` & `prompts/s3_pdf_bites_extractor_prompt.md`):**
  - Zero hardcoded page numbers, chapter numbers, hardware SKUs, or customer names in Python code.
  - Dynamically introspect all PDFs in `data/raw_sources/pdf/` using `pypdf` (page count, page-by-page text, SHA-256 hash).
  - Dynamically discover canonical `tmf:Customer` and hardware/device records from SQLite via `mappings/cmdb_r2rml.ttl` + valid `tmf:ServiceSpecification` SKUs from `<urn:telco:graph:ref:catalog>`.
  - Invoke Gemini via `src/llm_client.py` (`resolve_model_for_component(config, "track_b_pdf_bites")`, zero heuristic fallback) to classify pages (`RELEVANT_EXTRACTED` vs. `EXCLUDED_DISTRACTOR_PAGE`), extract `GLOBAL_SCOPE` and `DOCUMENT_SCOPE` structured BITES triples + document lifecycle metadata, and emit 4 HITL Gate 2 verification questions.
  - Run deterministic `rapidfuzz` similarity scoring against canonical CMDB customers (`0.75 * raw_ratio + 0.25 * legal_suffix_normalized_ratio`) to propose Golden ID bridge triples (`owl:sameAs` / `skos:exactMatch` / `telco:resolvedToCanonicalCustomer`) inside `[0.85, 0.95]` HITL review band.
- **Two-Phase HITL Gate 2 Workflow (`scripts/run_dt01c_pdf_bites_gate2.py`):**
  - `--mode candidate` (default): Write `data/semantic_store/gate2_candidate_proposal.json` and `reports/hitl_gate2_ingestion_er_curation.html` (`.md`), keeping BITES/ER/lifecycle graphs unpromoted in `knowledge_graph.trig`, printing the 4 HITL Gate 2 verification questions, and transitioning `SYS-01` Element 4 to `CURATION_PENDING (Awaiting HITL Gate 2)`.
  - `--mode approve`: Populate `<urn:telco:graph:bites:doc-hw-v4>`, `<urn:telco:graph:bites:doc-msa-v1>`, `<urn:telco:graph:meta:doc-lifecycle>`, and `<urn:telco:graph:bridge:er>` in `knowledge_graph.trig` (keeping `<urn:telco:graph:virtual:ib>` at `0` triples and preserving `<urn:telco:graph:tbox:sid-etom>` and `<urn:telco:graph:ref:catalog>`), update Gate 2 reports to `PROMOTED`, transition `SYS-01` Element 4 to `PROMOTED`, and optionally copy `knowledge_graph.trig` and `excel_catalog_rml.yaml` to `data/golden_reference/` when `--update-golden-ref` is passed.
  - `--interactive`: Run Phase 1, prompt operator in console, and run Phase 2 upon approval.

---

## 3. Key Design Decisions
1. **Dynamic CMDB Inventory Discovery (`mappings/cmdb_r2rml.ttl` + SQLite):** Parse `cmdb_r2rml.ttl` via `rdflib` to locate `rr:TriplesMap` entries for `tmf:Customer` and hardware/device classes, extract `rr:tableName` and mapped columns, and query SQLite dynamically.
2. **Deterministic `rapidfuzz` Composite ER Scoring:** Combine `rapidfuzz.fuzz.ratio` (`0.75`) and legal-suffix-stripped `rapidfuzz.fuzz.token_sort_ratio` (`0.25`) to score customer mentions against canonical CMDB customers (e.g., `"A Corporate Enterprise B.V."` vs. `"A Corporate Enterprise"` -> `~0.917` inside `[0.85, 0.95]`).
3. **Structured BITES Triples (`ExtractedBitesTriple`):** Gemini outputs schema-validated structured triples (`subject_iri`, `predicate_qname`, `object_value`, `object_kind`, `datatype_qname`) sanitized via `src/llm_client.py`, which are deterministically compiled into `rdflib` Named Graphs on `--mode approve`.
4. **Centralized Configuration (`config.yaml`):** Add `pdf_bites_prompt_template_path`, `gate2_candidate_proposal_path`, `er_review_band_min`, and `er_review_band_max` under `track_b_ingestion_and_er`.

---

## 4. Step-by-Step Implementation Plan

### Step 1: Configuration & Pydantic v2 Models
- Update `config.yaml` (`track_b_ingestion_and_er`) with:
  - `pdf_bites_prompt_template_path: "prompts/s3_pdf_bites_extractor_prompt.md"`
  - `gate2_candidate_proposal_path: "data/semantic_store/gate2_candidate_proposal.json"`
  - `er_review_band_min: 0.85`
  - `er_review_band_max: 0.95`
- Update `src/models.py`:
  - Extend `TrackBIngestionAndErSettings`.
  - Add Step 4 Pydantic v2 models: `PdfPageIntrospection`, `PdfDocumentIntrospection`, `PdfCorpusIntrospection`, `CanonicalCustomerRecord`, `PdfPageRelevanceDecision`, `ExtractedBitesTriple`, `PdfDocumentExtractionProposal`, `CustomerMentionCandidate`, `FuzzyErMatchProposal`, `BitAndErGate2CandidateProposal`, `Dt01cExecutionResult`.

### Step 2: Externalized Prompt & Prong 3 BITES + Fuzzy ER Engine
- Create `prompts/s3_pdf_bites_extractor_prompt.md`.
- Create `src/track_b/s3_pdf_bites_er_ingestor.py` implementing:
  - `validate_dt01a_prerequisite(config, root_dir)`
  - `introspect_pdf_corpus(pdf_dir)` (`pypdf` + SHA-256)
  - `discover_canonical_cmdb_entities(r2rml_path, sqlite_path, trig_path)`
  - `generate_bites_proposal_via_llm(...)` (via `src/llm_client.py`, zero heuristic fallback)
  - `resolve_customer_mentions_fuzzy(...)` (`rapidfuzz` composite scoring)
  - `write_gate2_curation_reports(...)` (`.html` + `.md`)
  - `compile_and_promote_gate2_graphs(...)` (idempotent TriG update)
  - `run_dt01c_pdf_bites_gate2(...)`

### Step 3: CLI Runner, `SYS-01` Inspector & `DT-00` Reset Integration
- Create `scripts/run_dt01c_pdf_bites_gate2.py` (`--mode candidate|approve`, `--interactive`, `--update-golden-ref`).
- Update `src/state_inspector.py` (`_inspect_element_4_bites_and_er`) to dynamically aggregate `<urn:telco:graph:bites:*>` graphs, `<urn:telco:graph:bridge:er>`, and `gate2_candidate_proposal.json` / `hitl_gate2_ingestion_er_curation.html` for `EMPTY`, `CURATION_PENDING (Awaiting HITL Gate 2)`, and `PROMOTED` states.
- Update `src/state_manager.py` (`reset_to_clean_slate`) to also delete `gate2_candidate_proposal.json`.

### Step 4: Unit Tests, Docs & Live Verification (`CURATION_PENDING` Pause)
- Create `tests/test_step4_dt01c_pdf_bites_gate2.py` verifying:
  1. Zero hardcoded page numbers, chapter numbers, hardware SKUs, or customer names in `s3_pdf_bites_er_ingestor.py`.
  2. Fail-fast check when `DT-01a` is missing or not `LOCKED_APPROVED` (and graceful handling when `DT-01b` is absent).
  3. Deterministic `rapidfuzz` composite scoring (`~0.917` inside `[0.85, 0.95]`).
  4. Two-phase `--mode candidate` (`CURATION_PENDING`, 4 Gate 2 verification questions, 0 BITES/ER triples persisted) -> `--mode approve` (`PROMOTED`, `<urn:telco:graph:bites:doc-hw-v4>`, `<urn:telco:graph:bites:doc-msa-v1>`, `<urn:telco:graph:meta:doc-lifecycle>`, `<urn:telco:graph:bridge:er>` populated, `<urn:telco:graph:virtual:ib>` = 0 triples, `SYS-01` Element 4 `PROMOTED`) -> `DT-00` reset (`EMPTY`).
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\run_dt01c_pdf_bites_gate2.py --mode candidate` and `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py` so the workspace pauses at HITL Gate 2 for human review.
- Update `README.md` and append the Gate 5 Implementation Summary to `implementation_plan/IMP-006_implementation_plan.md`.

---

## Implementation Summary
- **Configuration & Models (`config.yaml`, `src/models.py`):** Added `pdf_bites_prompt_template_path`, `gate2_candidate_proposal_path`, `er_review_band_min` (`0.85`), and `er_review_band_max` (`0.95`), plus Step 4 Pydantic v2 models (`PdfPageIntrospection`, `PdfDocumentIntrospection`, `PdfCorpusIntrospection`, `CanonicalCustomerRecord`, `PdfPageRelevanceDecision`, `ExtractedBitesTriple`, `CustomerMentionCandidate`, `PdfDocumentExtractionProposal`, `PdfBitesLlmProposal`, `FuzzyErMatchProposal`, `BitAndErGate2CandidateProposal`, `Dt01cExecutionResult`).
- **100% Document-Independent PDF BITES & Fuzzy ER Engine (`prompts/s3_pdf_bites_extractor_prompt.md`, `src/track_b/s3_pdf_bites_er_ingestor.py`):**
  - Implemented `validate_dt01a_prerequisite` (fail-fast on `DT-01a` only; graceful handling when `DT-01b` is absent).
  - Implemented dynamic `pypdf` corpus introspection (`introspect_pdf_corpus`) and dynamic CMDB entity discovery via `mappings/cmdb_r2rml.ttl` (`rr:sqlQuery` / `rr:tableName`) + SQLite (`discover_canonical_entities`).
  - Integrated `src/llm_client.py` (`resolve_model_for_component(config, "track_b_pdf_bites")`) with zero heuristic fallback and deterministic `rapidfuzz` composite ER scoring (`0.75 * raw + 0.25 * legal-suffix-normalized`).
- **Two-Phase HITL Gate 2 CLI, `SYS-01`, `DT-00` & Tests:**
  - Created `scripts/run_dt01c_pdf_bites_gate2.py` (`--mode candidate`, `--mode approve`, `--interactive`, `--update-golden-ref`).
  - Updated `src/state_inspector.py` (`_inspect_element_4_bites_and_er`) and `src/state_manager.py` (`reset_to_clean_slate` cleaning `gate2_candidate_proposal.json`).
  - Created `tests/test_step4_dt01c_pdf_bites_gate2.py`.
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **26 passed** (0 `DeprecationWarning`, 0 `FutureWarning`).
  - Live `.\.venv\Scripts\python.exe scripts\run_dt01c_pdf_bites_gate2.py --mode candidate` (`gemini-3.8-flash` on Vertex AI): paused at `CURATION_PENDING` with 2 active PDFs, 16 `GLOBAL_SCOPE` candidate triples, 8 `DOCUMENT_SCOPE` candidate triples, 3 ER links, 2 quarantined Excel rows, 0 `virtual:ib` triples, and 4 HITL Gate 2 verification questions.
  - Live `.\.venv\Scripts\python.exe scripts\run_dt01c_pdf_bites_gate2.py --mode approve --update-golden-ref` (after Q1–Q4 HITL Gate 2 approval): promoted `16` `GLOBAL_SCOPE` triples (`<urn:telco:graph:bites:doc-hw-v4>`), `8` `DOCUMENT_SCOPE` triples (`<urn:telco:graph:bites:doc-msa-v1>`), `16` `DOCUMENT_LIFECYCLE` triples (`<urn:telco:graph:meta:doc-lifecycle>`), and `5` ER bridge triples (`<urn:telco:graph:bridge:er>`) into `data/semantic_store/knowledge_graph.trig` (`0` persisted triples in `<urn:telco:graph:virtual:ib>`), and snapshotted `knowledge_graph.trig` & `excel_catalog_rml.yaml` to `data/golden_reference/`.
  - Live `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`: Elements 1–4 verified in their final states (`LOCKED_APPROVED`, `BOUND_ZERO_COPY`, `LOADED_WITH_QUARANTINE`, and `PROMOTED`).



