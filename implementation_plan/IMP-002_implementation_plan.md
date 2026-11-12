# Implementation Plan — `IMP-002`: Project Initiation Scaffolding & Stage 0 Generator Refactoring

## 1. Unique Reference ID
- **Reference ID:** `IMP-002`
- **Predecessor Plan:** `IMP-001` (to be renamed from `implementation_plan/implementation_plan.md` to `implementation_plan/IMP-001_implementation_plan.md`)

---

## 2. Objective & Scope

### Objective
Apply the `AGENTS.md` project initialization rules (**Part 1 – Part 7**) to the workspace by:
1. Renaming the existing Stage 0 implementation plan to `implementation_plan/IMP-001_implementation_plan.md`.
2. Scaffolding the standard enterprise project structure (`logs/`, `src/`, `tests/`, `terraform/`, `config.yaml`, `.gitignore`, `requirements.txt`, `README.md`) bound to GitHub repository `https://github.com/JakoSwanenburg/telecom-agentic-ai-demo.git` and GCP project `telecom-agentic-ai-demo` (`europe-west4`).
3. Refactoring the Stage 0 raw data generator (`scripts/generate_stage0_raw_sources.py`) into modular, PEP 8 typed Python components under `src/` with Pydantic v2 configuration and data validation, dual logging (console + rotating log files in `./logs/` locally; `stdout` in cloud), and comprehensive `pytest` unit tests executing with zero deprecation/future warnings (`pytest -W error::DeprecationWarning -W error::FutureWarning`).

### Scope
- **In Scope**:
  - Plan file migration (`IMP-001_implementation_plan.md`) and new plan (`IMP-002_implementation_plan.md`).
  - Centralized `config.yaml` + environment variable override loader (`src/config.py`).
  - Dual logging module (`src/logger.py`).
  - Shared Pydantic v2 data structures (`src/models.py`).
  - Modular Stage 0 raw sources generator (`src/stage0_generator.py`) and thin CLI entrypoint (`scripts/generate_stage0_raw_sources.py`).
  - Comprehensive unit test suite (`tests/test_config_and_logger.py`, `tests/test_stage0_generator.py`).
  - Standard multi-file Terraform foundation (`./terraform/providers.tf`, `variables.tf`, `apis.tf`, `main.tf`, `iam.tf`, `outputs.tf`, `terraform.tfvars`) configured for `telecom-agentic-ai-demo` (`europe-west4`) with clean destroy guarantees (`force_destroy = true`, `deletion_protection = false`, `disable_on_destroy = false`) and Google Cloud security best practices. *(Note: No `terraform apply` or cloud deployment will be executed unless explicitly requested).*
  - Project `.gitignore`, `requirements.txt`, and `README.md`.

---

## 3. Key Design Decisions (Including Agreed GCP Services & Resource Names)

1. **GitHub & GCP Project Isolation (`Part 4`, `Part 5`, `Part 6`)**:
   - **GitHub Remote**: `https://github.com/JakoSwanenburg/telecom-agentic-ai-demo.git` on branch `main` (verified via `git ls-remote origin`).
   - **GCP Project ID**: `telecom-agentic-ai-demo` (Project Number `726639202349`, verified `ACTIVE` via `gcloud projects describe`).
   - **Default GCP Region**: `europe-west4` (Netherlands).
   - **Terraform Resource Naming Convention (`<project-prefix>-<resource-type>-<purpose>`)**:
     - Project Prefix: `telco-agent`
     - Baseline APIs (`google_project_service` with `disable_on_destroy = false`): `run.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`, `logging.googleapis.com`, `cloudtrace.googleapis.com`, `aiplatform.googleapis.com`, `storage.googleapis.com`.
     - Dedicated Least-Privilege Workload Service Account (`google_service_account`): `telco-agent-sa-runtime` (assigned only scoped roles: `roles/logging.logWriter`, `roles/cloudtrace.agent`, `roles/secretmanager.secretAccessor`; zero primitive roles, zero exported keys).
     - Artifact Storage Bucket (`google_storage_bucket` in `europe-west4`): `telecom-agentic-ai-demo-bkt-artifacts` (`uniform_bucket_level_access = true`, `public_access_prevention = "enforced"`, `force_destroy = true`).
