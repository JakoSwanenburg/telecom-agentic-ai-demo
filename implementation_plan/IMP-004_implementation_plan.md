# Implementation Plan — `IMP-004`: Development Step 2 (Stage 2 Activities B1 & B2 — Scenario `DT-01a`: Prong 1 SQL CMDB Schema Profiler, Pruned TMF SID/eTOM TBox, R2RML Virtual Graph Mapping & Mandatory HITL Gate 1 Lock)

## 1. Unique Reference ID
- **Reference ID:** `IMP-004`
- **Incremental Build Step:** Step 2 of 11 (`ADR-TELCO-UC001-ACT03-V1` Section 10 & `PLAN-TELCO-AGENT-UC1-2026-V2` Section 5 / Section 9)
- **Scenario ID:** `DT-01a`

---

## 2. Objective & Scope

### Objective
Implement and verify **Scenario `DT-01a`** (Stage 2 Activities B1 & B2: *Prong 1 SQL CMDB Schema Profiler, Pruned TMF SID/eTOM TBox, R2RML Virtual Graph Mapping & Mandatory HITL Gate 1 Lock*):
1. Dynamically inspect the live SQLite CMDB (`data/raw_sources/sql/cmdb_installed_base.db`, 4 tables, 104 rows) via `PRAGMA table_info(...)` and row-level profiling queries, classifying every physical table and column against the TM Forum SID (`GB922`) & eTOM (`GB921`) vocabulary.
2. Author the Conceptual Ontology Slice (`data/semantic_store/tbox_sid_etom.ttl`, 14 pruned OWL classes, object/datatype properties, rich `skos:altLabel` synonyms, eTOM `1.3.7` / `1.4.5` concepts, QUDT unit annotations, and **zero** SQL table/column leakage) and materialize it into Named Graph `<urn:telco:graph:tbox:sid-etom>` in `data/semantic_store/knowledge_graph.trig` while keeping `<urn:telco:graph:virtual:ib>` at **`0` persisted triples on disk**.
3. Author the Base W3C SHACL Shapes (`shapes/service_spec_shape.ttl` and `shapes/trouble_ticket_shape.ttl`).
4. Author the Physical W3C R2RML Virtual Graph Mapping (`mappings/cmdb_r2rml.ttl`) with `<#CustomerTriplesMap>`, `<#CfsCircuitTriplesMap>` (enforcing `WHERE VALID_TO_TS IS NULL`, shadow enum `OPER_STATUS_CD` translation, and QUDT `Kbps`/`Mbps`/`Gbps` $\rightarrow$ `Gbps` normalization), and `<#RfsResourceTriplesMap>` targeting `<urn:telco:graph:virtual:ib>`.
5. Implement the Evaluator Ontology Critique and Mandatory HITL Gate 1 Sign-Off report generator (`reports/hitl_gate1_ontology_mapping_review.html` and `.md`) supporting `--mode candidate` (`CANDIDATE_PROPOSED`) and `--mode approve` (`LOCKED_APPROVED`), plus optional `--update-golden-ref`.
6. Update `SYS-01` (`src/state_inspector.py`) so Element 1 reports exact Class, Property, and `skos:altLabel` counts alongside `CANDIDATE_PROPOSED` / `LOCKED_APPROVED`, and Element 2 reports `BOUND_ZERO_COPY` (`0` persisted triples on disk, `3` bound SQLite tables, `1` excluded noise table).
7. Write and run comprehensive unit tests in `tests/test_step2_dt01a_cmdb_gate1.py`.

### Scope Boundaries
- **In Scope**: Step 2 (`DT-01a`) only — Prong 1 SQL CMDB Schema Profiler, TBox, Base SHACL Shapes, R2RML Mapping, HITL Gate 1 report, `SYS-01` Element 1/2 refinement, and Step 2 unit tests.
- **Out of Scope**: Step 3 (`DT-01b` Excel RML & `pySHACL` Quarantine), Step 4 (`DT-01c` PDF BITES & Entity Resolution), and Layers 1–4 runtime engines.

---

## 3. Key Design Decisions

