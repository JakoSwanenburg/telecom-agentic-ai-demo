# Mandatory HITL Gate 1 Review — Prong 1 SQL CMDB Profiler, TMF SID/eTOM TBox & R2RML Mapping (`DT-01a`)

- **Gate 1 Sign-Off Status:** **`LOCKED_APPROVED`**
- **Executed At (UTC):** `2026-11-12T15:07:00Z`
- **Evaluator Critique Result:** `PASS: 0/40 physical SQL tokens leaked into TBox; 14 OWL classes, 37 properties, and 122 skos:altLabel synonyms verified; T_BILLING_AUDIT_NOISE excluded; SCD2 (WHERE VALID_TO_TS IS NULL), shadow enum translation, and QUDT Gbps math active; <urn:telco:graph:virtual:ib> has 0 persisted triples on disk.`

---

## 1. SQLite CMDB Table-Level Profiling & Noise Exclusion Summary

| Table Name | Total Rows | Active Rows | Disposition | Target TMF SID Classes | R2RML TriplesMap |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `T_OSS_CUST_PARTY` | 15 | 15 | **`BOUND_VIRTUAL_GRAPH`** | `tmf:Customer` | `<#CustomerTriplesMap>` |
| `T_CMDB_CFS_CIRCUIT` | 32 | 25 | **`BOUND_VIRTUAL_GRAPH`** | `tmf:CustomerFacingService` | `<#CfsCircuitTriplesMap>` |
| `T_CMDB_RFS_RESOURCE` | 32 | 32 | **`BOUND_VIRTUAL_GRAPH`** | `tmf:ResourceFacingService`, `tmf:PhysicalResource`, `telco:OltPortResource`, `telco:PeRouterResource`, `telco:CpeDeviceResource` | `<#RfsResourceTriplesMap>` |
| `T_BILLING_AUDIT_NOISE` | 25 | 0 | **`EXCLUDED_NOISE`** | *None (Excluded)* | `NONE (Excluded Noise Table)` |

---

## 2. Dynamic Column-Level Disposition Matrix (`PRAGMA table_info`)

