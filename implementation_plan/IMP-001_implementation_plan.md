# Implementation Plan — `IMP-001`: Stage 0 (Activity 0.2) Wide & Noise-Rich Raw Data Sources Generator

## 0. Unique Reference ID
- **Reference ID:** `IMP-001`

## 1. Objective & Scope

### Objective
Build and execute a self-contained, deterministic Python generator script (`scripts/generate_stage0_raw_sources.py`) that produces the frozen Stage 0 (Activity 0.2) raw enterprise data footprint under `data/raw_sources/` for **Use Case UC-001** (*Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration* for customer **A Corporate Enterprise**, circuit **CIR-994821**).

### Scope & Target Artifacts
1. **Prong 1 — Wide Relational SQL CMDB**:
   - `data/raw_sources/sql/cmdb_installed_base.db` (SQLite database)
   - `data/raw_sources/sql/cmdb_dump.sql` (Full DDL/DML SQL dump)
   - Four tables with exact required columns, nullable foreign keys, shadow enums (`'10'`=Active, `'20'`=Degraded, `'99'`=Cancelled), mixed bandwidth units (`Gbps`, `Mbps`, `Kbps`), and 40–50+ distractor rows:
     - `T_OSS_CUST_PARTY` (7 columns, 15 customers including `CUST-ENT-409` / `'A Corporate Enterprise'`, `SEGMENT_CD='ENT_VIP'`)
     - `T_CMDB_CFS_CIRCUIT` (11 columns, 32 rows covering 31 distinct circuits: active row for `CIR-994821` with `OPER_STATUS_CD='10'` and `VALID_TO_TS=NULL`, 1 historical superseded SCD Type 2 row for `CIR-994821` with `VALID_TO_TS` in the past, plus 30 distractor circuits across MPLS, FTTx, and 5G-Slicing)
     - `T_CMDB_RFS_RESOURCE` (9 columns, 32 resource rows including target `CIR-994821` $\rightarrow$ `NLD-HAG-PE02` $\rightarrow$ `OLT04-P12` $\rightarrow$ `CPE-ASN-7741` $\rightarrow$ `NOK-7210-SAS-Mxp`, plus 31 distractor rows across Cisco, Juniper, Huawei, and Nokia hardware)
     - `T_BILLING_AUDIT_NOISE` (10 columns, 25 unrelated billing/tax audit rows to verify schema pruning)
2. **Prong 2 — Multi-Tab Excel Workbook**:
   - `data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx`
   - Three worksheets, each formatted with a merged title banner in rows 1–3, an empty row 4, and column headers in row 5:
     - Tab 1 `Residential_FTTH_Plans`: 15 consumer FTTH plans (distractor tab).
     - Tab 2 `B2B_Enterprise_SLA_Matrix`: 20 enterprise products across 14 columns (`Product_SKU_Code`, `Marketing_Name`, `Service_Category`, `Max_Packet_Loss_Pct`, `Max_Jitter_ms`, `MTTR_Target_Hours`, `Eligible_Upgrade_SKU`, `Auto_Remediation_Allowed`, `Monthly_List_Price_EUR`, `Internal_Finance_GL_Code`, `Shadow_Lifecycle_Flag`, `Min_Contract_Months`, `SLA_Credit_Cap_Pct`, `Engineering_Notes`). Target `ETH-10G-GOLD` has `Max_Packet_Loss_Pct=0.1`, `Eligible_Upgrade_SKU='ETH-100G-PLATINUM'`, `Auto_Remediation_Allowed='YES'`. Includes 2 deliberate dirty/non-compliant distractor rows to test Track B `pySHACL` quarantine.
     - Tab 3 `Deprecated_Legacy_SKUs`: 15 legacy ATM/Frame-Relay/ISDN SKUs (distractor tab).
