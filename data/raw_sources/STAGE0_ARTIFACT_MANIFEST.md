# Stage 0 (Activity 0.2) Frozen Source Artifact Manifest — Use Case UC-001

**Document ID:** `MANIFEST-TELCO-UC001-ACT02-V1`  
**Use Case:** `UC-001` — *Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration*  
**Target Customer:** `A Corporate Enterprise` (`CUST-ENT-409` in SQL CMDB / `"A Corporate Enterprise B.V."`, KvK `NL-8841209` in MSA PDF)  
**Target Circuit & Resources:** Circuit `CIR-994821` (`ETH-10G-GOLD`) $\rightarrow$ PE Router `NLD-HAG-PE02` $\rightarrow$ OLT Port `OLT04-P12` (`RFS-OLT04-P12`) $\rightarrow$ CPE Asset `CPE-ASN-7741` (Hardware SKU `NOK-7210-SAS-Mxp`)  
**Generator Module:** `src/stage0_generator.py` via `scripts/generate_stage0_raw_sources.py` (Deterministic Seed = `42`)

---

## 1. Summary of Generated Raw Data Artifacts

| Prong / Source Type | Artifact File Path | Volume / Noise Profile | Exact Location of Target `UC-001` Data Points |
| :--- | :--- | :--- | :--- |
| **Prong 1 (SQLite CMDB)** | `data/raw_sources/sql/cmdb_installed_base.db` | 4 tables, **104 total rows**, nullable FKs, shadow enums (`'10'`,`'20'`,`'99'`), mixed units (`Gbps`,`Mbps`,`Kbps`), SCD2 history | `T_OSS_CUST_PARTY` (`PARTY_SURR_ID=1009`, `CUST_EXT_REF='CUST-ENT-409'`); `T_CMDB_CFS_CIRCUIT` (`CFS_ROW_ID=2001` active `CIR-994821`, `CFS_ROW_ID=2000` superseded SCD2 row); `T_CMDB_RFS_RESOURCE` (`RFS_ID='RFS-OLT04-P12'`) |
| **Prong 1 (SQL Dump)** | `data/raw_sources/sql/cmdb_dump.sql` | Full DDL + DML export of all 4 tables (`T_OSS_CUST_PARTY`, `T_CMDB_CFS_CIRCUIT`, `T_CMDB_RFS_RESOURCE`, `T_BILLING_AUDIT_NOISE`) | Same as `cmdb_installed_base.db` |
| **Prong 2 (Excel SLA Catalog)** | `data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx` | **3 tabs**, merged banners (rows 1–3), empty row 4, headers in row 5, **50 total SKUs**, 14 columns in Tab 2 + 2 dirty SHACL quarantine test rows | **Tab 2 (`B2B_Enterprise_SLA_Matrix`), Row 7**: `Product_SKU_Code='ETH-10G-GOLD'`, `Max_Packet_Loss_Pct=0.1`, `Eligible_Upgrade_SKU='ETH-100G-PLATINUM'`, `Auto_Remediation_Allowed='YES'` |
| **Prong 3A (Hardware Manual PDF)** | `data/raw_sources/pdf/Vendor_Optical_Hardware_Manual_v4.pdf` | **5 pages / 5 chapters** covering power, thermal, RJ-45 copper, and multi-vendor optical transceivers (`Cisco`, `Juniper`, `Nokia`) | **Page 4, Chapter 4 (Section 4.2 & Specification Table Row 3)**: `NOK-7210-SAS-Mxp` (10GBASE-LR 1310nm): Nominal Tx `-1.0 dBm`, Overload Rx `-1.0 dBm`, Normal Rx `-14.0 to -24.9 dBm`, DDM Recalibration Window `-25.0 to -27.5 dBm`, Critical LOS Cutoff `< -27.5 dBm` |
| **Prong 3B (MSA Contract PDF)** | `data/raw_sources/pdf/MSA_Contract_A_Corporate_Enterprise_2026.pdf` | **4 pages / 7 clauses** covering corporate parties, term, invoicing, liability, force majeure, 5 site schedules (Annex A), and Annex B SLA rules | **Page 1 (Clause 1)**: `"A Corporate Enterprise B.V."` (`NL-8841209` / `CUST-ENT-409`); **Page 3 (Clause 6 / Annex A, Site 1)**: `CIR-994821` on `ETH-10G-GOLD`; **Page 4 (Clause 7 / Annex B)**: `15%` monthly credit if packet loss `> 0.1%` for `> 30 min` + pre-authorized remote DDM recalibration if `maintenance_lock == false` |
| **Multi-Procedure SOP (DOCX)** | `data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.docx` | **6 sections** (1 governance + 4 distractor SOPs `101`, `205`, `310`, `509` + 1 target SOP `402`) | **Section 5 (`SOP-ASSUR-402`)**: 4-step workflow, `reported_packet_loss_pct >= 0.5%` pre-condition, semantic context join, live singleton optical probe (`bypass_cache=true`), and deterministic **Branches A, B, and C** |
| **Multi-Procedure SOP (Markdown)** | `data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.md` | Markdown mirror of the 6-section Master Runbook for direct inspection and diffing | **Section 5 (`SOP-ASSUR-402`)** |