1. **Dynamic Live SQLite Schema Profiling & Exact Column Disposition (`src/track_b/s1_cmdb_tbox_profiler.py`)**:
   - Inspects `data/raw_sources/sql/cmdb_installed_base.db` dynamically via `sqlite_master` and `PRAGMA table_info(...)`:
     - **`T_BILLING_AUDIT_NOISE` (25 rows, 10 columns incl. `ERP_BATCH_REF` & `AUDIT_HASH`)**: Table and all 10 columns flagged as `EXCLUDED_NOISE` (noting that `ERP_BATCH_REF` and `AUDIT_HASH` represent internal batch/hash audit metadata irrelevant to `UC-001` assurance).
     - **`T_OSS_CUST_PARTY` (15 rows, 7 columns)**:
       - `CUST_EXT_REF`, `LEGAL_NAME`, `SEGMENT_CD`, `ACCT_MGR_ID` $\rightarrow$ `MAPPED_TO_TBOX` (`tmf:Customer`, canonical IRI template `urn:telco:party:customer:{CUST_EXT_REF}`).
       - `PARTY_SURR_ID`, `LEGACY_CRM_ID`, `CREATED_TS` $\rightarrow$ `EXCLUDED_INTERNAL_OR_LEGACY` (never exposed in `tbox_sid_etom.ttl`).
     - **`T_CMDB_CFS_CIRCUIT` (32 rows, 11 columns)**:
       - `CIRCUIT_ID`, `CUST_REF_ID`, `PROD_SPEC_CODE`, `OPER_STATUS_CD`, `BW_VAL`, `BW_UNIT_CD`, `INSTALL_DT` $\rightarrow$ `MAPPED_TO_TBOX` (`tmf:CustomerFacingService`, canonical IRI template `urn:telco:service:cfs:{CIRCUIT_ID}`).
       - `CFS_ROW_ID`, `VALID_FROM_TS`, `VALID_TO_TS` $\rightarrow$ `PHYSICAL_SCD2_CONTROL_ONLY` (used strictly inside the Layer 4 R2RML `rr:sqlQuery` filter `WHERE VALID_TO_TS IS NULL` and the SCD2 verification log proving `CFS_ROW_ID=2001` [`ETH-10G-GOLD`] is active and `CFS_ROW_ID=2000` [`ETH-1G-SILVER`] is superseded for `CIR-994821`, with zero exposure in the Conceptual TBox).
       - `LEGACY_BILL_TAG` $\rightarrow$ `EXCLUDED_LEGACY`.
     - **`T_CMDB_RFS_RESOURCE` (32 rows, 9 columns)**:
       - `RFS_ID`, `PARENT_CFS_ID`, `PE_ROUTER_HOSTNAME`, `OLT_PORT_ID`, `CPE_ASSET_ID`, `CPE_MODEL_SKU`, `VLAN_TAG`, `FIBER_SPAN_ID` $\rightarrow$ `MAPPED_TO_TBOX` (`tmf:ResourceFacingService`, `tmf:PhysicalResource`, `telco:OltPortResource`, `telco:PeRouterResource`, `telco:CpeDeviceResource`, `tmf:PhysicalResourceSpec`).
       - `LAST_SYNC_UTC` $\rightarrow$ `EXCLUDED_SYNC_METADATA`.

2. **Pruned TMF SID/eTOM Conceptual Ontology (`data/semantic_store/tbox_sid_etom.ttl`) & TriG Dataset (`data/semantic_store/knowledge_graph.trig`)**:
   - Defines 14 OWL classes (`tmf:Customer`, `tmf:Product`, `tmf:CustomerFacingService`, `tmf:ServiceSpecification`, `tmf:ResourceFacingService`, `tmf:PhysicalResource`, `telco:OltPortResource`, `telco:CpeDeviceResource`, `telco:PeRouterResource`, `tmf:PhysicalResourceSpec`, `tmf:TroubleTicket`, `telco:SlaClause`, `telco:OpticalCalibrationProfile`, `etom:BusinessProcess`), object properties, datatype properties, QUDT unit annotations (`unit:GigaBIT-PER-SEC`, `unit:MilliWATT-DeciBEL`, `unit:DEG_C`, `unit:PERCENT`, `unit:HR`), eTOM process individuals (`1.3.7 Problem Handling`, `1.4.5 Resource Trouble Management`), and $\ge 2$ `skos:altLabel` business synonyms per class/property.
   - Enforces **strictly zero** SQL table or column names in `tbox_sid_etom.ttl`.
   - Loads `tbox_sid_etom.ttl` into Named Graph `<urn:telco:graph:tbox:sid-etom>` in `data/semantic_store/knowledge_graph.trig` while ensuring `<urn:telco:graph:virtual:ib>` has **`0` persisted triples on disk**.

