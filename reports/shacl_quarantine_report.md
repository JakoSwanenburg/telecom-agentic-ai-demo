# Scenario DT-01b: Prong 2 Excel Catalog & Row-Level `pySHACL` Quarantine Report

- **Executed At (UTC):** `2026-11-13T07:20:02Z`
- **Workbook:** `data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx`
- **Target Worksheet:** `B2B_Enterprise_SLA_Matrix` (Header Row: `5`, Data Start Row: `6`)
- **Excluded Distractor Tabs:** `2` (`Residential_FTTH_Plans, Deprecated_Legacy_SKUs`)
- **Valid B2B SKUs Promoted:** `18` (`198` triples in `<urn:telco:graph:ref:catalog>`)
- **Quarantined Rows Blocked:** `2`
- **Persisted Triples in `<urn:telco:graph:virtual:ib>`:** `0`

## (a) Worksheet Tab & Banner Filtering Audit

| Worksheet | Classification | Header Row | Data Start Row | Banner Rows | Rationale |
|---|---|---:|---:|---|---|
| `Residential_FTTH_Plans` | `EXCLUDED_DISTRACTOR_TAB` | 5 | 6 | [1, 2, 3, 4] | Consumer broadband and residential GPON/XGS-PON product catalog, explicitly out of scope for B2B enterprise SLA assurance under UC-001. |
| `B2B_Enterprise_SLA_Matrix` | `TARGET_INGEST_TAB` | 5 | 6 | [1, 2, 3, 4] | Authoritative commercial catalog defining B2B Enterprise Carrier Ethernet and IP-VPN tiers, packet-loss thresholds, MTTR targets, and autonomous optical remediation governance matching the UC-001 charter. |
| `Deprecated_Legacy_SKUs` | `EXCLUDED_DISTRACTOR_TAB` | 5 | 6 | [1, 2, 3, 4] | Historical archive of decommissioned legacy technologies (Frame Relay, ISDN, PDH/SDH, ATM) retired from active provisioning and assurance workflows. |

## (b) Column-to-TBox RML Mapping Table

| Col # | Source Column Header | Status | Target Property | Datatype | Notes |
|---:|---|---|---|---|---|
| 1 | `Product_SKU_Code` | `MAPPED` | `tmf:skuCode` | `xsd:string` | Primary commercial SKU identifier uniquely identifying each service specification instance in the catalog. |
| 2 | `Marketing_Name` | `MAPPED` | `tmf:specName` | `xsd:string` | Commercial marketing title and display label for the service specification. |
| 3 | `Service_Category` | `EXCLUDED_NOISE` | `-` | `-` | Internal organizational category tag not represented in the locked Conceptual TBox. |
| 4 | `Max_Packet_Loss_Pct` | `MAPPED` | `telco:maxPacketLossPct` | `xsd:double` | Contractual packet loss percentage ceiling governing closed-loop triage under eTOM 1.3.7. |
| 5 | `Max_Jitter_ms` | `MAPPED` | `telco:maxJitterMs` | `xsd:double` | Maximum allowed network delay variation (jitter) in milliseconds. |
| 6 | `MTTR_Target_Hours` | `MAPPED` | `telco:mttrHours` | `xsd:double` | Mean Time to Repair (MTTR) SLA target in operational hours. |
| 7 | `Eligible_Upgrade_SKU` | `MAPPED` | `telco:eligibleUpgradeSpec` | `-` | Commercial upgrade path referencing the next tier service specification entity IRI. |
| 8 | `Auto_Remediation_Allowed` | `MAPPED` | `telco:autoRemediationAllowed` | `xsd:boolean` | Governance flag indicating whether autonomous optical recalibration is legally and technically authorized. |
| 9 | `Monthly_List_Price_EUR` | `EXCLUDED_NOISE` | `-` | `-` | Financial commercial billing list price, excluded from technical assurance ontology per charter boundaries. |
| 10 | `Internal_Finance_GL_Code` | `EXCLUDED_NOISE` | `-` | `-` | Internal ERP general ledger accounting code, excluded as non-semantic enterprise noise. |
| 11 | `Shadow_Lifecycle_Flag` | `MAPPED` | `telco:lifecycleStatus` | `xsd:string` | Catalog publication status mapped from internal lifecycle codes into canonical statuses. |
| 12 | `Min_Contract_Months` | `MAPPED` | `telco:minContractMonths` | `xsd:integer` | Minimum contractual commitment duration in integer months. |
| 13 | `SLA_Credit_Cap_Pct` | `MAPPED` | `telco:slaCreditCapPct` | `xsd:double` | Contractual service credit penalty cap expressed as a percentage. |
| 14 | `Engineering_Notes` | `EXCLUDED_NOISE` | `-` | `-` | Free-form administrative NOC notes excluded from the structured knowledge graph. |