---

## 2. Detailed Breakdown by Prong & Noise Filtering Verification

### 2.1 Prong 1: Relational SQL CMDB (`cmdb_installed_base.db` & `cmdb_dump.sql`)
- **`T_OSS_CUST_PARTY` (15 rows, 7 columns)**:
  - Columns: `PARTY_SURR_ID`, `CUST_EXT_REF`, `LEGAL_NAME`, `SEGMENT_CD`, `ACCT_MGR_ID`, `LEGACY_CRM_ID`, `CREATED_TS`
  - **Target Row**: `PARTY_SURR_ID=1009`, `CUST_EXT_REF='CUST-ENT-409'`, `LEGAL_NAME='A Corporate Enterprise'`, `SEGMENT_CD='ENT_VIP'`
- **`T_CMDB_CFS_CIRCUIT` (32 rows, 11 columns)**:
  - Columns: `CFS_ROW_ID`, `CIRCUIT_ID`, `CUST_REF_ID`, `PROD_SPEC_CODE`, `OPER_STATUS_CD`, `BW_VAL`, `BW_UNIT_CD`, `INSTALL_DT`, `VALID_FROM_TS`, `VALID_TO_TS`, `LEGACY_BILL_TAG`
  - **Target Active Row**: `CFS_ROW_ID=2001`, `CIRCUIT_ID='CIR-994821'`, `CUST_REF_ID='CUST-ENT-409'`, `PROD_SPEC_CODE='ETH-10G-GOLD'`, `OPER_STATUS_CD='10'` (Active), `BW_VAL=10`, `BW_UNIT_CD='Gbps'`, `VALID_FROM_TS='2025-06-01T00:00:00Z'`, `VALID_TO_TS=NULL`
  - **Target Historical SCD2 Row (Superseded)**: `CFS_ROW_ID=2000`, `CIRCUIT_ID='CIR-994821'`, `PROD_SPEC_CODE='ETH-1G-SILVER'`, `VALID_FROM_TS='2023-01-15T00:00:00Z'`, `VALID_TO_TS='2025-06-01T00:00:00Z'`
- **`T_CMDB_RFS_RESOURCE` (32 rows, 9 columns)**:
  - Columns: `RFS_ID`, `PARENT_CFS_ID`, `PE_ROUTER_HOSTNAME`, `OLT_PORT_ID`, `CPE_ASSET_ID`, `CPE_MODEL_SKU`, `VLAN_TAG`, `FIBER_SPAN_ID`, `LAST_SYNC_UTC`
  - **Target Row**: `RFS_ID='RFS-OLT04-P12'`, `PARENT_CFS_ID='CIR-994821'`, `PE_ROUTER_HOSTNAME='NLD-HAG-PE02'`, `OLT_PORT_ID='OLT04-P12'`, `CPE_ASSET_ID='CPE-ASN-7741'`, `CPE_MODEL_SKU='NOK-7210-SAS-Mxp'`, `VLAN_TAG=2409`, `FIBER_SPAN_ID='FBR-HAG-RING02-S14'`
