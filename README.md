# Telecom Agentic AI Demo (`UC-001`)

Enterprise Reference Implementation demonstrating the **5-Layer Telecom Agentic AI & Semantic Knowledge Fabric Architecture** (`ARCH-TELCO-AGENT-EKG-2026-V3`), the **First Use Case Implementation Plan** (`PLAN-TELCO-AGENT-UC1-2026-V2`), and the **Component Design Decisions Specification** (`ADR-TELCO-UC001-ACT03-V1`) for **Use Case UC-001: Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration**.

---

## 1. Architecture & Use Case Overview (`UC-001`)

- **TM Forum Alignment**:
  - **eTOM Processes**: `1.3.7` Problem Handling & `1.4.5` Resource Trouble Management.
  - **SID Entity Spine**: `Customer (CUST-ENT-409)` $\rightarrow$ `CustomerFacingService (CIR-994821)` $\rightarrow$ `ServiceSpecification (ETH-10G-GOLD)` $\rightarrow$ `ResourceFacingService (RFS-OLT04-P12)` $\rightarrow$ `PhysicalResource (CPE-ASN-7741 / OLT04-P12)` $\rightarrow$ `PhysicalResourceSpec (NOK-7210-SAS-Mxp)`.
- **Three Functional Planes**:
  1. **Design-Time Build Plane**: Multi-procedure SOP-to-Skill compilation (`SOP-ASSUR-402` sliced from a 6-section Master NOC Runbook with Southbound MCP Catalog verification) and 3-pronged knowledge ingestion (SQL Virtual Graph, Excel Materialized Reference Graph with `pySHACL` quarantine, PDF BITES Extraction + Entity Resolution).
  2. **Runtime Operational Read Plane (Layers 1–5)**: Dual-Interface Thin-Client MCP Orchestrator (Layer 1, `Option 1D`), Deterministic LangGraph State-Machine Worker Agent (Layer 2, `Option 2.2A`), Dual-Mode NL2Semantics Conceptual TBox Translator (Layer 3, `Option 3C-Dual`), Deterministic `rdflib.Dataset` Named Graph & R2RML-to-SQLite Pushdown Federation Compiler (Layer 4, `Option 4A`), and Heterogeneous OSS/BSS Data Sources (Layer 5).
  3. **Runtime CQRS Action Plane (`Option 6A-Generic`)**: Real-time non-cached hardware probing + port mutex locking (`cqrs://singleton-check/probe_resource_state`) and `pySHACL`-validated, token-bucket-governed mutations (`cqrs://transactional-write/execute_governed_mutation`, `cqrs://transactional-write/commit_validated_graph_triples`).

---

## 2. Repository Structure