3. **Base W3C SHACL Shapes (`shapes/service_spec_shape.ttl` & `shapes/trouble_ticket_shape.ttl`)**:
   - `shapes/service_spec_shape.ttl`: Validates `tmf:ServiceSpecification` instances (`telco:maxPacketLossPct >= 0.0`, `telco:lifecycleStatus` in `("ACTIVE" "DEPRECATED")`, `telco:availabilityTargetPct` between `0.0` and `100.0`).
   - `shapes/trouble_ticket_shape.ttl`: Validates `tmf:TroubleTicket` instances (`tmf:ticketId`, `tmf:severity` in `("CRITICAL" "MAJOR" "MINOR" "WARNING")`, `tmf:status`, `telco:affectedCircuit`, `telco:affectedResource`).

4. **W3C R2RML Virtual Graph Mapping (`mappings/cmdb_r2rml.ttl`)**:
   - Defines `<#CustomerTriplesMap>`, `<#CfsCircuitTriplesMap>`, and `<#RfsResourceTriplesMap>` targeting `<urn:telco:graph:virtual:ib>`, embedding SQLite pushdown queries with `WHERE VALID_TO_TS IS NULL`, shadow enum `CASE WHEN OPER_STATUS_CD ...` translation (`'10'->'ACTIVE'`, `'20'->'MAINTENANCE'`, `'99'->'DECOMMISSIONED'`), and QUDT bandwidth normalization (`Kbps`/`Mbps`/`Gbps` $\rightarrow$ `Gbps`).

5. **HITL Gate 1 Mode & Golden Reference Separation (`scripts/run_dt01a_cmdb_gate1.py`)**:
   - `--mode candidate`: Sets Gate 1 status to `CANDIDATE_PROPOSED` (`SYS-01` Element 1 = `CANDIDATE_PROPOSED`).
   - `--mode approve` (default): Sets Gate 1 status to `LOCKED_APPROVED` with architect sign-off metadata (`SYS-01` Element 1 = `LOCKED_APPROVED`), writing strictly to the active working directories (`data/semantic_store/`, `mappings/`, `shapes/`, and `reports/`).
   - `--update-golden-ref` (optional flag, default `false`): Explicitly copies approved Step 2 artifacts (`tbox_sid_etom.ttl`, `cmdb_r2rml.ttl`, `shapes/*.ttl`) into `data/golden_reference/` only when requested, preserving `data/golden_reference/` as an immutable baseline during routine demo runs.

---

## 4. Step-by-Step Implementation Plan

### Step 1: Add Step 2 Pydantic v2 Models (`src/models.py`)
- Add strict Pydantic v2 models (`ConfigDict(extra="forbid", frozen=True)`) for:
  - `ColumnProfileEntry` (column name, SQL type, nullable, primary key, disposition enum, mapped TBox property/IRI template, rationale)
  - `TableProfileEntry` (table name, total row count, active row count, table disposition, target TMF class, canonical IRI template, column profiles)
  - `Scd2CircuitVerification` (circuit ID, expired row ID & SKU, active row ID & SKU, raw status code vs. canonical status, raw bandwidth vs. normalized Gbps)
  - `EvaluatorOntologyCritique` (zero SQL leakage passed, noise table excluded, SCD2 filter verified, all classes have `skos:altLabel` synonyms, critique summary)
  - `Dt01aExecutionResult` (complete validated summary returned by `run_dt01a_cmdb_profiler`)

