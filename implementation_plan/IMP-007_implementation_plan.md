# Implementation Plan: `IMP-007` — Development Step 5 (Layer 4: Deterministic R2RML-to-SQLite Pushdown Compiler, Multi-Graph Federated Executor & 5-Challenge Resolution Proof)

## 1. Unique Reference ID
`IMP-007`

## 2. Objective & Scope
Implement **Development Step 5 (Stage 1/2 — Layer 4)** inside `d:/Telecom Agentic AI Demo/` strictly scoped to:
1. **Fail-Fast Track B Prerequisite Check:** Verify at initialization/query time that `data/semantic_store/tbox_sid_etom.ttl`, `data/semantic_store/knowledge_graph.trig`, `mappings/cmdb_r2rml.ttl`, and `data/raw_sources/sql/cmdb_installed_base.db` exist, and that `<urn:telco:graph:virtual:ib>` has `0` persisted triples on disk in `knowledge_graph.trig`. Fail fast with an explicit `RuntimeError` if missing or violated.
2. **100% Generic R2RML-to-SQLite Pushdown Compiler (`src/layer4/__init__.py` & `src/layer4/r2rml_sqlite_compiler.py`):**
   - Zero hardcoded SQL table names, column names, or SQL query strings in Python code.
   - Dynamically parse `mappings/cmdb_r2rml.ttl` via `rdflib` (`rr:TriplesMap`, `rr:logicalTable`, `rr:sqlQuery` / `rr:tableName`, `rr:subjectMap`, `rr:predicateObjectMap`, `rr:column`, `rr:template`, `rr:datatype`, `rr:termType`).
   - Execute each `rr:TriplesMap` SQL query against `cmdb_installed_base.db`, recording compiled SQL, latency (ms), and row count, and project triples **strictly in memory** into `<urn:telco:graph:virtual:ib>` on a runtime `rdflib.Dataset` clone (never writing virtual triples to disk).
   - Generically project any SQL `SELECT` column returned by an `rr:TriplesMap` query that is not yet bound by an explicit `rr:predicateObjectMap` (using `gate1_candidate_proposal.json` mapping if present, or a generic `telco:<camelCaseColumn>` datatype property) so `CPE_MODEL_SKU` is available in `<urn:telco:graph:virtual:ib>` without modifying `mappings/cmdb_r2rml.ttl`.
   - Run a generic SCD Type 2 & Noise Audit derived from SQLite `sqlite_master` + `mappings/cmdb_r2rml.ttl` comments/tables (recording unmapped excluded tables and suppressed historical rows vs. retained active rows).
3. **Federated Multi-Named-Graph Executor & 5-Challenge Resolution Proof (`src/layer4/federated_executor.py`):**
   - Enforce read-only SPARQL (`SELECT`, `ASK`, `CONSTRUCT`, `DESCRIBE`; deterministically reject `INSERT`, `DELETE`, `DROP`, `CLEAR`, `LOAD`, `CREATE`, `MOVE`, `COPY`, `ADD`).
   - Execute canonical federated SPARQL join across `<urn:telco:graph:virtual:ib>`, `<urn:telco:graph:ref:catalog>`, `<urn:telco:graph:bites:doc-hw-v4>`, `<urn:telco:graph:bites:doc-msa-v1>`, `<urn:telco:graph:meta:doc-lifecycle>`, and `<urn:telco:graph:bridge:er>` matching canonical SKU codes (`STRAFTER(STR(?specIri), "urn:telco:spec:service:") = ?catalogSku`) and CPE hardware model (`STRAFTER(STR(?hwSpecIri), "urn:telco:spec:resource:") = ?cpeModelSku`), with `OPTIONAL { ... }` blocks for supplementary fields (`nominalTxDbm`, `normalRxWindow`, `slaCreditPct`, `breachDurationMins`) and mandatory core thresholds (`maxPacketLossPct`, `autoRemediationAllowed`, `rxOpticalPowerMinDbm`, `rxLosCutThresholdDbm`).
   - Build the structured `FiveChallengeProofTable` and render `reports/layer4_federation_proof_report.html` and `.md`.
4. **CLI Verification Runner (`scripts/run_step5_layer4_federation.py`), `DT-00` Update & Unit Tests (`tests/test_step5_layer4_federation.py`).**

---

## 3. Key Design Decisions (Locked in Gate 1)
1. **Cross-Prong Join Key (`virtual:ib` <-> `ref:catalog`):** Resolved inside Layer 4's federated SPARQL query via `STRAFTER(STR(?specIri), "urn:telco:spec:service:") = ?catalogSku` (no edits to Prong 1 or Prong 2 IRIs).
2. **Unbound `SELECT` Column Projection (`CPE_MODEL_SKU`):** `mappings/cmdb_r2rml.ttl` remains untouched; `r2rml_sqlite_compiler.py` generically emits triples for any `SELECT` column not bound by an explicit `rr:predicateObjectMap`, enabling pure SPARQL join to `<urn:telco:graph:bites:doc-hw-v4>`.
3. **Zero Fabrication for Supplementary Optical/SLA Fields:** Core operational thresholds (`maxPacketLossPct`, `autoRemediationAllowed`, `rxOpticalPowerMinDbm`, `rxLosCutThresholdDbm`) are required in Pydantic; supplementary fields (`nominalTxDbm`, `normalRxWindow`, `slaCreditPct`, `breachDurationMins`) are `Optional` via SPARQL `OPTIONAL`.
4. **Configuration:** Add `layer4_federation_proof_report_path: "reports/layer4_federation_proof_report.html"` under `layer4_compiler_federation` in `config.yaml` and `Layer4CompilerFederationSettings`.

