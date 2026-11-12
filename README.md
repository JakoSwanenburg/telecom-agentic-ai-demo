# Telecom Agentic AI Demo (`UC-001`)

Enterprise Reference Implementation demonstrating the **5-Layer Telecom Agentic AI & Semantic Knowledge Fabric Architecture** (`ARCH-TELCO-AGENT-EKG-2026-V2`) and the **4-Stage Pre-Implementation Foundation Plan** (`PLAN-TELCO-AGENT-UC1-2026-V1`) for **Use Case UC-001: Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration**.

---

## 1. Architecture & Use Case Overview (`UC-001`)

- **TM Forum Alignment**:
  - **eTOM Processes**: `1.3.7` Problem Handling & `1.4.5` Resource Trouble Management.
  - **SID Entity Spine**: `Customer (CUST-ENT-409)` $\rightarrow$ `CustomerFacingService (CIR-994821)` $\rightarrow$ `ServiceSpecification (ETH-10G-GOLD)` $\rightarrow$ `ResourceFacingService (RFS-OLT04-P12)` $\rightarrow$ `PhysicalResource (CPE-ASN-7741 / OLT04-P12)` $\rightarrow$ `PhysicalResourceSpec (NOK-7210-SAS-Mxp)`.
- **Three Functional Planes**:
  1. **Design-Time Build Plane**: Multi-procedure SOP-to-Skill compilation (`SOP-ASSUR-402` sliced from a 6-section Master NOC Runbook) and 3-pronged knowledge ingestion (SQL Virtual Graph, Excel Materialized Reference Graph, PDF BITES Extraction).
  2. **Runtime Operational Read Plane (Layers 1–5)**: Thin-Client MCP Orchestrator (Layer 1), Deterministic State-Machine Worker Agent (Layer 2), NL2Semantics Conceptual TBox Translator (Layer 3), Deterministic R2RML/SPARQL Federation Compiler (Layer 4), and Heterogeneous OSS/BSS Data Sources (Layer 5).
  3. **Runtime CQRS Action Plane**: Real-time non-cached hardware probing + Redis port mutex locking (`Singleton Check MCP Server`) and `pySHACL`-validated, circuit-breaker-governed mutations (`Transactional Write MCP Server`).

---

## 2. Repository Structure

```text
.
├── config.yaml                  # Centralized non-secret configuration (with env var overrides)
├── requirements.txt             # Python dependencies
├── README.md                    # Project documentation
├── documents/                   # Architecture Blueprint, Implementation Plan & UC-001 Charter
├── implementation_plan/         # Gated Implementation Plans (IMP-001, IMP-002, ...)
├── logs/                        # Local rotating log files (excluded from Git via .gitignore)
├── data/
│   └── raw_sources/             # Frozen Stage 0 (Activity 0.2) noisy enterprise raw sources
│       ├── sql/                 # Prong 1: cmdb_installed_base.db & cmdb_dump.sql
│       ├── excel/               # Prong 2: Telco_Master_Product_SLA_Catalog_2026.xlsx
│       ├── pdf/                 # Prong 3: Vendor_Optical_Hardware_Manual_v4.pdf & MSA PDF
│       ├── sop/                 # Multi-SOP Runbook (.docx & .md)
│       └── STAGE0_ARTIFACT_MANIFEST.md
├── src/
│   ├── __init__.py
│   ├── models.py                # Pydantic v2 schemas for config & shared generator results
│   ├── config.py                # YAML configuration loader with env var overrides
│   ├── logger.py                # Dual logger (local rotating file + stdout vs. cloud stdout)
│   └── stage0_generator.py      # Modular Stage 0 raw sources generator & verifier
├── scripts/
│   └── generate_stage0_raw_sources.py  # CLI entrypoint for Stage 0 raw sources generation
├── tests/
│   ├── test_config_and_logger.py       # Unit tests for config, env overrides & dual logging
│   └── test_stage0_generator.py        # Unit tests for Stage 0 generation & fail-fast checks
└── terraform/                   # 100% Terraform-managed GCP infrastructure (europe-west4)
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

All non-secret settings and relative paths are stored in [`config.yaml`](file:///d:/Telecom%20Agentic%20AI%20Demo/config.yaml) and validated via Pydantic v2 in [`src/config.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/config.py).

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

---

## 5. Execution & Unit Testing

### Generate & Verify Stage 0 Raw Data Sources (`Activity 0.2`)
```powershell
.\.venv\Scripts\python.exe scripts\generate_stage0_raw_sources.py
```

### Run Unit Tests (Zero Deprecation / Future Warnings Enforced)
```powershell
.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning
```