### Step 2: Implement Prong 1 Profiler, TBox, SHACL & R2RML Generator (`src/track_b/s1_cmdb_tbox_profiler.py`)
- Create `src/track_b/__init__.py` and `src/track_b/s1_cmdb_tbox_profiler.py`:
  - Dynamically profile `data/raw_sources/sql/cmdb_installed_base.db` via `PRAGMA table_info(...)` and SQL queries.
  - Generate `data/semantic_store/tbox_sid_etom.ttl` and materialize `<urn:telco:graph:tbox:sid-etom>` in `data/semantic_store/knowledge_graph.trig` (with `0` triples in `<urn:telco:graph:virtual:ib>`).
  - Generate `shapes/service_spec_shape.ttl` and `shapes/trouble_ticket_shape.ttl`.
  - Generate `mappings/cmdb_r2rml.ttl`.
  - Execute the automated Evaluator Ontology Critique.
  - Render `reports/hitl_gate1_ontology_mapping_review.html` and `reports/hitl_gate1_ontology_mapping_review.md`.
  - Support optional `update_golden_ref: bool = False`.

### Step 3: Update `SYS-01` State Inspector (`src/state_inspector.py`) & `DT-00` Reset (`src/state_manager.py`)
- Update `_inspect_element_1_tbox` in `src/state_inspector.py` to count `owl:Class`, `owl:ObjectProperty` + `owl:DatatypeProperty`, and `skos:altLabel` triples, and distinguish `CANDIDATE_PROPOSED` vs. `LOCKED_APPROVED`.
- Ensure `reset_to_clean_slate` in `src/state_manager.py` also removes `reports/hitl_gate1_ontology_mapping_review.md`.

### Step 4: Create CLI Runner (`scripts/run_dt01a_cmdb_gate1.py`)
- Implement `scripts/run_dt01a_cmdb_gate1.py` with `--mode {candidate,approve}` (default `approve`) and `--update-golden-ref` flag, outputting a rich summary panel to the console.

### Step 5: Write Unit Tests & Execute Verification (`tests/test_step2_dt01a_cmdb_gate1.py`)
- Write unit tests in `tests/test_step2_dt01a_cmdb_gate1.py` verifying:
  - Dynamic SQLite profiling and column dispositions (`T_BILLING_AUDIT_NOISE` excluded, `PHYSICAL_SCD2_CONTROL_ONLY`, etc.).
  - `tbox_sid_etom.ttl`, `cmdb_r2rml.ttl`, `shapes/service_spec_shape.ttl`, and `shapes/trouble_ticket_shape.ttl` parse cleanly in `rdflib` with zero SQL leakage in `tbox_sid_etom.ttl`.
  - `<urn:telco:graph:virtual:ib>` has `0` persisted triples in `knowledge_graph.trig` while `<urn:telco:graph:tbox:sid-etom>` contains the TBox triples.
  - `SYS-01` transitions Element 1 to `CANDIDATE_PROPOSED` (`--mode candidate`) and `LOCKED_APPROVED` (`--mode approve`), Element 2 to `BOUND_ZERO_COPY`, and resets to `EMPTY` / `UNBOUND` after `DT-00`.
- Run `.\.venv\Scripts\pytest.exe -v -W error::DeprecationWarning -W error::FutureWarning`.
- Run `.\.venv\Scripts\python.exe scripts\run_dt01a_cmdb_gate1.py --mode approve` followed by `.\.venv\Scripts\python.exe scripts\inspect_demo_state.py`.

---

## 5. Implementation Summary (Gate 5)

### What Was Built
1. **Step 2 (`DT-01a`) Pydantic v2 Models (`src/models.py`)**:
   - Added `ColumnDisposition`, `ColumnProfileEntry`, `TableProfileEntry`, `Scd2CircuitVerification`, `EvaluatorOntologyCritique`, and `Dt01aExecutionResult` with `ConfigDict(extra="forbid", frozen=True)`.