## (c) Promoted B2B SKUs Summary (18 Valid SKUs)

| Excel Row | SKU Code | Subject IRI | Triples | Max Packet Loss % | Availability % | Auto-Remediation | Lifecycle |
|---:|---|---|---:|---:|---:|---|---|
| 6 | `ETH-1G-SILVER` | `urn:telco:catalog:spec:ETH-1G-SILVER` | 11 | 0.25 | - | True | `ACTIVE` |
| 7 | `ETH-10G-GOLD` | `urn:telco:catalog:spec:ETH-10G-GOLD` | 11 | 0.1 | - | True | `ACTIVE` |
| 8 | `ETH-100G-PLATINUM` | `urn:telco:catalog:spec:ETH-100G-PLATINUM` | 11 | 0.01 | - | True | `ACTIVE` |
| 9 | `ETH-400G-ULTRA` | `urn:telco:catalog:spec:ETH-400G-ULTRA` | 11 | 0.005 | - | False | `ACTIVE` |
| 10 | `MPLS-VPN-STD` | `urn:telco:catalog:spec:MPLS-VPN-STD` | 11 | 0.5 | - | False | `ACTIVE` |
| 11 | `MPLS-VPN-PREM` | `urn:telco:catalog:spec:MPLS-VPN-PREM` | 11 | 0.1 | - | True | `ACTIVE` |
| 12 | `SDWAN-PRO` | `urn:telco:catalog:spec:SDWAN-PRO` | 11 | 0.2 | - | True | `ACTIVE` |
| 13 | `SDWAN-ENTERPRISE-AI` | `urn:telco:catalog:spec:SDWAN-ENTERPRISE-AI` | 11 | 0.05 | - | True | `ACTIVE` |
| 14 | `DIA-1G-BIZ` | `urn:telco:catalog:spec:DIA-1G-BIZ` | 11 | 0.3 | - | False | `ACTIVE` |
| 15 | `DIA-10G-BIZ` | `urn:telco:catalog:spec:DIA-10G-BIZ` | 11 | 0.1 | - | True | `ACTIVE` |
| 16 | `DIA-100G-CORE` | `urn:telco:catalog:spec:DIA-100G-CORE` | 11 | 0.02 | - | False | `ACTIVE` |
| 17 | `WAVELENGTH-10G-METRO` | `urn:telco:catalog:spec:WAVELENGTH-10G-METRO` | 11 | 0.001 | - | False | `ACTIVE` |
| 18 | `WAVELENGTH-100G-METRO` | `urn:telco:catalog:spec:WAVELENGTH-100G-METRO` | 11 | 0.001 | - | False | `ACTIVE` |
| 19 | `5G-SLICE-URLLC` | `urn:telco:catalog:spec:5G-SLICE-URLLC` | 11 | 0.05 | - | True | `ACTIVE` |
| 20 | `5G-SLICE-EMBB` | `urn:telco:catalog:spec:5G-SLICE-EMBB` | 11 | 0.5 | - | True | `ACTIVE` |
| 21 | `GOV-SEC-ETH-10G` | `urn:telco:catalog:spec:GOV-SEC-ETH-10G` | 11 | 0.05 | - | False | `ACTIVE` |
| 22 | `CLOUD-CONNECT-10G` | `urn:telco:catalog:spec:CLOUD-CONNECT-10G` | 11 | 0.1 | - | True | `ACTIVE` |
| 23 | `ETH-2.5G-MID` | `urn:telco:catalog:spec:ETH-2.5G-MID` | 11 | 0.2 | - | True | `PILOT` |