- **`T_BILLING_AUDIT_NOISE` (25 rows, 10 columns)**:
  - Columns: `INV_ID`, `CUST_REF_ID`, `BILL_CYCLE_CD`, `GROSS_AMT_EUR`, `TAX_CD`, `VAT_PCT`, `GL_POST_DT`, `DUNNING_LVL`, `ERP_BATCH_REF`, `AUDIT_HASH`
  - Purpose: Completely excluded by Layer 4 R2RML/SMS2 virtual graph mappings during schema pruning.

### 2.2 Prong 2: Multi-Tab Excel Catalog (`Telco_Master_Product_SLA_Catalog_2026.xlsx`)
- **Formatting Noise**: Merged banner across rows 1–3, empty separator row 4, table headers in row 5.
- **Tab 1 (`Residential_FTTH_Plans`)**: 15 consumer GPON/XGS-PON plans (distractor worksheet ignored by ingestion).
- **Tab 2 (`B2B_Enterprise_SLA_Matrix`)**: 20 B2B SKUs across 14 columns:
  - **Row 7 (Target)**: `ETH-10G-GOLD` | `Max_Packet_Loss_Pct = 0.1` | `Max_Jitter_ms = 2.0` | `MTTR_Target_Hours = 4` | `Eligible_Upgrade_SKU = 'ETH-100G-PLATINUM'` | `Auto_Remediation_Allowed = 'YES'`
  - **Row 8 (Upgrade Target)**: `ETH-100G-PLATINUM` | `Max_Packet_Loss_Pct = 0.01` | `MTTR_Target_Hours = 2`
  - **Rows 24 & 25 (SHACL Quarantine Test Rows)**: `DARK-FIBER-METRO-X` (`Max_Packet_Loss_Pct = -0.5`, `Shadow_Lifecycle_Flag = '99_INVALID'`) and `SDWAN-LEGACY-99` (`Max_Packet_Loss_Pct = 125.0`, `MTTR_Target_Hours = NULL`).
- **Tab 3 (`Deprecated_Legacy_SKUs`)**: 15 obsolete ATM/Frame-Relay/ISDN SKUs (distractor worksheet ignored by ingestion).

### 2.3 Prong 3: Unstructured PDFs (`Vendor_Optical_Hardware_Manual_v4.pdf` & `MSA_Contract_A_Corporate_Enterprise_2026.pdf`)
- **`Vendor_Optical_Hardware_Manual_v4.pdf` (5 Pages)**:
  - Pages 1–3 (Chapters 1–3) & Page 5 (Chapter 5): Power, thermal, copper RJ-45, and field cleaning distractors.
  - **Page 4 (Chapter 4)**: `NOK-7210-SAS-Mxp` 10GBASE-LR 1310nm thresholds: Nominal Tx `-1.0 dBm`, Overload Rx `-1.0 dBm`, Normal Rx `-14.0 dBm to -24.9 dBm`, Soft Degradation / DDM Recalibration Window `-25.0 dBm to -27.5 dBm`, Critical LOS Cutoff `< -27.5 dBm`.
- **`MSA_Contract_A_Corporate_Enterprise_2026.pdf` (4 Pages)**:
  - **Page 1 (Clause 1)**: Links legal entity `"A Corporate Enterprise B.V."` (Registration `NL-8841209`) to OSS ID `CUST-ENT-409` (`"A Corporate Enterprise"`).
  - **Page 3 (Clause 6 / Annex A)**: Lists `CIR-994821` (`ETH-10G-GOLD`, `NOK-7210-SAS-Mxp`) alongside 4 distractor corporate sites.
  - **Page 4 (Clause 7 / Annex B)**: Specifies `15%` monthly service credit if packet loss exceeds `0.1%` for `>30 minutes` on `CIR-994821`, and grants pre-authorized remote TMF640 DDM optical recalibration when `maintenance_lock == false`.

---

## 3. Living Governance Logs (Updated for Activity 0.2 Completion)

