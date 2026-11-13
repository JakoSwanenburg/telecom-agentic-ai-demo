# SYS-01 Live System State Inspector Dashboard — `UC-001`

**Inspected At (UTC):** `2026-11-13T10:54:00Z`  
**Use Case:** `UC-001` — *Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration*  
**Target Circuit:** `CIR-994821` (`ETH-10G-GOLD`) on `OLT04-P12` / `NOK-7210-SAS-Mxp`

| # | Inspected Architectural Element | Underlying Artifact / Endpoint | Current State | Key Metrics & Details |
| :---: | :--- | :--- | :---: | :--- |
| 1 | **1. Conceptual TBox & Mappings** | `data/semantic_store/tbox_sid_etom.ttl & mappings/cmdb_r2rml.ttl` | **`LOCKED_APPROVED`** | Classes: 14 | Properties: 37 | skos:altLabel: 120 | HITL Gate 1: APPROVED |
| 2 | **2. Prong 1: SQL CMDB Virtual Graph** | `urn:telco:graph:virtual:ib` | **`BOUND_ZERO_COPY`** | Persisted triples on disk: 0 | Bound SQLite tables: 3 | Excluded noise tables: 1 |
| 3 | **3. Prong 2: Excel Reference Graph** | `urn:telco:graph:ref:catalog` | **`LOADED_WITH_QUARANTINE`** | Materialized triples: 198 | Valid B2B SKUs loaded: 18 | Excluded distractor tabs: 2 | pySHACL quarantined rows: 2 |
| 4 | **4. Prong 3: PDF BITES & ER Bridge** | `<urn:telco:graph:bites:*> & <urn:telco:graph:bridge:er>` | **`PROMOTED`** | GLOBAL_SCOPE triples: 16 | DOCUMENT_SCOPE triples: 8 | Active PDFs: 2 | ER links: 3 | HITL Gate 2: APPROVED |
| 5 | **5. Southbound MCP Primitive Catalog** | `config/mcp_primitives_catalog.json` | **`COMPLETE`** | Registered primitives: 4/4 | TMF640_SERVICE_ACTIVATION: BOUND | TMF621_TROUBLE_TICKET: BOUND |
| 6 | **6. Layer 2 Worker Agent & Skill** | `skills/skill_sop_402.yaml` | **`REMOVED`** | Compiled states: 0 | Active guardrails: 0 | Northbound MCP Tool: NOT_DEPLOYED |
| 7 | **7. Layer 3 & CQRS Runtime Settings** | `config.yaml & data/cqrs_state/cqrs_runtime_state.json` | **`ACTIVE_PRESET`** | Layer 3 Mode: dual_comparison | Telemetry Preset: branch_a_soft_degradation | Active Mutex Locks: 0 | Token Bucket: 3/3 |