3. **Prong 3 — Two Multi-Chapter Unstructured PDFs**:
   - `data/raw_sources/pdf/Vendor_Optical_Hardware_Manual_v4.pdf` (5 pages):
     - Chapter 1: General Safety, Rack Mounting & Power Supply Specifications
     - Chapter 2: Environmental, Thermal & Fan Tray Thresholds
     - Chapter 3: Copper RJ-45 & Electrical Interface Specifications (Cisco ASR-920 & Juniper ACX2100)
     - Chapter 4: Optical SFP+/XFP Transceiver Operating Parameters (prose + specification table covering `CISCO-ASR-920-10G`, `JUNIPER-ACX-10G`, and `NOK-7210-SAS-Mxp` with 10GBASE-LR 1310nm thresholds: Nominal Tx `-1.0 dBm`, Overload Rx `-1.0 dBm`, Normal Rx `-14.0 dBm to -24.9 dBm`, Soft Degradation / DDM Recalibration Window `-25.0 dBm to -27.5 dBm`, Critical LOS / Hard Attenuation Cutoff `< -27.5 dBm`)
     - Chapter 5: Transceiver Diagnostics & Field Cleaning Procedures
   - `data/raw_sources/pdf/MSA_Contract_A_Corporate_Enterprise_2026.pdf` (4 pages):
     - Clauses 1–5: Parties (`"A Corporate Enterprise B.V."`, Registration `NL-8841209`), Term, Invoicing, Liability, Force Majeure
     - Clause 6 (Annex A): Subscribed Circuit Schedule (`CIR-994821` on `ETH-10G-GOLD` plus 4 other corporate sites)
     - Clause 7 (Annex B): Bespoke SLA Penalty & Autonomous Maintenance Rules for `CIR-994821` (15% monthly service credit if packet loss exceeds 0.1% for >30 minutes; pre-authorized remote DDM optical recalibration provided no customer maintenance freeze lock is active)
4. **Multi-Procedure NOC SOP Manual**:
   - `data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.docx`
   - `data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.md`
   - Six sections:
     - Section 1: Purpose, General NOC Safety & Change Control Governance
     - Section 2 (`SOP-ASSUR-101`): BGP Peering Session Flap Triage & Dampening
     - Section 3 (`SOP-ASSUR-205`): 5G RAN gNodeB Sector Outage & Tilt Reset
     - Section 4 (`SOP-ASSUR-310`): Residential GPON ONT Optical Dying-Gasp Handling
     - Section 5 (`SOP-ASSUR-402` — TARGET): Enterprise L2 Fiber Packet-Loss Triage & Optical DDM Recalibration (4-step deterministic workflow, `reported_packet_loss_pct >= 0.5%` pre-condition, semantic context lookup across CMDB/Catalog/PDFs, live singleton optical probe `bypass_cache=true`, mutex lock check, and Branches A, B, C)
     - Section 6 (`SOP-ASSUR-509`): Core DWDM Erbium-Doped Fiber Amplifier (EDFA) Pump Laser Replacement
5. **Stage 0 Artifact Manifest & Updated Governance Logs**:
   - `data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md` documenting all generated file paths, row/page counts, exact locations of `UC-001` target parameters, plus the updated **Use Case Design & Implementation Log (UCDIL — v2, Activity 0.2 Locked)** and **Observation Notepad**.

---

## 2. Key Design Decisions

1. **Exact Prompt Schema Compliance**:
   - Use the exact column names defined in the prompt for `T_OSS_CUST_PARTY` (7 cols), `T_CMDB_CFS_CIRCUIT` (11 cols), `T_CMDB_RFS_RESOURCE` (9 cols), and `T_BILLING_AUDIT_NOISE` (10 cols).