### 3.1 Use Case Design & Implementation Log (UCDIL — Baseline v2)

| Design Dimension | Parameter / Artifact | Locked Specification for UC-001 | Status |
| :--- | :--- | :--- | :--- |
| **1. Scope & eTOM** | Use Case ID & Title | `UC-001`: Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | TM Forum eTOM / SID | eTOM `1.3.7` & `1.4.5` \| SID: `Customer -> CFS -> ServiceSpec -> RFS -> PhysicalResource -> Spec` | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | Customer & Circuit | Customer: `'A Corporate Enterprise'` (`CUST-ENT-409` / `'A Corporate Enterprise B.V.'`, `NL-8841209`) \| Circuit: `CIR-994821` | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | Hardware & Port | CPE Asset: `CPE-ASN-7741` \| Model SKU: `NOK-7210-SAS-Mxp` \| OLT Port: `OLT04-P12` \| Router: `NLD-HAG-PE02` | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | SOP & Branches | Source: `SOP_NOC_Master_Assurance_Runbook_v2026` (Section 5: `SOP-ASSUR-402`) $\rightarrow$ Branches A, B, C | **LOCKED (Act 0.1)** |
| **2. Data Footprint** | Prong 1 (SQL CMDB) | `data/raw_sources/sql/cmdb_installed_base.db` & `cmdb_dump.sql` (4 tables, 104 rows, SCD2 + shadow enums) | **LOCKED (Act 0.2)** |
| **2. Data Footprint** | Prong 2 (Excel SLA) | `data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx` (3 tabs, 50 SKUs, 2 dirty SHACL test rows) | **LOCKED (Act 0.2)** |
| **2. Data Footprint** | Prong 3 (PDF Docs) | `Vendor_Optical_Hardware_Manual_v4.pdf` (5p) & `MSA_Contract_A_Corporate_Enterprise_2026.pdf` (4p) | **LOCKED (Act 0.2)** |
| **2. Data Footprint** | Multi-SOP Runbook | `SOP_NOC_Master_Assurance_Runbook_v2026.docx` & `SOP_NOC_Master_Assurance_Runbook_v2026.md` (6 sections; target `SOP-ASSUR-402` in Section 5) | **LOCKED (Act 0.2)** |

### 3.2 Observation Notepad (Findings Through Activity 0.2)

| ID & Activity | Observation / Friction Encountered | Impact Target | Remediation Applied |
| :--- | :--- | :--- | :--- |
| **OBS-00 (Setup)** | Implementation Plan needed a living Use Case Design & Implementation Log (UCDIL) across Stages 0–3. | Implementation Plan (Sections 2 & 6) | Maintained UCDIL in Activity 0.1 Charter and updated to Baseline v2 in `STAGE0_ARTIFACT_MANIFEST.md`. |
| **OBS-01 (Act 0.1)** | Telecom SOPs are multi-procedure runbooks; compiler must slice out only the target procedure. | Architecture Blueprint (Section 3.2) | Generated 6-section Master Runbook with 4 distractor SOPs (`101`, `205`, `310`, `509`) and target `SOP-ASSUR-402` in Section 5. |
| **OBS-02 (Act 0.1)** | Enterprise data buries target parameters inside wide SQL tables, multi-tab spreadsheets, and multi-chapter PDFs. | Implementation Plan (Sections 2.2 & 4.3) | Generated wide 4-table SQLite DB, 3-tab Excel with merged banners, and 2 multi-page PDFs with chapter/clause noise. |
| **OBS-03 (Act 0.2)** | Testing Layer 4 temporal window filtering (`SCD Type 2`) and Track B `pySHACL` quarantine requires explicit historical and malformed distractor records in the frozen Stage 0 dataset. | Stage 0 Raw Data & Track B Ingestion | Added 1 superseded SCD2 row (`CFS_ROW_ID=2000`) for `CIR-994821` in `T_CMDB_CFS_CIRCUIT` and 2 malformed distractor rows (`Rows 24–25`) in `B2B_Enterprise_SLA_Matrix`. |
