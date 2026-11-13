# Implementation Plan — `IMP-004-R1`: Development Step 2 Refinement (100% Use-Case & Database-Schema Independent Prong 1 AI Schema Profiler + True Two-Phase Interactive HITL Gate 1 Workflow)

## 1. Unique Reference ID
- **Reference ID:** `IMP-004-R1` (Refines `IMP-004`)
- **Incremental Build Step:** Step 2 of 11 (`ADR-TELCO-UC001-ACT03-V1` Section 6 / Section 10 & `PLAN-TELCO-AGENT-UC1-2026-V2` Section 5)
- **Scenario ID:** `DT-01a`

---

## 2. Objective & Scope

### Objective
Refine Step 2 (`DT-01a`) to enforce **100% Use-Case & Database-Schema Independence** in `src/track_b/s1_cmdb_tbox_profiler.py`, live **Vertex AI / Gemini (`google-genai`) structured profiling** with **zero heuristic fallback**, and a **True Two-Phase Interactive HITL Gate 1 Workflow**:
1. Create the two reusable, schema-independent knowledge inputs on disk and register their paths in `config.yaml`:
   - **Input 1 (Use Case Definition):** `data/raw_sources/uc001_use_case_charter.md`
   - **Input 2 (Generic Telecom Terminology Reference):** `data/reference_standards/tmf_sid_etom_vocab.json` (32+ standard TM Forum SID `GB922` classes across all 8 domains, standard eTOM `GB921` Level 2/3 processes, and QUDT units).
2. Externalize the AI Schema Profiler prompt template in `prompts/s1_cmdb_schema_profiler_prompt.md` per `AGENTS.md` Part 2.7.
3. Refactor `src/track_b/s1_cmdb_tbox_profiler.py` so the Python code contains **zero hardcoded table names** (such as `T_OSS_CUST_PARTY` or `T_BILLING_AUDIT_NOISE`) and **zero hardcoded column names**:
   - Dynamically introspect any SQLite database (`sqlite_master`, `PRAGMA table_info`, `PRAGMA foreign_key_list`, low-cardinality distinct value distributions, and `SELECT * LIMIT 5` sample rows).
   - Invoke Gemini via `google-genai` (`GEMINI_API_KEY` if set in environment, otherwise Vertex AI on GCP project `telecom-agentic-ai-demo` in `europe-west4` authenticated as `j.swanenburg@planet.nl`, failing fast if neither is available) using `response_schema=CandidateOntologyAndMappingProposal`, saving the structured proposal at `data/semantic_store/gate1_candidate_proposal.json`.
   - Generically compile `data/semantic_store/tbox_sid_etom.ttl`, `data/semantic_store/knowledge_graph.trig`, `mappings/cmdb_r2rml.ttl`, and `shapes/*.ttl` purely from `CandidateOntologyAndMappingProposal`.