2. **Prong 1 SQL CMDB Dynamic Profiler, TBox, SHACL & R2RML Generator (`src/track_b/s1_cmdb_tbox_profiler.py`)**:
   - Implemented `profile_cmdb_sqlite_database()` to dynamically inspect `data/raw_sources/sql/cmdb_installed_base.db` via `sqlite_master` and `PRAGMA table_info(...)` across all 4 tables (104 rows: `T_OSS_CUST_PARTY` [15], `T_CMDB_CFS_CIRCUIT` [32 total / 25 active], `T_CMDB_RFS_RESOURCE` [32], `T_BILLING_AUDIT_NOISE` [25]), applying the exact column dispositions (`MAPPED_TO_TBOX`, `PHYSICAL_SCD2_CONTROL_ONLY`, `EXCLUDED_INTERNAL_OR_LEGACY`, `EXCLUDED_LEGACY`, `EXCLUDED_SYNC_METADATA`, `EXCLUDED_NOISE`).
   - Generated `data/semantic_store/tbox_sid_etom.ttl` (14 OWL classes, 37 properties, 122 `skos:altLabel` synonyms, eTOM `1.3.7` / `1.4.5` individuals, QUDT unit annotations, and **0** physical SQL tokens leaked) and materialized `<urn:telco:graph:tbox:sid-etom>` in `data/semantic_store/knowledge_graph.trig` with `0` persisted triples in `<urn:telco:graph:virtual:ib>`.
   - Generated `shapes/service_spec_shape.ttl` and `shapes/trouble_ticket_shape.ttl`.
   - Generated `mappings/cmdb_r2rml.ttl` (`<#CustomerTriplesMap>`, `<#CfsCircuitTriplesMap>`, `<#RfsResourceTriplesMap>` targeting `<urn:telco:graph:virtual:ib>`).
   - Implemented `evaluate_ontology_and_r2rml()` and rendered `reports/hitl_gate1_ontology_mapping_review.html` and `.md`.
3. **`SYS-01` Inspector & `DT-00` Reset Refinements (`src/state_inspector.py` & `src/state_manager.py`)**:
   - Updated `_inspect_element_1_tbox()` to report exact `Classes`, `Properties`, `skos:altLabel`, and `HITL Gate 1` status (`CANDIDATE_PROPOSED` vs. `LOCKED_APPROVED`).
   - Updated `reset_to_clean_slate()` to also clean `.md` counterparts of HITL/quarantine reports.
4. **CLI Runner (`scripts/run_dt01a_cmdb_gate1.py`)**:
   - Implemented CLI supporting `--mode {candidate,approve}` (default `approve`) and optional `--update-golden-ref` (default `False`).

### Files Created or Modified
- **Modified**:
  - `src/models.py`
  - `src/state_inspector.py`
  - `src/state_manager.py`
  - `README.md`
  - `implementation_plan/IMP-004_implementation_plan.md`
  - `reports/system_state_dashboard.html`
  - `reports/system_state_dashboard.md`
- **Created**:
  - `src/track_b/__init__.py`
  - `src/track_b/s1_cmdb_tbox_profiler.py`
  - `scripts/run_dt01a_cmdb_gate1.py`
  - `tests/test_step2_dt01a_cmdb_gate1.py`
  - `data/semantic_store/tbox_sid_etom.ttl`
  - `data/semantic_store/knowledge_graph.trig`
  - `mappings/cmdb_r2rml.ttl`
  - `shapes/service_spec_shape.ttl`
  - `shapes/trouble_ticket_shape.ttl`
  - `reports/hitl_gate1_ontology_mapping_review.html`
  - `reports/hitl_gate1_ontology_mapping_review.md`

### Deviations Taken During Gate 4
- None.

### Verification Results
- **Unit Test Suite (`pytest -v -W error::DeprecationWarning -W error::FutureWarning`)**: **18 / 18 passed** in `0.98s` with zero warnings or deprecations.
- **Scenario `DT-01a` Execution (`scripts/run_dt01a_cmdb_gate1.py --mode approve`)**: Executed cleanly (exit code `0`), profiling 4 SQLite tables (104 rows), verifying `CIR-994821` SCD2 row `2000` (`ETH-1G-SILVER`, filtered) vs. row `2001` (`ETH-10G-GOLD`, retained active, `ACTIVE`, `10.0 Gbps`), verifying `0/40` SQL tokens leaked into `tbox_sid_etom.ttl` (14 OWL classes, 37 properties, 122 `skos:altLabel` synonyms), and locking HITL Gate 1 as `LOCKED_APPROVED`.
- **`SYS-01` Execution (`scripts/inspect_demo_state.py`)**: Verified Element 1 (`LOCKED_APPROVED`: `Classes: 14 | Properties: 37 | skos:altLabel: 122 | HITL Gate 1: APPROVED`) and Element 2 (`BOUND_ZERO_COPY`: `Persisted triples on disk: 0 | Bound SQLite tables: 3 | Excluded noise tables: 1 (T_BILLING_AUDIT_NOISE)`).