---

## 4. Step-by-Step Implementation Plan

### Step 1: Configuration & Pydantic v2 Models (`config.yaml`, `src/models.py`)
- Add `layer4_federation_proof_report_path: "reports/layer4_federation_proof_report.html"` to `config.yaml` and `Layer4CompilerFederationSettings` in `src/models.py`.
- Add Step 5 Pydantic v2 models in `src/models.py`: `CompiledR2rmlQueryRecord`, `Scd2AuditSummary`, `VirtualGraphCompileResult`, `ChallengeResolutionProofEntry`, `FiveChallengeProofTable`, `FederatedCircuitContext`, `Layer4FederationExecutionResult`.

### Step 2: Generic R2RML-to-SQLite Pushdown Compiler (`src/layer4/__init__.py`, `src/layer4/r2rml_sqlite_compiler.py`)
- Implement `validate_layer4_prerequisites(config, root_dir)` (fail-fast check + `virtual:ib == 0` on disk).
- Implement `compile_r2rml_to_virtual_graph(config, logger, root_dir)` with zero hardcoded table/column/SQL strings.

### Step 3: Federated Multi-Graph Executor & CLI (`src/layer4/federated_executor.py`, `scripts/run_step5_layer4_federation.py`, `src/state_manager.py`)
- Implement `execute_readonly_sparql(dataset, query_text)` (rejecting mutation keywords).
- Implement `query_federated_circuit_context(circuit_id, config, logger, root_dir)`, `build_five_challenge_proof_table(...)`, and HTML/MD report writer.
- Create `scripts/run_step5_layer4_federation.py` (`--circuit-id`, default `CIR-994821`).
- Update `src/state_manager.py` (`reset_to_clean_slate`) to clean `reports/layer4_federation_proof_report.*`.

### Step 4: Unit Tests, Docs & Live Verification (`tests/test_step5_layer4_federation.py`, `README.md`)
- Write unit tests covering zero hardcoded SQL/table/column names, read-only SPARQL enforcement, SCD2 filtering (`CFS_ROW_ID=2000` suppressed vs. `2001` retained), `'10' -> 'ACTIVE'`, `10.0 Gbps`, full 6-graph federated join for `CIR-994821`, and `0` persisted triples in `<urn:telco:graph:virtual:ib>` before and after execution.
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\run_step5_layer4_federation.py --circuit-id CIR-994821` and `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`.
- Update `README.md` and append Gate 5 Implementation Summary to `implementation_plan/IMP-007_implementation_plan.md`.

---

## Implementation Summary
- **Configuration & Models (`config.yaml`, `src/models.py`):** Added `layer4_federation_proof_report_path` to `config.yaml` and `Layer4CompilerFederationSettings`, plus Step 5 Pydantic v2 models (`CompiledR2rmlQueryRecord`, `Scd2AuditSummary`, `VirtualGraphCompileResult`, `FederatedCircuitContext`, `ChallengeResolutionProofEntry`, `FiveChallengeProofTable`, `Layer4FederationExecutionResult`).
- **100% Generic R2RML-to-SQLite Pushdown Compiler (`src/layer4/__init__.py`, `src/layer4/r2rml_sqlite_compiler.py`):**
  - Implemented `validate_layer4_prerequisites` (verifies Track B + SQLite artifacts and `0` persisted triples in `<urn:telco:graph:virtual:ib>` on disk).
  - Implemented `compile_r2rml_to_virtual_graph` with zero hardcoded SQL table names, column names, or domain SQL strings, projecting unbound `SELECT` columns (`CPE_MODEL_SKU` -> `telco:cpeModelSku`) and running a dynamic SCD2 + unmapped noise table audit.
- **Federated Multi-Graph Executor & CLI (`src/layer4/federated_executor.py`, `scripts/run_step5_layer4_federation.py`, `src/state_manager.py`):**
  - Implemented read-only SPARQL guard (`execute_readonly_sparql`), 6-graph federated join (`query_federated_circuit_context`), `FiveChallengeProofTable`, and HTML/MD proof reports.
  - Updated `src/state_manager.py` (`reset_to_clean_slate`) to clean `reports/layer4_federation_proof_report.*`.
- **Verification Results:**
  - `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`: **35 passed** (0 `DeprecationWarning`, 0 `FutureWarning`).
  - Live `.\.venv\Scripts\python.exe scripts\run_step5_layer4_federation.py --circuit-id CIR-994821`:
    - Projected **535** triples ephemerally in memory into `<urn:telco:graph:virtual:ib>` across 3 R2RML TriplesMaps (`CfsCircuitTriplesMap` 25 rows/175 triples, `CustomerTriplesMap` 15 rows/72 triples, `RfsResourceTriplesMap` 32 rows/288 triples), suppressing **7** historical SCD2 rows and excluding `T_BILLING_AUDIT_NOISE`.
    - Resolved unified context for `CIR-994821`: `CUST-ENT-409` (`'A Corporate Enterprise'`) <-> `'A Corporate Enterprise B.V.'` (`ER=0.9235`), `ETH-10G-GOLD` (`ACTIVE`, `10.0 Gbps`), `NOK-7210-SAS-Mxp`, `maxPacketLossPct=0.1%`, `autoRemediationAllowed=True`, `rxOpticalPowerMinDbm=-25.0 dBm`, `rxLosCutThresholdDbm=-27.5 dBm`, and all 5 Challenges marked `RESOLVED`.
    - Confirmed `<urn:telco:graph:virtual:ib>` on disk remained at **0** triples before and after execution (`inspect_demo_state.py`).