## (d) Detailed `pySHACL` Row Quarantine Table (2 Quarantined Rows)

| Excel Row | SKU Code | Violated SHACL Constraint | Result Path | SHACL Message | Raw Values |
|---:|---|---|---|---|---|
| 24 | `DARK-FIBER-METRO-X` | `http://www.w3.org/ns/shacl#MinInclusiveConstraintComponent; http://www.w3.org/ns/shacl#DatatypeConstraintComponent; http://www.w3.org/ns/shacl#InConstraintComponent` | `http://telco.enterprise.org/ontology/maxPacketLossPct; http://telco.enterprise.org/ontology/autoRemediationAllowed; http://telco.enterprise.org/ontology/lifecycleStatus` | A ServiceSpecification must define maximum packet loss percentage between 0.0 and 100.0.; A ServiceSpecification must define boolean autoRemediationAllowed.; A ServiceSpecification must have lifecycle status of ACTIVE, PILOT, or DEPRECATED. | `{"Product_SKU_Code": "DARK-FIBER-METRO-X", "Marketing_Name": "Unlit Metro Dark Fiber Pair (Dirty Row Test)", "Service_Category": "L0_DARK_FIBER", "Max_Packet_Loss_Pct": -0.5, "Max_Jitter_ms": 0, "MTTR_Target_Hours": 24, "Eligible_Upgrade_SKU": "WAVELENGTH-10G-METRO", "Auto_Remediation_Allowed": "MAYBE_LEGACY", "Monthly_List_Price_EUR": 1500, "Internal_Finance_GL_Code": "GL-ERR-9901", "Shadow_Lifecycle_Flag": "99_INVALID", "Min_Contract_Months": 36, "SLA_Credit_Cap_Pct": 10, "Engineering_Notes": "DIRTY DATA TEST: Negative packet loss & invalid enum for pySHACL quarantine"}` |
| 25 | `SDWAN-LEGACY-99` | `http://www.w3.org/ns/shacl#MaxInclusiveConstraintComponent; http://www.w3.org/ns/shacl#DatatypeConstraintComponent; http://www.w3.org/ns/shacl#InConstraintComponent` | `http://telco.enterprise.org/ontology/maxPacketLossPct; http://telco.enterprise.org/ontology/autoRemediationAllowed; http://telco.enterprise.org/ontology/lifecycleStatus` | A ServiceSpecification must define maximum packet loss percentage between 0.0 and 100.0.; A ServiceSpecification must define boolean autoRemediationAllowed.; A ServiceSpecification must have lifecycle status of ACTIVE, PILOT, or DEPRECATED. | `{"Product_SKU_Code": "SDWAN-LEGACY-99", "Marketing_Name": "Unmigrated Legacy Velo Box (Dirty Row Test)", "Service_Category": "MANAGED_SDWAN", "Max_Packet_Loss_Pct": 125, "Max_Jitter_ms": -5, "MTTR_Target_Hours": null, "Eligible_Upgrade_SKU": "SDWAN-PRO", "Auto_Remediation_Allowed": "UNKNOWN", "Monthly_List_Price_EUR": -100, "Internal_Finance_GL_Code": "GL-ERR-9902", "Shadow_Lifecycle_Flag": "99_OBS_SHADOW", "Min_Contract_Months": 12, "SLA_Credit_Cap_Pct": 0, "Engineering_Notes": "DIRTY DATA TEST: Loss > 100% and NULL MTTR for pySHACL quarantine"}` |