4. Enforce a True Two-Phase HITL Gate 1 Workflow in `scripts/run_dt01a_cmdb_gate1.py`:
   - **`--mode candidate` (NEW DEFAULT)**: Runs dynamic SQLite introspection + Gemini structured profiling, writes `data/semantic_store/gate1_candidate_proposal.json` and `reports/hitl_gate1_ontology_mapping_review.html` (`.md`), leaves `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `shapes/*.ttl` unmaterialized (`SYS-01` Element 1 = `CANDIDATE_PROPOSED (Awaiting HITL Approval)`, Element 2 = `UNBOUND (Pending Gate 1 Lock)`), and prints the **HITL Gate 1 Architect Verification Questions** to the console.
   - **`--mode approve` (or `--interactive` when confirmed)**: Reads `gate1_candidate_proposal.json`, compiles and writes `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `shapes/*.ttl`, updates the HITL report to `LOCKED_APPROVED`, and transitions `SYS-01` Element 1 $\rightarrow$ `LOCKED_APPROVED` and Element 2 $\rightarrow$ `BOUND_ZERO_COPY`.

---

## 3. Key Design Decisions

1. **GCP Vertex AI Provisioning & `google-genai` Authentication (`Option 1B` if set, else `Option 1A` Vertex AI)**:
   - **Active GCP Account:** Set `j.swanenburg@planet.nl` as the active `gcloud` account and verify Application Default Credentials (ADC) for `telecom-agentic-ai-demo`.
   - **Terraform API & Quota Project Enablement (`./terraform/`):** Configure `user_project_override = true` and `billing_project = var.project_id` in `terraform/providers.tf`, enable `aiplatform.googleapis.com` and `serviceusage.googleapis.com` in `terraform/apis.tf`, grant `roles/serviceusage.serviceUsageConsumer` in `terraform/iam.tf`, and execute `terraform init` and `terraform apply` on `./terraform/` (`project_id = "telecom-agentic-ai-demo"`, `region = "europe-west4"`).
   - **Client Resolution (`src/track_b/s1_cmdb_tbox_profiler.py`):**
     - If `GEMINI_API_KEY` is present in `os.environ`, initialize `genai.Client(api_key=os.environ["GEMINI_API_KEY"])`.
     - Otherwise, initialize `genai.Client(vertexai=True, project=config.gcp.project_id, location=config.ai.location, credentials=OAuth2Credentials(token=token, quota_project_id=config.gcp.project_id))` using `gemini-3.8-flash` on the `global` Vertex AI endpoint (`ai.location: "global"`, while `gcp.region: "europe-west4"` remains locked for all regional Terraform resources).
     - **Zero Heuristic Fallback:** If the LLM call fails or credentials are missing, fail fast with an explicit error (`RuntimeError`) per `AGENTS.md` Part 2.3.

2. **Two Reusable, Schema-Independent Knowledge Inputs (`config.yaml`)**:
   - Extend `track_b_ingestion_and_er` in `config.yaml` and `TrackBIngestionAndErSettings` in `src/models.py` with:
     - `use_case_charter_path: "data/raw_sources/uc001_use_case_charter.md"`
     - `tmf_sid_etom_vocab_path: "data/reference_standards/tmf_sid_etom_vocab.json"`
     - `gate1_candidate_proposal_path: "data/semantic_store/gate1_candidate_proposal.json"`
     - `profiler_prompt_template_path: "prompts/s1_cmdb_schema_profiler_prompt.md"`
   - **`DT-00` Preservation (`src/state_manager.py`):** Preserve `data/raw_sources/uc001_use_case_charter.md` and `data/reference_standards/tmf_sid_etom_vocab.json` across clean-slate wipes while deleting `data/semantic_store/gate1_candidate_proposal.json`.

3. **100% Schema & Use-Case Independent Profiler & Compiler (`src/track_b/s1_cmdb_tbox_profiler.py`)**:
   - **Dynamic SQLite Introspection (`introspect_sqlite_database`):**
     - Queries `sqlite_master` for all non-system tables.
     - For each table, runs `PRAGMA table_info`, `PRAGMA foreign_key_list`, row count (`SELECT COUNT(*)`), distinct value distribution for low-cardinality columns ($\le 10$ distinct values), null count per column, and `SELECT * LIMIT 5` sample rows.
   - **Structured LLM Proposal (`CandidateOntologyAndMappingProposal`):**
     - Contains:
       - `proposed_classes`: List of pruned OWL classes selected from `tmf_sid_etom_vocab.json` (IRI, `rdfs:label`, `rdfs:comment`, `subClassOf`, aligned eTOM process IDs, and $\ge 2$ `skos:altLabel` business synonyms).
       - `proposed_properties`: List of OWL Object & Datatype properties (IRI, property type, domain class IRI, range class/datatype IRI, `qudt_unit_iri`, `rdfs:label`, `rdfs:comment`, and $\ge 2$ `skos:altLabel` synonyms).
       - `etom_processes`: List of in-scope eTOM processes (`1.3.7`, `1.4.5`, etc.).
       - `table_mappings`: List of table profiling & R2RML mapping specifications (`table_name`, `total_rows`, `active_rows`, `table_disposition` [`BOUND_VIRTUAL_GRAPH` | `EXCLUDED_NOISE`], `exclusion_rationale`, `triples_map_id`, `sql_query`, `subject_iri_template`, `target_class_iris`, `scd2_filter_column`, `columns`: list of `ColumnProfileEntry`, and `predicate_object_mappings`: list of R2RML predicate-object specifications).
       - `scd2_temporal_analysis`: Discovered SCD Type 2 versioned entity verification (entity identifier, expired row ID & spec, active row ID & spec, shadow enum translation summary, unit normalization summary).
       - `shacl_shapes`: Structured SHACL NodeShape specifications compiled to `shapes/*.ttl`.
       - `architect_verification_questions`: List of 4 targeted HITL Gate 1 verification questions for the human architect.
   - **Generic Artifact Compilation (`compile_approved_artifacts_from_proposal`):**
     - Generates `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, `shapes/service_spec_shape.ttl`, and `shapes/trouble_ticket_shape.ttl` purely from `CandidateOntologyAndMappingProposal` without any hardcoded table or column names in Python.

4. **True Two-Phase Interactive HITL Gate 1 (`scripts/run_dt01a_cmdb_gate1.py` & `src/state_inspector.py`)**:
   - **Phase 1 (`--mode candidate`, default):**
     - Produces `data/semantic_store/gate1_candidate_proposal.json` and `reports/hitl_gate1_ontology_mapping_review.html` (`.md`).
     - Ensures `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `shapes/*.ttl` are **not** written yet.
     - `SYS-01` (`src/state_inspector.py`) detects `gate1_candidate_proposal.json` when `tbox_sid_etom.ttl` is absent and reports:
       - Element 1: `CANDIDATE_PROPOSED (Awaiting HITL Approval)` (with proposed class, property, and `skos:altLabel` counts)
       - Element 2: `UNBOUND (Pending Gate 1 Lock)` (`Persisted triples on disk: 0 | Bound SQLite tables: 0 | Pending HITL Gate 1 approval`)
     - Prints the **HITL Gate 1 Architect Verification Questions** and next-step approval instructions to the console.
   - **Phase 2 (`--mode approve` or `--interactive`):**
     - Loads `data/semantic_store/gate1_candidate_proposal.json` (or runs Phase 1 first if not yet generated), compiles and locks `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `shapes/*.ttl`, runs the Evaluator Agent critique, updates `reports/hitl_gate1_ontology_mapping_review.html` (`.md`) to `LOCKED_APPROVED`, and transitions `SYS-01` Element 1 $\rightarrow$ `LOCKED_APPROVED` and Element 2 $\rightarrow$ `BOUND_ZERO_COPY`.

---

## 4. Step-by-Step Implementation Plan

### Step 1: GCP Auth & Terraform Enablement of Vertex AI (`aiplatform.googleapis.com`)
- Set `gcloud config set account j.swanenburg@planet.nl`.
- Run `terraform init` and `terraform apply -auto-approve` in `./terraform/` to enable `aiplatform.googleapis.com` (and project services defined in `./terraform/apis.tf`) on `telecom-agentic-ai-demo`.

### Step 2: Create Reusable Knowledge Inputs & Externalized Prompt Template
- Create `data/raw_sources/uc001_use_case_charter.md`.
- Create `data/reference_standards/tmf_sid_etom_vocab.json` (32+ TM Forum SID classes across all 8 domains, eTOM L2/L3 processes, QUDT units).
- Create `prompts/s1_cmdb_schema_profiler_prompt.md`.
- Update `config.yaml`, `src/models.py`, and `src/state_manager.py`.

### Step 3: Refactor `src/track_b/s1_cmdb_tbox_profiler.py` for 100% Schema/Use-Case Independence & Two-Phase Gate 1
- Remove all hardcoded SQLite table and column names from `src/track_b/s1_cmdb_tbox_profiler.py`.
- Implement `introspect_sqlite_database()`, `generate_candidate_proposal_via_llm()`, `compile_approved_artifacts_from_proposal()`, and two-phase `run_dt01a_cmdb_profiler(mode="candidate" | "approve")`.

### Step 4: Update `SYS-01` (`src/state_inspector.py`) & CLI (`scripts/run_dt01a_cmdb_gate1.py`)
- Update `_inspect_element_1_tbox` and `_inspect_element_2_virtual_sql` in `src/state_inspector.py` to support the two-phase states (`CANDIDATE_PROPOSED (Awaiting HITL Approval)` / `UNBOUND (Pending Gate 1 Lock)` vs. `LOCKED_APPROVED` / `BOUND_ZERO_COPY`).
- Update `scripts/run_dt01a_cmdb_gate1.py` so `--mode candidate` is the default, printing the HITL Gate 1 Architect Verification Questions and supporting `--mode approve` and `--interactive`.

### Step 5: Update Unit Tests & Execute Verification (`tests/test_step2_dt01a_cmdb_gate1.py`)
- Update `tests/test_step2_dt01a_cmdb_gate1.py` to verify:
  1. Zero hardcoded SQLite table or column names exist anywhere in `src/track_b/s1_cmdb_tbox_profiler.py`.
  2. Running `--mode candidate` pauses at `CANDIDATE_PROPOSED (Awaiting HITL Approval)` / `UNBOUND (Pending Gate 1 Lock)` without materializing `tbox_sid_etom.ttl` or `cmdb_r2rml.ttl`, and emits the HITL Gate 1 verification questions.
  3. Running `--mode approve` compiles and locks `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `shapes/*.ttl` from `gate1_candidate_proposal.json` and transitions `SYS-01` to `LOCKED_APPROVED` / `BOUND_ZERO_COPY`.
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\reset_demo_state.py`, then `.\.venv\Scripts\python.exe scripts\run_dt01a_cmdb_gate1.py --mode candidate`, followed by `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py` so the workspace pauses at the HITL Gate 1 review step as requested.

---

## 5. Gate 5: Implementation Summary

### What Was Built
1. **100% Schema-Independent & Use-Case-Independent Knowledge Inputs**:
   - Created `data/raw_sources/uc001_use_case_charter.md` (Input 1: natural-language Use Case Charter for `UC-001` covering business objective, eTOM `1.3.7` / `1.4.5` scope, SLA triage, optical DDM recalibration vs. field dispatch).
   - Created `data/reference_standards/tmf_sid_etom_vocab.json` (Input 2: generic telecom reference vocabulary with 35 standard TM Forum SID `GB922` classes across all 8 domains, 10 eTOM `GB921` Level 2/3 processes, and 8 QUDT units).
   - Created externalized system prompt `prompts/s1_cmdb_schema_profiler_prompt.md` per `AGENTS.md` Part 2.7.
2. **100% Schema-Independent AI Profiler & W3C Compiler (`src/track_b/s1_cmdb_tbox_profiler.py`)**:
   - Removed all hardcoded SQLite table and column names from `src/track_b/s1_cmdb_tbox_profiler.py` (verified via automated source inspection in `test_zero_hardcoded_table_or_column_names_in_profiler_code`).
   - Implemented `introspect_sqlite_database()` to dynamically discover all tables (`sqlite_master`), column metadata (`PRAGMA table_info`), foreign keys (`PRAGMA foreign_key_list`), distinct low-cardinality codes, and sample rows (`SELECT *`).
   - Implemented `generate_candidate_proposal_via_llm()` using `google-genai` (`GEMINI_API_KEY` if set, otherwise Vertex AI `gemini-3.8-flash` on `telecom-agentic-ai-demo` with `location="global"` and `quota_project_id="telecom-agentic-ai-demo"`, with zero heuristic fallback).
   - Implemented generic W3C Turtle, TriG, R2RML, and SHACL compilers (`compile_tbox_turtle_from_proposal`, `compile_r2rml_turtle_from_proposal`, `compile_shacl_shape_turtle`) that compile directly from `CandidateOntologyAndMappingProposal`.
3. **True Two-Phase Interactive HITL Gate 1 (`scripts/run_dt01a_cmdb_gate1.py` & `src/state_inspector.py`)**:
   - Made `--mode candidate` the default in `scripts/run_dt01a_cmdb_gate1.py` and added `--interactive`.
   - In `--mode candidate`, `run_dt01a_cmdb_profiler` writes `data/semantic_store/gate1_candidate_proposal.json` and `reports/hitl_gate1_ontology_mapping_review.html` (`.md`), leaves `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and `shapes/*.ttl` unlocked, prints the 4 **HITL Gate 1 Architect Verification Questions**, and leaves `SYS-01` (`inspect_demo_state.py`) at Element 1 = `CANDIDATE_PROPOSED (Awaiting HITL Approval)` and Element 2 = `UNBOUND (Pending Gate 1 Lock)`.
   - In `--mode approve` (or `--interactive` when confirmed), `run_dt01a_cmdb_profiler` reads `gate1_candidate_proposal.json`, compiles and locks `tbox_sid_etom.ttl`, `knowledge_graph.trig` (`0` persisted triples in `<urn:telco:graph:virtual:ib>`), `cmdb_r2rml.ttl`, and `shapes/*.ttl`, updates the HITL report to `LOCKED_APPROVED`, and transitions `SYS-01` Element 1 $\rightarrow$ `LOCKED_APPROVED` and Element 2 $\rightarrow$ `BOUND_ZERO_COPY`.

### Files Created or Modified
- **Created:**
  - `implementation_plan/IMP-004-R1_implementation_plan.md`
  - `data/raw_sources/uc001_use_case_charter.md`
  - `data/reference_standards/tmf_sid_etom_vocab.json`
  - `prompts/s1_cmdb_schema_profiler_prompt.md`
  - `data/semantic_store/gate1_candidate_proposal.json`
- **Modified:**
  - `config.yaml`
  - `src/models.py`
  - `src/state_manager.py`
  - `src/state_inspector.py`
  - `src/track_b/s1_cmdb_tbox_profiler.py`
  - `scripts/run_dt01a_cmdb_gate1.py`
  - `tests/test_step1_state_and_config.py`
  - `tests/test_step2_dt01a_cmdb_gate1.py`
  - `terraform/providers.tf`, `terraform/variables.tf`, `terraform/apis.tf`, `terraform/iam.tf`, `terraform/terraform.tfstate`
  - `README.md`

### Approved Deviations Taken During Gate 4
- Enabled `serviceusage.googleapis.com`, `cloudresourcemanager.googleapis.com`, and `roles/serviceusage.serviceUsageConsumer` via Terraform (`18` total resources managed in `terraform/terraform.tfstate`), configured `user_project_override = true` and `billing_project = var.project_id` in `terraform/providers.tf`, and passed `quota_project_id=config.gcp.project_id` to `OAuth2Credentials` in `src/track_b/s1_cmdb_tbox_profiler.py`.
- Configured `gemini-3.8-flash` on the Vertex AI `global` endpoint (`ai.location: "global"`, while keeping `gcp.region: "europe-west4"` for all regional Terraform resources) per approved Gate 4 Option A.

### Verification Results
- **Unit Test Suite (`pytest -v -W error::DeprecationWarning -W error::FutureWarning`)**: **18 passed in 1.24s** with zero warnings or deprecations.
- **Live Two-Phase Execution**: Executed `reset_demo_state.py` $\rightarrow$ `run_dt01a_cmdb_gate1.py --mode candidate` (live `gemini-3.8-flash` call on Vertex AI) $\rightarrow$ `inspect_demo_state.py`, pausing the workspace in the `CANDIDATE_PROPOSED` / `UNBOUND` state for human architect review.