```text
.
├── config.yaml                          # Master non-secret configuration (with env var overrides)
├── config/
│   └── mcp_primitives_catalog.json      # Southbound MCP Platform Primitive Catalog (Option 2.1D-Catalog & 6A-Generic)
├── requirements.txt                     # Python W3C & Agentic AI verification stack dependencies
├── README.md                            # Project documentation
├── documents/                           # Architecture Blueprint v3, Implementation Plan v2, UC-001 v2, ADR v1
├── implementation_plan/                 # Gated Implementation Plans (IMP-001, IMP-002, IMP-003, ...)
├── logs/                                # Local rotating log files (excluded from Git via .gitignore)
├── data/
│   ├── raw_sources/                     # Frozen Stage 0 (Activity 0.2) noisy enterprise raw sources
│   │   ├── sql/                         # Prong 1: cmdb_installed_base.db & cmdb_dump.sql
│   │   ├── excel/                       # Prong 2: Telco_Master_Product_SLA_Catalog_2026.xlsx
│   │   ├── pdf/                         # Prong 3: Vendor_Optical_Hardware_Manual_v4.pdf & MSA PDF
│   │   ├── sop/                         # Multi-SOP Runbook (.docx & .md)
│   │   ├── uc001_use_case_charter.md    # Input 1: Natural-language Use Case Charter for UC-001
│   │   └── STAGE0_ARTIFACT_MANIFEST.md
│   ├── reference_standards/             # Input 2: Generic Telecom Terminology Reference
│   │   └── tmf_sid_etom_vocab.json      # 35+ TMF SID (GB922) classes, eTOM (GB921) processes & QUDT units
│   ├── semantic_store/                  # Active Named Graph store (gate1_candidate_proposal.json, tbox_sid_etom.ttl, knowledge_graph.trig)
│   ├── golden_reference/                # Pre-verified fallback reference artifacts
│   └── cqrs_state/                      # Inspectable CQRS runtime state (cqrs_runtime_state.json)
├── prompts/                             # Externalized LLM system prompt templates (AGENTS.md Part 2.7)
│   └── s1_cmdb_schema_profiler_prompt.md
├── mappings/                            # R2RML virtual SQL mappings & Excel RML rules
├── shapes/                              # Active pySHACL shape files (*.ttl)
├── skills/                              # Compiled Layer 2 Worker Agent skills & guardrails
├── reports/                             # Generated HTML/Markdown dashboards & HITL review reports
├── src/
│   ├── __init__.py
│   ├── models.py                        # Pydantic v2 schemas for config, catalog, CQRS state, DT-00, SYS-01 & DT-01a
│   ├── config.py                        # YAML configuration loader with env var overrides
│   ├── config_loader.py                 # Step 1 configuration loader interface
│   ├── catalog_manager.py               # Southbound MCP Platform Primitive Catalog manager & gap toggle
│   ├── state_manager.py                 # Scenario DT-00 clean-slate wipe & CQRS runtime state reset
│   ├── state_inspector.py               # SYS-01 Live System State Inspector (7 architectural elements)
│   ├── logger.py                        # Dual logger (local rotating file + stdout vs. cloud stdout)
│   ├── stage0_generator.py              # Modular Stage 0 raw sources generator & verifier
│   └── track_b/
│       ├── __init__.py
│       └── s1_cmdb_tbox_profiler.py     # Scenario DT-01a: Prong 1 SQL CMDB Profiler, TBox, SHACL & R2RML
├── scripts/
│   ├── generate_stage0_raw_sources.py   # CLI entrypoint for Stage 0 raw sources generation
│   ├── reset_demo_state.py              # CLI entrypoint for Scenario DT-00 (Wipe & Reset to Clean Slate)
│   ├── inspect_demo_state.py            # CLI entrypoint for SYS-01 (Live System State Inspector)
│   └── run_dt01a_cmdb_gate1.py          # CLI entrypoint for Scenario DT-01a (Prong 1 CMDB & HITL Gate 1)
├── tests/
│   ├── test_config_and_logger.py        # Unit tests for config, env overrides & dual logging
│   ├── test_stage0_generator.py         # Unit tests for Stage 0 generation & fail-fast checks
│   ├── test_step1_state_and_config.py   # Unit tests for Step 1 config lock, MCP catalog, DT-00 & SYS-01
│   └── test_step2_dt01a_cmdb_gate1.py   # Unit tests for Step 2 (DT-01a) CMDB profiler, TBox, R2RML & Gate 1
└── terraform/                           # 100% Terraform-managed GCP infrastructure (europe-west4)
    ├── providers.tf
    ├── variables.tf
    ├── apis.tf
    ├── main.tf
    ├── iam.tf
    ├── outputs.tf
    └── terraform.tfvars
```

---

## 3. Setup & Installation

1. **Create and activate the virtual environment (`.venv`)**:
   ```powershell
   uv venv .venv --python 3.12 --seed
   .\.venv\Scripts\Activate.ps1
   ```
2. **Install dependencies**:
   ```powershell
   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
   ```

---

## 4. Configuration (`config.yaml` & Environment Overrides)

