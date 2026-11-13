# Mandatory HITL Gate 1 Review — Prong 1 SQL CMDB AI Schema Profiler, TMF SID/eTOM TBox & R2RML Mapping (`DT-01a`)

- **Gate 1 Sign-Off Status:** **`LOCKED_APPROVED`**
- **Proposal ID:** `PROP-UC-001-GATE1` (`gemini-3.8-flash`)
- **Executed At (UTC):** `2026-11-13T06:40:18Z`
- **Evaluator Critique Result:** `PASS: 0/40 physical SQL tokens leaked into TBox; 14 OWL classes, 37 properties, and 120 skos:altLabel synonyms verified; 1 noise table(s) (T_BILLING_AUDIT_NOISE) excluded; SCD2 active-window filter, shadow enum translation, and QUDT Gbps normalization verified; <urn:telco:graph:virtual:ib> has 0 persisted triples on disk.`

---

## 1. HITL Gate 1 Lead Architect Verification Questions

1. [x] Does the Lead Ontologist approve the retention of exactly 14 TM Forum SID and telecom domain classes, confirming that financial billing and marketing classes are strictly pruned from the operational assurance TBox?
2. [x] Does the Lead Architect approve excluding T_BILLING_AUDIT_NOISE and stripping internal surrogate keys, legacy CRM identifiers, and NMS synchronization watermarks to prevent physical database plumbing leakage into the Knowledge Graph?
3. [x] Is the R2RML SQL pushdown filter WHERE VALID_TO_TS IS NULL confirmed as the authoritative mechanism to resolve active SCD Type 2 circuit state (such as retaining row 2001 and suppressing expired row 2000 for circuit CIR-994821)?
4. [x] Does the Lead Architect validate the status mapping rules (10 to ACTIVE, 20 to MAINTENANCE, 99 to DECOMMISSIONED) and the QUDT conversion arithmetic transforming mixed Kbps, Mbps, and Gbps values into canonical Gigabits per second?

---

## 2. SQLite CMDB Table-Level Profiling & Noise Exclusion Summary

| Table Name | Total Rows | Active Rows | Disposition | Target TMF SID Classes | R2RML TriplesMap |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `T_BILLING_AUDIT_NOISE` | 25 | 0 | **`EXCLUDED_NOISE`** | *None (Excluded)* | `NONE (Excluded Noise Table)` |
| `T_OSS_CUST_PARTY` | 15 | 15 | **`BOUND_VIRTUAL_GRAPH`** | `tmf:Customer` | `<#CustomerTriplesMap>` |
| `T_CMDB_CFS_CIRCUIT` | 32 | 25 | **`BOUND_VIRTUAL_GRAPH`** | `tmf:CustomerFacingService` | `<#CfsCircuitTriplesMap>` |
| `T_CMDB_RFS_RESOURCE` | 32 | 32 | **`BOUND_VIRTUAL_GRAPH`** | `tmf:ResourceFacingService` | `<#RfsResourceTriplesMap>` |

---

## 3. Target Circuit `CIR-994821` SCD Type 2, Shadow Enum & QUDT Verification

- **Superseded Historical Row Filtered Out:** `ROW_ID=2000` (`ETH-1G-SILVER`, expired `2025-06-01T00:00:00Z`)
- **Active Current Row Retained:** `ROW_ID=2001` (`ETH-10G-GOLD`)
- **Shadow Enum Translation:** `'10'` $\rightarrow$ **`'ACTIVE'`**
- **QUDT Bandwidth Normalization:** `10.0 Gbps` $\rightarrow$ **`10.0 Gbps`** (`unit:GigaBIT-PER-SEC`)

---

## 4. Dynamic Column-Level Disposition Matrix (`PRAGMA table_info`)

