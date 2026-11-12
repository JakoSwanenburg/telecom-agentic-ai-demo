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
│   │   └── STAGE0_ARTIFACT_MANIFEST.md
│   ├── semantic_store/                  # Active Named Graph store (knowledge_graph.trig & tbox_sid_etom.ttl)
│   ├── golden_reference/                # Pre-verified fallback reference artifacts
│   └── cqrs_state/                      # Inspectable CQRS runtime state (cqrs_runtime_state.json)
├── mappings/                            # R2RML virtual SQL mappings & Excel RML rules
├── shapes/                              # Active pySHACL shape files (*.ttl)
├── skills/                              # Compiled Layer 2 Worker Agent skills & guardrails
├── reports/                             # Generated HTML/Markdown dashboards & HITL review reports
├── src/
│   ├── __init__.py
│   ├── models.py                        # Pydantic v2 schemas for config, catalog, CQRS state, DT-00 & SYS-01
│   ├── config.py                        # YAML configuration loader with env var overrides
│   ├── config_loader.py                 # Step 1 configuration loader interface
│   ├── catalog_manager.py               # Southbound MCP Platform Primitive Catalog manager & gap toggle
│   ├── state_manager.py                 # Scenario DT-00 clean-slate wipe & CQRS runtime state reset
│   ├── state_inspector.py               # SYS-01 Live System State Inspector (7 architectural elements)
│   ├── logger.py                        # Dual logger (local rotating file + stdout vs. cloud stdout)
│   └── stage0_generator.py              # Modular Stage 0 raw sources generator & verifier
├── scripts/
│   ├── generate_stage0_raw_sources.py   # CLI entrypoint for Stage 0 raw sources generation
│   ├── reset_demo_state.py              # CLI entrypoint for Scenario DT-00 (Wipe & Reset to Clean Slate)
│   └── inspect_demo_state.py            # CLI entrypoint for SYS-01 (Live System State Inspector)
├── tests/
│   ├── test_config_and_logger.py        # Unit tests for config, env overrides & dual logging
│   ├── test_stage0_generator.py         # Unit tests for Stage 0 generation & fail-fast checks
│   └── test_step1_state_and_config.py   # Unit tests for Step 1 config lock, MCP catalog, DT-00 & SYS-01
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
| `AI_MODEL_NAME` | `ai.model_name` | `gemini-2.5-pro` | Configurable LLM model identifier |
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

### Run Unit Tests (Zero Deprecation / Future Warnings Enforced)
```powershell
.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning
```