2. **SCD Type 2 Temporal Representation for `CIR-994821`**:
   - Insert 1 active row for `CIR-994821` (`OPER_STATUS_CD='10'`, `VALID_FROM_TS='2025-06-01T00:00:00Z'`, `VALID_TO_TS=NULL`) and 1 historical superseded row (`CFS_ROW_ID=2000`, `OPER_STATUS_CD='10'`, `PROD_SPEC_CODE='ETH-1G-SILVER'`, `VALID_FROM_TS='2023-01-15T00:00:00Z'`, `VALID_TO_TS='2025-06-01T00:00:00Z'`) to test Layer 4 temporal window filtering.
3. **SHACL Quarantine Test Cases in Excel**:
   - Include 2 deliberate dirty distractor rows in `B2B_Enterprise_SLA_Matrix` (e.g., negative `Max_Packet_Loss_Pct = -0.5` and legacy `Shadow_Lifecycle_Flag = '99_INVALID'` / missing `MTTR_Target_Hours`) on non-target SKUs while keeping `ETH-10G-GOLD`, `ETH-100G-PLATINUM`, and 16 other B2B rows strictly valid.
4. **Deterministic Generation & Multi-Page PDF Layout**:
   - Fix `random.seed(42)`, recreate outputs idempotently, and use `reportlab.platypus` with explicit `PageBreak()` elements so `Vendor_Optical_Hardware_Manual_v4.pdf` renders as a 5-page document and `MSA_Contract_A_Corporate_Enterprise_2026.pdf` renders as a 4-page document.

---

## 3. Step-by-Step Implementation Plan

### Step 1: Environment Verification
- Confirm `.venv` contains `openpyxl`, `reportlab`, `python-docx`, and `pandas` (already installed in `.venv`).

### Step 2: Author `scripts/generate_stage0_raw_sources.py`
- Implement modular generator functions:
  - `generate_sql_cmdb(base_dir)`: Creates `data/raw_sources/sql/cmdb_installed_base.db` and exports `data/raw_sources/sql/cmdb_dump.sql`.
  - `generate_excel_catalog(base_dir)`: Creates `data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx` with 3 tabs, merged rows 1–3, empty row 4, headers in row 5, and target/distractor rows.
  - `generate_pdfs(base_dir)`: Creates `Vendor_Optical_Hardware_Manual_v4.pdf` (5 pages) and `MSA_Contract_A_Corporate_Enterprise_2026.pdf` (4 pages).
  - `generate_sop_runbook(base_dir)`: Creates `SOP_NOC_Master_Assurance_Runbook_v2026.docx` and `SOP_NOC_Master_Assurance_Runbook_v2026.md` with all 6 sections.
  - `generate_manifest(base_dir, stats)`: Creates `data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md` including the UCDIL and Observation Notepad updates.
  - `verify_and_print_summary(base_dir, stats)`: Queries the generated SQLite DB, inspects the Excel sheets, checks PDF sizes/page counts and SOP sections, and prints a structured console verification table.

### Step 3: Execute & Verify
- Run `.venv\Scripts\python.exe scripts/generate_stage0_raw_sources.py`.
- Verify that all 7 output files exist under `data/raw_sources/` and that all target `UC-001` parameters match the specification.
- Proceed to Gate 5 to append the **Implementation Summary** to `implementation_plan/IMP-001_implementation_plan.md`.

---

## 4. Implementation Summary (Gate 5)

### What Was Built
Built and executed the deterministic Stage 0 (Activity 0.2) raw data source generator script (`scripts/generate_stage0_raw_sources.py`) for **Use Case UC-001** (*Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration* for customer **A Corporate Enterprise**, circuit **CIR-994821**).