2. **Configuration & Portability (`Part 2.5`, `Part 3.1`)**:
   - All relative paths (`data/raw_sources`, `logs`), deterministic seed (`42`), target `UC-001` identifiers (`CUST-ENT-409`, `CIR-994821`, `ETH-10G-GOLD`, `NOK-7210-SAS-Mxp`, `OLT04-P12`, `SOP-ASSUR-402`), GCP settings, and LLM/agent configuration parameters are stored in `config.yaml` and validated via Pydantic v2 (`src/config.py`), with environment variable overrides (`GCP_PROJECT_ID`, `GCP_REGION`, `ENV`, `LOG_LEVEL`, `LOG_DIR`, `STAGE0_RAW_DIR`).
3. **Dual Logging (`Part 2.4`)**:
   - `src/logger.py` configures console output (`stdout`) plus rotating file logging (`./logs/telco_agent.log`) when running locally (`ENV=local` and `K_SERVICE` unset). When `ENV=cloud` or `K_SERVICE` is detected, file handlers are skipped and logs stream purely to `stdout`.
4. **Shared Data Validation (`Part 2.2`, `Part 3.1`)**:
   - All data structures passed between generator, manifest builder, and verifier functions (`SqlTableCounts`, `SqlArtifactResult`, `ExcelTabCounts`, `ExcelArtifactResult`, `PdfArtifactResult`, `SopArtifactResult`, `Stage0GenerationSummary`) are strict Pydantic v2 models (`ConfigDict(extra="forbid", frozen=True)`).

---

## 4. Step-by-Step Implementation Plan

### Step 1: Migrate `IMP-001` & Install Dependencies
1. Rename `implementation_plan/implementation_plan.md` to `implementation_plan/IMP-001_implementation_plan.md` and add `IMP-001` header metadata.
2. Create `requirements.txt` and install `pydantic`, `pyyaml`, and `pytest` into `.venv`.