| Table | Column | SQL Type | Disposition | Mapped TBox Target | Transformation / Audit Rationale |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `T_OSS_CUST_PARTY` | `PARTY_SURR_ID` | `INTEGER` | **`EXCLUDED_INTERNAL_OR_LEGACY`** | `NONE (Excluded)` | Internal relational surrogate sequence key; canonical IRI uses CUST_EXT_REF. |
| `T_OSS_CUST_PARTY` | `CUST_EXT_REF` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:Customer / tmf:customerId` | Canonical enterprise customer business identifier (e.g., CUST-ENT-409). |
| `T_OSS_CUST_PARTY` | `LEGAL_NAME` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:Customer / tmf:partyLegalName` | Official registered customer name used for entity resolution against MSA PDFs. |
| `T_OSS_CUST_PARTY` | `SEGMENT_CD` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:Customer / tmf:marketSegment` | Commercial customer tier used for assurance prioritization. |
| `T_OSS_CUST_PARTY` | `ACCT_MGR_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:Customer / telco:accountManagerCode` | Assigned enterprise account manager reference for VIP SLA escalations. |
| `T_OSS_CUST_PARTY` | `LEGACY_CRM_ID` | `TEXT` | **`EXCLUDED_INTERNAL_OR_LEGACY`** | `NONE (Excluded)` | Deprecated Siebel CRM foreign key; excluded to prevent legacy schema pollution. |
| `T_OSS_CUST_PARTY` | `CREATED_TS` | `TEXT` | **`EXCLUDED_INTERNAL_OR_LEGACY`** | `NONE (Excluded)` | Internal database row creation timestamp not required by assurance TBox. |
| `T_CMDB_CFS_CIRCUIT` | `CFS_ROW_ID` | `INTEGER` | **`PHYSICAL_SCD2_CONTROL_ONLY`** | `NONE (Layer 4 SCD2 Audit Control Only)` | Physical SCD Type 2 version surrogate key; zero exposure in Conceptual TBox. |
| `T_CMDB_CFS_CIRCUIT` | `CIRCUIT_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / tmf:serviceId` | Canonical L2 enterprise circuit identifier (e.g., CIR-994821). |
| `T_CMDB_CFS_CIRCUIT` | `CUST_REF_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / tmf:hasCustomer` | Links CustomerFacingService instance to owning tmf:Customer. |
| `T_CMDB_CFS_CIRCUIT` | `PROD_SPEC_CODE` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / tmf:isDescribedBy` | Links active circuit to its commercial ServiceSpecification SKU (e.g., ETH-10G-GOLD). |
| `T_CMDB_CFS_CIRCUIT` | `OPER_STATUS_CD` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / tmf:operationalStatus` | Translates undocumented numeric shadow enums ('10','20','99') into canonical SID status literals. |
| `T_CMDB_CFS_CIRCUIT` | `BW_VAL` | `NUMERIC` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / telco:bandwidthGbps` | Raw bandwidth magnitude; combined with BW_UNIT_CD via QUDT scaling. |
| `T_CMDB_CFS_CIRCUIT` | `BW_UNIT_CD` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / telco:bandwidthGbps (qudt:unit unit:GigaBIT-PER-SEC)` | Mixed unit code ('Kbps','Mbps','Gbps') normalized to canonical Gbps. |
| `T_CMDB_CFS_CIRCUIT` | `INSTALL_DT` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:CustomerFacingService / telco:installationDate` | Service commission date for operational lifecycle context. |
| `T_CMDB_CFS_CIRCUIT` | `VALID_FROM_TS` | `TEXT` | **`PHYSICAL_SCD2_CONTROL_ONLY`** | `NONE (Layer 4 SCD2 Window Start Control Only)` | Physical SCD Type 2 effective-from timestamp handled by Layer 4 virtual SQL pushdown. |
| `T_CMDB_CFS_CIRCUIT` | `VALID_TO_TS` | `TEXT` | **`PHYSICAL_SCD2_CONTROL_ONLY`** | `NONE (Layer 4 R2RML WHERE VALID_TO_TS IS NULL Filter)` | Physical SCD Type 2 expiration timestamp; governs active circuit filtering in R2RML. |
| `T_CMDB_CFS_CIRCUIT` | `LEGACY_BILL_TAG` | `TEXT` | **`EXCLUDED_LEGACY`** | `NONE (Excluded)` | Deprecated legacy billing tag; excluded from operational assurance ontology. |
| `T_CMDB_RFS_RESOURCE` | `RFS_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / tmf:rfsId` | Canonical ResourceFacingService bearer identifier (e.g., RFS-OLT04-P12). |
| `T_CMDB_RFS_RESOURCE` | `PARENT_CFS_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / tmf:supportsService` | Binds ResourceFacingService to the parent CustomerFacingService circuit. |
| `T_CMDB_RFS_RESOURCE` | `PE_ROUTER_HOSTNAME` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / telco:terminatesOnRouter (telco:PeRouterResource)` | Provider Edge aggregation router hostname (e.g., NLD-HAG-PE02). |
| `T_CMDB_RFS_RESOURCE` | `OLT_PORT_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / telco:usesOltPort (telco:OltPortResource)` | Physical OLT optical port identifier probed by CQRS gNMI telemetry (e.g., OLT04-P12). |
| `T_CMDB_RFS_RESOURCE` | `CPE_ASSET_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / telco:demarcatesAtCpe (telco:CpeDeviceResource)` | Customer Premises Equipment demarcation asset identifier (e.g., CPE-ASN-7741). |
| `T_CMDB_RFS_RESOURCE` | `CPE_MODEL_SKU` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:PhysicalResource / tmf:hasResourceSpecification (tmf:PhysicalResourceSpec)` | Hardware model SKU (e.g., NOK-7210-SAS-Mxp) linking CMDB inventory to optical manual specs. |
| `T_CMDB_RFS_RESOURCE` | `VLAN_TAG` | `INTEGER` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / telco:vlanTag` | IEEE 802.1Q encapsulation VLAN tag on the access bearer. |
| `T_CMDB_RFS_RESOURCE` | `FIBER_SPAN_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:ResourceFacingService / telco:fiberSpanId` | Physical metro fiber ring/span identifier for outside-plant fault localization. |
| `T_CMDB_RFS_RESOURCE` | `LAST_SYNC_UTC` | `TEXT` | **`EXCLUDED_SYNC_METADATA`** | `NONE (Excluded)` | Internal NMS polling sync watermark; excluded from Conceptual TBox. |
| `T_BILLING_AUDIT_NOISE` | `INV_ID` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `CUST_REF_ID` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `BILL_CYCLE_CD` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `GROSS_AMT_EUR` | `NUMERIC` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `TAX_CD` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `VAT_PCT` | `NUMERIC` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `GL_POST_DT` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `DUNNING_LVL` | `INTEGER` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. |
| `T_BILLING_AUDIT_NOISE` | `ERP_BATCH_REF` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. Represents internal batch/hash audit metadata (ERP_BATCH_REF / AUDIT_HASH). |
| `T_BILLING_AUDIT_NOISE` | `AUDIT_HASH` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial ERP/billing invoice audit column out of scope for UC-001 L2 assurance. Represents internal batch/hash audit metadata (ERP_BATCH_REF / AUDIT_HASH). |

---

## 3. Target Circuit `CIR-994821` SCD Type 2, Shadow Enum & QUDT Verification

- **Superseded Historical Row Filtered Out (`VALID_TO_TS IS NOT NULL`):** `CFS_ROW_ID=2000` (`ETH-1G-SILVER`, expired `2025-06-01T00:00:00Z`)
- **Active Current Row Retained (`WHERE VALID_TO_TS IS NULL`):** `CFS_ROW_ID=2001` (`ETH-10G-GOLD`)
- **Shadow Enum Translation (`OPER_STATUS_CD`):** `'10'` $\rightarrow$ **`'ACTIVE'`**
- **QUDT Bandwidth Normalization:** `10.0 Gbps` $\rightarrow$ **`10.0 Gbps`** (`unit:GigaBIT-PER-SEC`)