### Files Created
1. **Generator Script**:
   - [`scripts/generate_stage0_raw_sources.py`](file:///d:/Telecom%20Agentic%20AI%20Demo/scripts/generate_stage0_raw_sources.py)
2. **Prong 1 — Relational SQL CMDB**:
   - [`data/raw_sources/sql/cmdb_installed_base.db`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/sql/cmdb_installed_base.db) (32,768 bytes; 4 tables, 104 total rows)
   - [`data/raw_sources/sql/cmdb_dump.sql`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/sql/cmdb_dump.sql) (19,344 bytes; full SQL DDL/DML dump)
3. **Prong 2 — Multi-Tab Excel Workbook**:
   - [`data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx) (12,576 bytes; 3 tabs, merged banner rows 1–3, empty row 4, headers in row 5, 50 total SKUs including `ETH-10G-GOLD` and 2 dirty distractor rows for SHACL quarantine testing)
4. **Prong 3 — Multi-Chapter Unstructured PDFs**:
   - [`data/raw_sources/pdf/Vendor_Optical_Hardware_Manual_v4.pdf`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/pdf/Vendor_Optical_Hardware_Manual_v4.pdf) (10,329 bytes; 5 pages / 5 chapters, with `NOK-7210-SAS-Mxp` optical thresholds on Page 4, Chapter 4)
   - [`data/raw_sources/pdf/MSA_Contract_A_Corporate_Enterprise_2026.pdf`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/pdf/MSA_Contract_A_Corporate_Enterprise_2026.pdf) (7,449 bytes; 4 pages / 7 clauses, with `"A Corporate Enterprise B.V."` `NL-8841209`, Annex A schedule, and Annex B 15% SLA penalty & pre-authorized DDM recalibration on Page 4)
5. **Multi-Procedure NOC SOP Master Runbook**:
   - [`data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.docx`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.docx) (40,739 bytes; 6 sections, with target `SOP-ASSUR-402` in Section 5)
   - [`data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.md`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/sop/SOP_NOC_Master_Assurance_Runbook_v2026.md) (8,368 bytes; Markdown mirror)
6. **Artifact Manifest & Living Governance Logs**:
   - [`data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md`](file:///d:/Telecom%20Agentic%20AI%20Demo/data/raw_sources/STAGE0_ARTIFACT_MANIFEST.md) (11,283 bytes; full manifest + updated UCDIL Baseline v2 and Observation Notepad `OBS-00` through `OBS-03`)

### Deviations Taken During Gate 4
- **None.** Execution followed the approved Gate 3 plan with zero deviations.

### Verification Results
- **SQL Join Check (`CIR-994821` active row where `VALID_TO_TS IS NULL`)**:
  - Verified tuple: `('CUST-ENT-409', 'A Corporate Enterprise', 'CIR-994821', 'ETH-10G-GOLD', '10', 10, 'Gbps', 'NLD-HAG-PE02', 'OLT04-P12', 'CPE-ASN-7741', 'NOK-7210-SAS-Mxp')`
  - Table row counts: `T_OSS_CUST_PARTY` (15), `T_CMDB_CFS_CIRCUIT` (32), `T_CMDB_RFS_RESOURCE` (32), `T_BILLING_AUDIT_NOISE` (25).
- **Excel Verification (`B2B_Enterprise_SLA_Matrix`)**:
  - Verified Row 7 (`ETH-10G-GOLD`): `Max_Packet_Loss_Pct = 0.1%`, `Eligible_Upgrade_SKU = 'ETH-100G-PLATINUM'`, `Auto_Remediation_Allowed = 'YES'`.
- **PDF & SOP Verification**:
  - `Vendor_Optical_Hardware_Manual_v4.pdf`: 5 pages generated with Chapter 4 table and prose for `NOK-7210-SAS-Mxp` (`-14.0 to -24.9 dBm` normal, `-25.0 to -27.5 dBm` DDM recalibration window, `< -27.5 dBm` critical LOS cutoff).
  - `MSA_Contract_A_Corporate_Enterprise_2026.pdf`: 4 pages generated with Clauses 1–7, Annex A, and Annex B.
  - `SOP_NOC_Master_Assurance_Runbook_v2026.docx` & `.md`: 6 sections generated with Section 5 (`SOP-ASSUR-402`) detailing the 4-step workflow and deterministic Branches A, B, and C.