### Step 2: Create Root Configuration & Governance Files
1. Create `.gitignore` per **Part 4.4** rules (excluding `logs/`, `*.log`, `.env*`, `*.pem`, `*.key`, `*credentials*.json`, `__pycache__/`, `*.py[cod]`, `.venv/`, `venv/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, `tmp/`, `.terraform/`, while tracking source code, tests, `data/raw_sources/`, `documents/`, `config.yaml`, `README.md`, `implementation_plan/`, and `./terraform/`).
2. Create `config.yaml` containing workspace paths, logging settings, GCP project/region, AI model settings, and Stage 0 `UC-001` configuration.

### Step 3: Scaffold `./terraform/` Directory (`Part 5`)
1. Create `./terraform/providers.tf`, `./terraform/variables.tf`, `./terraform/apis.tf`, `./terraform/main.tf`, `./terraform/iam.tf`, `./terraform/outputs.tf`, and `./terraform/terraform.tfvars`.

### Step 4: Implement Modular Source Code (`src/` & `scripts/`)
1. Create `src/__init__.py`.
2. Create `src/models.py` (Pydantic v2 models for configuration and Stage 0 generation results).
3. Create `src/config.py` (YAML loader with environment variable overrides and fail-fast validation).
4. Create `src/logger.py` (dual logging for local vs. cloud environments).
5. Create `src/stage0_generator.py` (modular, typed Stage 0 Prong 1/2/3/SOP/Manifest generator and verifier).
6. Refactor `scripts/generate_stage0_raw_sources.py` to load `config.yaml`, initialize dual logging, and execute `src/stage0_generator.py`.

### Step 5: Implement & Run Unit Tests (`tests/`)
1. Create `tests/__init__.py`, `tests/test_config_and_logger.py`, and `tests/test_stage0_generator.py` covering core logic, Pydantic validation rules, fail-fast errors, env overrides, dual logging (local vs. cloud), and end-to-end Stage 0 artifact verification.
2. Execute `.\.venv\Scripts\python.exe scripts\generate_stage0_raw_sources.py` to verify artifact generation and dual logging to `./logs/`.
3. Execute `.\.venv\Scripts\pytest.exe -W error::DeprecationWarning -W error::FutureWarning` and confirm 100% pass with zero warnings.

### Step 6: Update Documentation (`Gate 5`) & Prepare for Git Commit (`Gate 6`)
1. Create/update `README.md` documenting project architecture, setup, `config.yaml` parameters, execution commands, and testing instructions.
2. Append the **Implementation Summary** to `implementation_plan/IMP-002_implementation_plan.md` and present changes for acceptance before `git commit`.


---

## 5. Implementation Summary (Gate 5)

### What Was Built
1. **Plan Migration**:
   - Migrated Stage 0 implementation plan to [`implementation_plan/IMP-001_implementation_plan.md`](file:///d:/Telecom%20Agentic%20AI%20Demo/implementation_plan/IMP-001_implementation_plan.md) and removed the legacy un-prefixed `implementation_plan/implementation_plan.md`.
2. **Project Initialization & Governance Scaffolding (`Part 4`, `Part 5`, `Part 6`)**:
   - Initialized Git on branch `main`, bound remote `origin` to `https://github.com/JakoSwanenburg/telecom-agentic-ai-demo.git`, and verified remote access (`git ls-remote origin`).
   - Verified active GCP project `telecom-agentic-ai-demo` (`726639202349`) via `gcloud projects describe`.
   - Created [`.gitignore`](file:///d:/Telecom%20Agentic%20AI%20Demo/.gitignore), [`config.yaml`](file:///d:/Telecom%20Agentic%20AI%20Demo/config.yaml), [`requirements.txt`](file:///d:/Telecom%20Agentic%20AI%20Demo/requirements.txt), and [`README.md`](file:///d:/Telecom%20Agentic%20AI%20Demo/README.md).
   - Scaffolded `./terraform/` ([`providers.tf`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/providers.tf), [`variables.tf`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/variables.tf), [`apis.tf`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/apis.tf), [`main.tf`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/main.tf), [`iam.tf`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/iam.tf), [`outputs.tf`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/outputs.tf), [`terraform.tfvars`](file:///d:/Telecom%20Agentic%20AI%20Demo/terraform/terraform.tfvars)) for project `telecom-agentic-ai-demo` in `europe-west4` with clean `terraform destroy` settings and least-privilege IAM.
3. **Modular Source Code & Stage 0 Refactoring (`Part 2` & `Part 3`)**:
   - [`src/models.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/models.py): Strict Pydantic v2 models (`ConfigDict(extra="forbid", frozen=True)`) for `AppConfig` and all Stage 0 artifact results.
   - [`src/config.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/config.py): Centralized `config.yaml` loader with environment variable overrides and fail-fast validation.
   - [`src/logger.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/logger.py): Dual logging utility writing to `stdout` + `./logs/telco_agent.log` locally, or `stdout` only in cloud environments (`ENV=cloud` / `K_SERVICE`).
   - [`src/stage0_generator.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/src/stage0_generator.py) & [`scripts/generate_stage0_raw_sources.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/scripts/generate_stage0_raw_sources.py): Refactored Stage 0 generator and CLI entrypoint.
4. **Unit Testing Suite (`tests/`)**:
   - [`tests/test_config_and_logger.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/tests/test_config_and_logger.py) (8 tests)
   - [`tests/test_stage0_generator.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/tests/test_stage0_generator.py) (2 end-to-end + fail-fast tests)

### Deviations Taken During Gate 4
- **None.** All work followed the approved `IMP-002` implementation plan without deviation.

### Verification Results
- **CLI Execution (`scripts/generate_stage0_raw_sources.py`)**:
  - Regenerated and verified all Stage 0 artifacts under `data/raw_sources/` and confirmed rotating log output in `logs/telco_agent.log`.
- **Unit Test Suite (`pytest -v -W error::DeprecationWarning -W error::FutureWarning`)**:
  - **10 / 10 tests passed** in `0.77s` with zero deprecation or future warnings.