All non-secret settings and relative paths are stored in [`config.yaml`](file:///d:/Telecom%20Agentic%20AI%20Demo/config.yaml) and validated via Pydantic v2 in [`src/config.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/config.py) and [`src/config_loader.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/config_loader.py).

| Environment Variable | Overridden `config.yaml` Key | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `ENV` | `project.environment` | `local` | Execution mode (`local` writes rotating logs to `./logs/`; `cloud` or `K_SERVICE` streams purely to `stdout`) |
| `GCP_PROJECT_ID` | `gcp.project_id` | `telecom-agentic-ai-demo` | Assigned GCP Project ID (1-to-1 workspace mapping) |
| `GCP_REGION` | `gcp.region` | `europe-west4` | Default GCP region (Netherlands) |
| `LOG_LEVEL` | `logging.level` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_DIR` | `logging.log_dir` | `logs` | Relative directory for local rotating log files |
| `STAGE0_RAW_DIR` | `paths.raw_sources_dir` | `data/raw_sources` | Relative output directory for Stage 0 raw sources |
| `STAGE0_SEED` | `stage0.seed` | `42` | Deterministic random seed for Stage 0 data generation |
| `AI_MODEL_NAME` | `ai.model_name` | `gemini-3.8-flash` | Configurable LLM model identifier (Vertex AI `global` endpoint or `GEMINI_API_KEY`) |
| `GEMINI_API_KEY` | *(Optional Auth Override)* | *(unset — uses Vertex AI)* | If set, uses Google AI Studio API key (`Option 1B`); otherwise uses Vertex AI (`Option 1A`) on `telecom-agentic-ai-demo` |
| `LAYER1_TRANSPORT_MODE` | `layer1_orchestrator.transport_mode` | `in_process` | Layer 1 Northbound MCP transport mode (`in_process` or `sse`) |
| `LAYER3_EXECUTION_MODE` | `layer3_nl2semantics.execution_mode` | `dual_comparison` | Layer 3 NL2Semantics mode (`dual_comparison`, `voicebox_hybrid`, `zero_shot_llm`) |
| `CQRS_TELEMETRY_PRESET` | `cqrs_action_plane.active_telemetry_preset` | `branch_a_soft_degradation` | Active hardware telemetry preset (`branch_a_soft_degradation`, `branch_b_hard_fiber_cut`, `branch_c_maintenance_lock`) |

---

## 5. Execution & Unit Testing

### Generate & Verify Stage 0 Raw Data Sources (`Activity 0.2`)
```powershell
.\.venv\Scripts\python.exe scripts\generate_stage0_raw_sources.py
```

### Execute Scenario `DT-00` (Wipe & Reset to Clean Slate)
```powershell
# Reset to clean slate with full MCP Primitive Catalog (TMF621 enabled):
.\.venv\Scripts\python.exe scripts\reset_demo_state.py

# Reset to clean slate with MCP Catalog Gap enabled (TMF621 disabled for Scenario DT-02a):
.\.venv\Scripts\python.exe scripts\reset_demo_state.py --set-catalog-gap true
```

### Execute `SYS-01` (Live System State Inspector)
```powershell
.\.venv\Scripts\python.exe scripts\inspect_demo_state.py
```
Outputs a rich console table and writes:
- `reports/system_state_dashboard.html`
- `reports/system_state_dashboard.md`

### Execute Scenario `DT-01a` (Dynamic AI Schema Profiler, TMF SID/eTOM TBox, R2RML & Two-Phase HITL Gate 1)
```powershell
# Phase 1 (DEFAULT — --mode candidate):
# Dynamically introspects SQLite + Use Case Charter + TMF SID/eTOM Vocab via Gemini (gemini-3.8-flash),
# writes gate1_candidate_proposal.json & hitl_gate1_ontology_mapping_review.html without locking TBox/R2RML,
# and prints the HITL Gate 1 Architect Verification Questions:
.\.venv\Scripts\python.exe scripts\run_dt01a_cmdb_gate1.py

# Phase 2 (--mode approve):
# Compiles and locks tbox_sid_etom.ttl, knowledge_graph.trig, cmdb_r2rml.ttl, and shapes/*.ttl
# from gate1_candidate_proposal.json and transitions SYS-01 to LOCKED_APPROVED / BOUND_ZERO_COPY:
.\.venv\Scripts\python.exe scripts\run_dt01a_cmdb_gate1.py --mode approve

# Interactive Two-Phase Mode (Phase 1 -> Console Prompt -> Phase 2):
.\.venv\Scripts\python.exe scripts\run_dt01a_cmdb_gate1.py --interactive

# Optional: Promote approved Step 2 artifacts into data/golden_reference/:
.\.venv\Scripts\python.exe scripts\run_dt01a_cmdb_gate1.py --mode approve --update-golden-ref
```
Generates:
- **Phase 1 (`--mode candidate`)**:
  - `data/semantic_store/gate1_candidate_proposal.json`
  - `reports/hitl_gate1_ontology_mapping_review.html` & `.md` (`CANDIDATE_PROPOSED`)
- **Phase 2 (`--mode approve`)**:
  - `data/semantic_store/tbox_sid_etom.ttl` & `<urn:telco:graph:tbox:sid-etom>` in `data/semantic_store/knowledge_graph.trig` (`0` persisted triples in `<urn:telco:graph:virtual:ib>`)
  - `mappings/cmdb_r2rml.ttl`
  - `shapes/service_spec_shape.ttl` & `shapes/trouble_ticket_shape.ttl`
  - `reports/hitl_gate1_ontology_mapping_review.html` & `.md` (`LOCKED_APPROVED`)

### Execute Scenario `DT-01b` (Prong 2 Multi-Tab Excel Catalog Profiler & Row-Level `pySHACL` Quarantine Gate)
Requires Step 2 (`DT-01a`) to be `LOCKED_APPROVED` (fails fast otherwise):
```powershell
.\.venv\Scripts\python.exe scripts\run_dt01b_excel_quarantine.py
```
Generates:
- `mappings/excel_catalog_rml.yaml` (declarative RML/mapping spec generated via `src/llm_client.py` using `ai.component_models.track_b_excel_profiler`)
- Populated `<urn:telco:graph:ref:catalog>` inside `data/semantic_store/knowledge_graph.trig` (`18` valid B2B SKUs / `198` triples, preserving `<urn:telco:graph:tbox:sid-etom>` and keeping `<urn:telco:graph:virtual:ib>` at `0` triples)
- `reports/shacl_quarantine_report.html`, `reports/shacl_quarantine_report.md`, and `reports/shacl_quarantine_summary.json` (`2` quarantined dirty rows)

### Execute Scenario `DT-01c` (Prong 3 PDF BITES Extractor, Fuzzy ER & Two-Phase HITL Gate 2)
Requires Step 2 (`DT-01a`) to be `LOCKED_APPROVED` (fails fast otherwise):
```powershell
# Phase 1 (DEFAULT — --mode candidate):
# Dynamically introspects PDFs via pypdf + CMDB customers via cmdb_r2rml.ttl,
# invokes Gemini via src/llm_client.py (track_b_pdf_bites) and rapidfuzz ER scoring,
# writes gate2_candidate_proposal.json & hitl_gate2_ingestion_er_curation.html/.md,
# and pauses SYS-01 Element 4 at CURATION_PENDING (Awaiting HITL Gate 2):
.\.venv\Scripts\python.exe scripts\run_dt01c_pdf_bites_gate2.py --mode candidate

# Phase 2 (--mode approve):
# Compiles and promotes <urn:telco:graph:bites:doc-hw-v4>, <urn:telco:graph:bites:doc-msa-v1>,
# <urn:telco:graph:meta:doc-lifecycle>, and <urn:telco:graph:bridge:er> into knowledge_graph.trig:
.\.venv\Scripts\python.exe scripts\run_dt01c_pdf_bites_gate2.py --mode approve

# Optional: Promote complete 3-prong knowledge_graph.trig & excel_catalog_rml.yaml to data/golden_reference/:
.\.venv\Scripts\python.exe scripts\run_dt01c_pdf_bites_gate2.py --mode approve --update-golden-ref
```

### Execute Step 5 (Layer 4 R2RML Pushdown Compiler & 6-Graph Federated Proof)
Requires Track B artifacts (`DT-01a..c`) with `0` persisted triples in `<urn:telco:graph:virtual:ib>` on disk:
```powershell
.\.venv\Scripts\python.exe scripts\run_step5_layer4_federation.py --circuit-id CIR-994821
```
Generates:
- Ephemeral in-memory `<urn:telco:graph:virtual:ib>` projection (`535` triples; `0` triples persisted to disk)
- `reports/layer4_federation_proof_report.html` & `.md` (compiled SQL pushdown queries, unified 6-graph context, and 5-Challenge Resolution Proof Table)

### Execute Scenario `RT-05` (Step 6 — Layer 3 `NL2Semantics` Dual Shadow Comparison & `semantic-read-mcp`)
Requires Track B + Layer 4 prerequisites (`DT-01a..c`) and compiled `data/semantic_store/stored_sparql_templates.yaml` (automatically compiled by `scripts/run_dt01c_pdf_bites_gate2.py --mode approve`, or via `--compile-templates` below):
```powershell
# Compile stored_sparql_templates.yaml standalone and run Dual Shadow Comparison for CIR-994821:
.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --compile-templates --mode dual_comparison --circuit-id CIR-994821

# Run Dual Shadow Comparison (Voicebox Hybrid vs. Zero-Shot LLM) using existing compiled templates:
.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --mode dual_comparison --circuit-id CIR-994821

# Run only Voicebox Hybrid or Zero-Shot LLM:
.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --mode voicebox_hybrid --circuit-id CIR-994821
.\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --mode zero_shot_llm --circuit-id CIR-994821
```
Generates:
- `reports/rt05_layer3_nl2semantics_comparison.html` & `.md` (side-by-side latency, AST Gatekeeper audit, row counts, missing fields, and compiled/generated SPARQL)
- Southbound MCP Server: `src/mcp_servers/semantic_read_mcp.py` (`MCPServer("semantic-read-mcp")` exposing `query_knowledge_fabric` with configurable `obo_jwt` scope verification via `layer3_nl2semantics.require_obo_jwt`)

### Run Unit Tests (Zero Deprecation / Future Warnings Enforced)
```powershell
.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning
```