| Table | Column | SQL Type | Disposition | Mapped TBox Target | Audit Rationale |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `T_BILLING_AUDIT_NOISE` | `INV_ID` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Billing invoice identifier INV_ID is out of scope for L2 fiber service assurance and network topology. |
| `T_BILLING_AUDIT_NOISE` | `CUST_REF_ID` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Customer reference on billing invoice record is out of scope for network assurance. |
| `T_BILLING_AUDIT_NOISE` | `BILL_CYCLE_CD` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Billing cycle code is out of scope for network fault triage. |
| `T_BILLING_AUDIT_NOISE` | `GROSS_AMT_EUR` | `NUMERIC` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Financial billing gross monetary amount is out of scope for network assurance. |
| `T_BILLING_AUDIT_NOISE` | `TAX_CD` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Tax regime identifier is out of scope for network assurance. |
| `T_BILLING_AUDIT_NOISE` | `VAT_PCT` | `NUMERIC` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Value added tax percentage is out of scope for network assurance. |
| `T_BILLING_AUDIT_NOISE` | `GL_POST_DT` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | General ledger posting timestamp is out of scope for network assurance. |
| `T_BILLING_AUDIT_NOISE` | `DUNNING_LVL` | `INTEGER` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | Customer dunning credit risk level is out of scope for network assurance. |
| `T_BILLING_AUDIT_NOISE` | `ERP_BATCH_REF` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | The column ERP_BATCH_REF represents batch audit metadata and is excluded from the virtual graph. |
| `T_BILLING_AUDIT_NOISE` | `AUDIT_HASH` | `TEXT` | **`EXCLUDED_NOISE`** | `NONE (Excluded Billing Noise Table)` | The column AUDIT_HASH represents cryptographic hash audit metadata and is excluded from the virtual graph. |
| `T_OSS_CUST_PARTY` | `PARTY_SURR_ID` | `INTEGER` | **`EXCLUDED_INTERNAL_OR_LEGACY`** | `NONE (Internal Surrogate Key)` | Internal database surrogate key has no business meaning in the TMF SID conceptual model. |
| `T_OSS_CUST_PARTY` | `CUST_EXT_REF` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:customerId` | Canonical customer account reference mapped to tmf:customerId and used as URI template key. |
| `T_OSS_CUST_PARTY` | `LEGAL_NAME` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:partyLegalName` | Corporate legal entity name mapped to tmf:partyLegalName. |
| `T_OSS_CUST_PARTY` | `SEGMENT_CD` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:marketSegment` | Market segment classification mapped to tmf:marketSegment. |
| `T_OSS_CUST_PARTY` | `ACCT_MGR_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:accountManagerCode` | Assigned enterprise account manager code mapped to telco:accountManagerCode. |
| `T_OSS_CUST_PARTY` | `LEGACY_CRM_ID` | `TEXT` | **`EXCLUDED_INTERNAL_OR_LEGACY`** | `NONE (Legacy CRM Identifier)` | Legacy CRM foreign key is deprecated and excluded from the enterprise semantic model. |
| `T_OSS_CUST_PARTY` | `CREATED_TS` | `TEXT` | **`EXCLUDED_INTERNAL_OR_LEGACY`** | `NONE (Database Audit Timestamp)` | Physical database record creation timestamp is excluded to prevent internal plumbing leakage. |
| `T_CMDB_CFS_CIRCUIT` | `CFS_ROW_ID` | `INTEGER` | **`PHYSICAL_SCD2_CONTROL_ONLY`** | `NONE (SCD2 Surrogate Primary Key)` | Physical SCD Type 2 surrogate primary key used for temporal versioning control only. |
| `T_CMDB_CFS_CIRCUIT` | `CIRCUIT_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:serviceId` | Business key for the connectivity circuit mapped to tmf:serviceId and used as subject template. |
| `T_CMDB_CFS_CIRCUIT` | `CUST_REF_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:hasCustomer` | Foreign key linking the circuit to the enterprise customer URI via tmf:hasCustomer. |
| `T_CMDB_CFS_CIRCUIT` | `PROD_SPEC_CODE` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:isDescribedBy` | Commercial product catalog code linking the circuit to its service specification via tmf:isDescribedBy. |
| `T_CMDB_CFS_CIRCUIT` | `OPER_STATUS_CD` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:operationalStatus` | Legacy numeric status code translated into canonical operational status literals in SQL. |
| `T_CMDB_CFS_CIRCUIT` | `BW_VAL` | `NUMERIC` | **`MAPPED_TO_TBOX`** | `telco:bandwidthGbps` | Raw numerical bandwidth value normalized to Gbps using BW_UNIT_CD in SQL pushdown. |
| `T_CMDB_CFS_CIRCUIT` | `BW_UNIT_CD` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:bandwidthGbps` | Bandwidth unit code used for normalization calculation to unit:GigaBIT-PER-SEC. |
| `T_CMDB_CFS_CIRCUIT` | `INSTALL_DT` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:installationDate` | Handover installation date mapped to telco:installationDate with xsd:date datatype. |
| `T_CMDB_CFS_CIRCUIT` | `VALID_FROM_TS` | `TEXT` | **`PHYSICAL_SCD2_CONTROL_ONLY`** | `NONE (SCD2 Valid From Timestamp)` | SCD Type 2 record effective start timestamp used strictly for physical temporal control. |
| `T_CMDB_CFS_CIRCUIT` | `VALID_TO_TS` | `TEXT` | **`PHYSICAL_SCD2_CONTROL_ONLY`** | `NONE (SCD2 Valid To Filter)` | SCD Type 2 expiration timestamp used in R2RML WHERE VALID_TO_TS IS NULL to select active inventory. |
| `T_CMDB_CFS_CIRCUIT` | `LEGACY_BILL_TAG` | `TEXT` | **`EXCLUDED_LEGACY`** | `NONE (Legacy Billing Tag)` | Obsolete billing system routing tag excluded from the enterprise assurance ontology. |
| `T_CMDB_RFS_RESOURCE` | `RFS_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:rfsId` | Primary identifier for the Resource Facing Service mapped to tmf:rfsId. |
| `T_CMDB_RFS_RESOURCE` | `PARENT_CFS_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:supportsService` | Reference to realizing Customer Facing Service mapped via tmf:supportsService. |
| `T_CMDB_RFS_RESOURCE` | `PE_ROUTER_HOSTNAME` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:terminatesOnRouter` | Provider Edge router hostname mapped to telco:terminatesOnRouter. |
| `T_CMDB_RFS_RESOURCE` | `OLT_PORT_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:usesOltPort` | Optical Line Terminal port mapped to telco:usesOltPort. |
| `T_CMDB_RFS_RESOURCE` | `CPE_ASSET_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:demarcatesAtCpe` | Customer Premises Equipment asset identifier mapped to telco:demarcatesAtCpe. |
| `T_CMDB_RFS_RESOURCE` | `CPE_MODEL_SKU` | `TEXT` | **`MAPPED_TO_TBOX`** | `tmf:hasResourceSpecification` | Vendor hardware model SKU linking the CPE device to its resource specification. |
| `T_CMDB_RFS_RESOURCE` | `VLAN_TAG` | `INTEGER` | **`MAPPED_TO_TBOX`** | `telco:vlanTag` | L2 transport encapsulation VLAN tag mapped to telco:vlanTag. |
| `T_CMDB_RFS_RESOURCE` | `FIBER_SPAN_ID` | `TEXT` | **`MAPPED_TO_TBOX`** | `telco:fiberSpanId` | Physical outside plant fiber span identifier mapped to telco:fiberSpanId. |
| `T_CMDB_RFS_RESOURCE` | `LAST_SYNC_UTC` | `TEXT` | **`EXCLUDED_SYNC_METADATA`** | `NONE (Sync Watermark)` | Network management system polling synchronization timestamp excluded from conceptual ontology. |
