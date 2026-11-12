"""
Stage 0 (Activity 0.2) Raw Telecom Data Sources Generator & Verifier (`UC-001`).

Generates realistic, wide, noise-rich enterprise data artifacts across:
  1. Prong 1: Relational SQLite CMDB + SQL DDL/DML Dump (4 tables, 104 total rows)
  2. Prong 2: Multi-Tab Excel Product & SLA Catalog (3 tabs, merged banners, 50 SKUs)
  3. Prong 3: Two Multi-Chapter Unstructured PDFs (5-page Hardware Manual + 4-page MSA Contract)
  4. Multi-Procedure NOC SOP Master Runbook (.docx and .md with 6 sections / 5 SOPs)
  5. Stage 0 Artifact Manifest & Updated UCDIL / Observation Notepad (STAGE0_ARTIFACT_MANIFEST.md)
"""

from __future__ import annotations

import logging
import random
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from docx import Document
from docx.shared import RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.config import get_workspace_root
from src.models import (
    AppConfig,
    ExcelArtifactResult,
    ExcelTabCounts,
    PdfArtifactResult,
    SopArtifactResult,
    SqlArtifactResult,
    SqlTableCounts,
    Stage0GenerationSummary,
)


# ============================================================================
# 1. PRONG 1 — WIDE RELATIONAL SQL CMDB
# ============================================================================
def generate_sql_cmdb(
    base_dir: Path, config: AppConfig, logger: logging.Logger
) -> SqlArtifactResult:
    """
    Create the 4-table SQLite CMDB database (`cmdb_installed_base.db`) and export
    its full SQL DDL/DML dump (`cmdb_dump.sql`).
    """
    random.seed(config.stage0.seed)
    sql_dir = base_dir / Path(config.paths.sql_subdir)
    sql_dir.mkdir(parents=True, exist_ok=True)

    db_path = sql_dir / config.stage0.sql_db_filename
    dump_path = sql_dir / config.stage0.sql_dump_filename

    if db_path.exists():
        db_path.unlink()

    logger.info("Creating Prong 1 SQLite CMDB at %s", db_path)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 1. Table T_OSS_CUST_PARTY (7 columns)
    cur.execute(
        """
        CREATE TABLE T_OSS_CUST_PARTY (
            PARTY_SURR_ID INTEGER PRIMARY KEY,
            CUST_EXT_REF TEXT NOT NULL UNIQUE,
            LEGAL_NAME TEXT NOT NULL,
            SEGMENT_CD TEXT NOT NULL,
            ACCT_MGR_ID TEXT,
            LEGACY_CRM_ID TEXT,
            CREATED_TS TEXT NOT NULL
        );
        """
    )

    # 2. Table T_CMDB_CFS_CIRCUIT (11 columns)
    cur.execute(
        """
        CREATE TABLE T_CMDB_CFS_CIRCUIT (
            CFS_ROW_ID INTEGER PRIMARY KEY,
            CIRCUIT_ID TEXT NOT NULL,
            CUST_REF_ID TEXT,
            PROD_SPEC_CODE TEXT NOT NULL,
            OPER_STATUS_CD TEXT NOT NULL,
            BW_VAL NUMERIC NOT NULL,
            BW_UNIT_CD TEXT NOT NULL,
            INSTALL_DT TEXT NOT NULL,
            VALID_FROM_TS TEXT NOT NULL,
            VALID_TO_TS TEXT,
            LEGACY_BILL_TAG TEXT,
            FOREIGN KEY (CUST_REF_ID) REFERENCES T_OSS_CUST_PARTY(CUST_EXT_REF)
        );
        """
    )

    # 3. Table T_CMDB_RFS_RESOURCE (9 columns)
    cur.execute(
        """
        CREATE TABLE T_CMDB_RFS_RESOURCE (
            RFS_ID TEXT PRIMARY KEY,
            PARENT_CFS_ID TEXT,
            PE_ROUTER_HOSTNAME TEXT NOT NULL,
            OLT_PORT_ID TEXT NOT NULL,
            CPE_ASSET_ID TEXT,
            CPE_MODEL_SKU TEXT NOT NULL,
            VLAN_TAG INTEGER,
            FIBER_SPAN_ID TEXT NOT NULL,
            LAST_SYNC_UTC TEXT NOT NULL
        );
        """
    )

    # 4. Table T_BILLING_AUDIT_NOISE (10 columns - unrelated table for schema pruning)
    cur.execute(
        """
        CREATE TABLE T_BILLING_AUDIT_NOISE (
            INV_ID TEXT PRIMARY KEY,
            CUST_REF_ID TEXT,
            BILL_CYCLE_CD TEXT NOT NULL,
            GROSS_AMT_EUR NUMERIC NOT NULL,
            TAX_CD TEXT NOT NULL,
            VAT_PCT NUMERIC NOT NULL,
            GL_POST_DT TEXT NOT NULL,
            DUNNING_LVL INTEGER NOT NULL,
            ERP_BATCH_REF TEXT,
            AUDIT_HASH TEXT NOT NULL
        );
        """
    )

    s0 = config.stage0
    customers = [
        (1001, "CUST-ENT-401", "Delta Marine Logistics N.V.", "ENT_VIP", "AM-NL-01", "SIEBEL-88101", "2021-03-14T09:15:00Z"),
        (1002, "CUST-SMB-102", "Bakkerij Van Der Berg B.V.", "SMB", "AM-NL-04", "SIEBEL-88102", "2022-07-01T11:20:00Z"),
        (1003, "CUST-RES-883", "J. de Vries Holding", "RES", None, "LEGACY-R-993", "2020-11-05T14:00:00Z"),
        (1004, "CUST-GOV-204", "Ministerie van Infrastructuur Waterstaat", "GOV", "AM-GOV-01", "SIEBEL-77004", "2019-01-10T08:00:00Z"),
        (1005, "CUST-ENT-405", "NorthSea Energy Trading B.V.", "ENT_VIP", "AM-NL-02", "SIEBEL-88105", "2021-09-22T16:45:00Z"),
        (1006, "CUST-SMB-106", "Rotterdam Port Customs Brokers", "SMB", "AM-NL-04", None, "2023-02-18T10:30:00Z"),
        (1007, "CUST-ENT-407", "EuroFin Clearing House N.V.", "ENT_VIP", "AM-NL-01", "SIEBEL-88107", "2020-05-12T12:00:00Z"),
        (1008, "CUST-RES-888", "K. Janssen Particulier", "RES", None, None, "2023-08-30T19:10:00Z"),
        # TARGET CUSTOMER FOR UC-001 (Row 9)
        (1009, s0.target_customer_id, s0.target_customer_legal_name, "ENT_VIP", "AM-NL-01", "SIEBEL-88409", "2021-04-01T08:30:00Z"),
        (1010, "CUST-GOV-210", "Gemeente Utrecht Stadsnetwerk", "GOV", "AM-GOV-02", "SIEBEL-77010", "2018-06-15T07:45:00Z"),
        (1011, "CUST-SMB-111", "TechHub Eindhoven Coworking B.V.", "SMB", "AM-NL-05", "SIEBEL-88111", "2022-10-03T13:15:00Z"),
        (1012, "CUST-ENT-412", "Benelux Pharma ColdChain B.V.", "ENT_VIP", "AM-NL-02", "SIEBEL-88112", "2021-12-01T09:00:00Z"),
        (1013, "CUST-RES-893", "P. Bakker Residentieel", "RES", None, "LEGACY-R-998", "2024-01-20T17:25:00Z"),
        (1014, "CUST-SMB-114", "Schiphol AirCargo Express B.V.", "SMB", "AM-NL-03", "SIEBEL-88114", "2022-04-11T15:50:00Z"),
        (1015, "CUST-ENT-415", "Randstad Cloud Datacenters N.V.", "ENT_VIP", "AM-NL-01", "SIEBEL-88115", "2020-08-19T10:05:00Z"),
    ]
    cur.executemany(
        "INSERT INTO T_OSS_CUST_PARTY VALUES (?, ?, ?, ?, ?, ?, ?);",
        customers,
    )

    cfs_rows = [
        # Historical SCD Type 2 superseded row for target circuit CIR-994821
        (
            2000,
            s0.target_circuit_id,
            s0.target_customer_id,
            "ETH-1G-SILVER",
            "10",
            1000,
            "Mbps",
            "2023-01-15",
            "2023-01-15T00:00:00Z",
            "2025-06-01T00:00:00Z",
            "BILL-TAG-409-OLD",
        ),
        # ACTIVE TARGET ROW FOR UC-001 (Valid_To_TS is NULL, OPER_STATUS_CD='10'=Active)
        (
            2001,
            s0.target_circuit_id,
            s0.target_customer_id,
            s0.target_product_sku,
            "10",
            10,
            "Gbps",
            "2023-01-15",
            "2025-06-01T00:00:00Z",
            None,
            "BILL-TAG-409-GOLD",
        ),
        (2002, "CIR-994822", s0.target_customer_id, "ETH-1G-SILVER", "10", 1000, "Mbps", "2023-03-10", "2023-03-10T00:00:00Z", None, "BILL-TAG-409-RTM"),
        (2003, "CIR-994823", s0.target_customer_id, "MPLS-VPN-STD", "10", 500000, "Kbps", "2022-11-01", "2022-11-01T00:00:00Z", None, "BILL-TAG-409-UTR"),
        (2004, "CIR-994824", s0.target_customer_id, "SDWAN-PRO", "20", 250, "Mbps", "2024-02-20", "2024-02-20T00:00:00Z", None, "BILL-TAG-409-EIN"),
        (2005, "CIR-994825", s0.target_customer_id, s0.target_product_sku, "99", 10, "Gbps", "2021-05-01", "2021-05-01T00:00:00Z", "2024-01-01T00:00:00Z", None),
    ]

    distractor_specs = [
        ("ETH-1G-SILVER", 1000, "Mbps"),
        ("ETH-10G-GOLD", 10, "Gbps"),
        ("ETH-100G-PLATINUM", 100, "Gbps"),
        ("MPLS-VPN-STD", 500000, "Kbps"),
        ("SDWAN-PRO", 500, "Mbps"),
        ("FTTH-RES-1G", 1000000, "Kbps"),
        ("5G-SLICE-URLLC", 2, "Gbps"),
        ("DARK-FIBER-METRO", 40, "Gbps"),
        ("WAVELENGTH-10G", 10000, "Mbps"),
    ]
    cust_ids = [c[1] for c in customers if c[1] != s0.target_customer_id]
    status_codes = ["10", "10", "10", "20", "99"]

    for idx in range(1, 27):
        row_id = 2005 + idx
        c_type = random.choice(["CIR", "MPLS", "FTTH", "5GS"])
        circuit_id = f"{c_type}-{800100 + idx}"
        cust_ref = random.choice(cust_ids) if idx % 9 != 0 else None
        spec, bw_val, bw_unit = distractor_specs[idx % len(distractor_specs)]
        oper_status = status_codes[idx % len(status_codes)]
        install_dt = f"202{idx % 5}-0{(idx % 8) + 1}-1{(idx % 9)}"
        valid_from = f"{install_dt}T00:00:00Z"
        valid_to = "2025-12-31T23:59:59Z" if oper_status == "99" else None
        bill_tag = f"BL-LEGACY-{idx:03d}" if idx % 4 != 0 else None
        cfs_rows.append(
            (row_id, circuit_id, cust_ref, spec, oper_status, bw_val, bw_unit, install_dt, valid_from, valid_to, bill_tag)
        )

    cur.executemany(
        "INSERT INTO T_CMDB_CFS_CIRCUIT VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        cfs_rows,
    )

    rfs_rows = [
        # TARGET RESOURCE ROW FOR UC-001
        (
            s0.target_rfs_id,
            s0.target_circuit_id,
            s0.target_pe_router,
            s0.target_olt_port,
            s0.target_cpe_asset_id,
            s0.target_cpe_model_sku,
            2409,
            "FBR-HAG-RING02-S14",
            "2026-11-11T16:00:00Z",
        ),
        (
            "RFS-OLT02-P08",
            "CIR-994822",
            "NLD-RTM-PE01",
            "OLT02-P08",
            "CPE-ASN-7742",
            "CISCO-ASR-920-10G",
            2410,
            "FBR-RTM-METRO-S03",
            "2026-11-11T15:55:00Z",
        ),
        (
            "RFS-OLT07-P03",
            "CIR-994823",
            "NLD-UTR-PE04",
            "OLT07-P03",
            "CPE-ASN-7743",
            "JUNIPER-ACX-10G",
            2411,
            "FBR-UTR-CORE-S09",
            "2026-11-11T15:50:00Z",
        ),
    ]

    pe_routers = ["NLD-AMS-PE01", "NLD-AMS-PE02", "NLD-RTM-PE01", "NLD-HAG-PE01", "NLD-HAG-PE02", "NLD-EIN-PE03", "NLD-UTR-PE04"]
    cpe_models = [
        "CISCO-ASR-920-10G",
        "JUNIPER-ACX-10G",
        "HUAWEI-ATN-910C",
        "NOK-7210-SAS-Mxp",
        "CISCO-ISR-4431",
        "JUNIPER-MX204-OPT",
        "HUAWEI-MA5800-X7",
    ]

    other_circuits = [r[1] for r in cfs_rows[4:]]
    for idx in range(1, 30):
        rfs_id = f"RFS-OLT{(idx % 12) + 1:02d}-P{(idx % 24) + 1:02d}-{idx:02d}"
        parent_cfs = other_circuits[idx % len(other_circuits)] if idx % 10 != 0 else None
        pe_host = pe_routers[idx % len(pe_routers)]
        olt_port = f"OLT{(idx % 12) + 1:02d}-P{(idx % 24) + 1:02d}"
        cpe_asset = f"CPE-ASN-{8100 + idx}" if idx % 8 != 0 else None
        cpe_sku = cpe_models[idx % len(cpe_models)]
        vlan = 1000 + (idx * 17) % 2900
        fiber_span = f"FBR-NL-SPAN-{300 + idx}"
        sync_ts = f"2026-11-11T15:{(idx * 2) % 60:02d}:00Z"
        rfs_rows.append((rfs_id, parent_cfs, pe_host, olt_port, cpe_asset, cpe_sku, vlan, fiber_span, sync_ts))

    cur.executemany(
        "INSERT INTO T_CMDB_RFS_RESOURCE VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
        rfs_rows,
    )

    billing_rows = []
    for idx in range(1, 26):
        inv_id = f"INV-2026-{90000 + idx}"
        cust_ref = customers[idx % len(customers)][1]
        cycle_cd = random.choice(["M01", "M15", "Q01"])
        gross_amt = round(random.uniform(150.0, 18500.0), 2)
        tax_cd = random.choice(["NL_VAT_21", "EU_REV_0", "EXEMPT_GOV"])
        vat_pct = 21.0 if tax_cd == "NL_VAT_21" else 0.0
        post_dt = f"2026-10-{(idx % 28) + 1:02d}"
        dunning = 0 if idx % 6 != 0 else random.choice([1, 2, 3])
        batch_ref = f"SAP-B-{7700 + idx}" if idx % 5 != 0 else None
        audit_hash = f"sha256:{idx:04x}99a8b7c6d5e4f3a2b1"
        billing_rows.append((inv_id, cust_ref, cycle_cd, gross_amt, tax_cd, vat_pct, post_dt, dunning, batch_ref, audit_hash))

    cur.executemany(
        "INSERT INTO T_BILLING_AUDIT_NOISE VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        billing_rows,
    )

    conn.commit()

    logger.info("Exporting SQL DDL/DML dump to %s", dump_path)
    with open(dump_path, "w", encoding="utf-8") as f:
        f.write("-- Stage 0 (Activity 0.2) Frozen SQL CMDB Dump for Use Case UC-001\n")
        f.write("-- Generated deterministically by src/stage0_generator.py\n\n")
        for line in conn.iterdump():
            f.write(f"{line}\n")

    conn.close()

    return SqlArtifactResult(
        db_path=db_path,
        dump_path=dump_path,
        table_counts=SqlTableCounts(
            T_OSS_CUST_PARTY=len(customers),
            T_CMDB_CFS_CIRCUIT=len(cfs_rows),
            T_CMDB_RFS_RESOURCE=len(rfs_rows),
            T_BILLING_AUDIT_NOISE=len(billing_rows),
        ),
    )


# ============================================================================
# 2. PRONG 2 — MULTI-TAB EXCEL WORKBOOK
# ============================================================================
def _style_worksheet_banner_and_headers(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    title: str,
    subtitle: str,
    headers: List[str],
    banner_color: str = "1F4E78",
) -> None:
    """Format rows 1-3 as a merged banner, row 4 as an empty separator, and row 5 as headers."""
    num_cols = len(headers)
    last_col_letter = get_column_letter(num_cols)

    ws.merge_cells(f"A1:{last_col_letter}3")
    banner_cell = ws["A1"]
    banner_cell.value = f"{title}\n{subtitle}\nCONFIDENTIAL — INTERNAL PRODUCT MANAGEMENT & NOC ENGINEERING USE ONLY"
    banner_cell.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    banner_cell.fill = PatternFill(start_color=banner_color, end_color=banner_color, fill_type="solid")
    banner_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.row_dimensions[4].height = 14

    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_font = Font(name="Calibri", size=10, bold=True, color="000000")
    thin_border = Border(
        left=Side(style="thin", color="8EA9DB"),
        right=Side(style="thin", color="8EA9DB"),
        top=Side(style="thin", color="8EA9DB"),
        bottom=Side(style="medium", color="1F4E78"),
    )

    ws.row_dimensions[5].height = 24
    for col_idx, h_text in enumerate(headers, start=1):
        c = ws.cell(row=5, column=col_idx, value=h_text)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(h_text) + 5, 16)


def generate_excel_catalog(
    base_dir: Path, config: AppConfig, logger: logging.Logger
) -> ExcelArtifactResult:
    """
    Create the 3-tab Excel SLA workbook (`Telco_Master_Product_SLA_Catalog_2026.xlsx`)
    with merged banner rows 1-3, empty row 4, headers in row 5, and 50 total SKUs.
    """
    excel_dir = base_dir / Path(config.paths.excel_subdir)
    excel_dir.mkdir(parents=True, exist_ok=True)
    excel_path = excel_dir / config.stage0.excel_catalog_filename

    logger.info("Creating Prong 2 Multi-Tab Excel Catalog at %s", excel_path)
    wb = openpyxl.Workbook()

    # Tab 1: Residential_FTTH_Plans (15 rows - Distractor Tab)
    ws_res = wb.active
    ws_res.title = "Residential_FTTH_Plans"
    res_headers = [
        "Plan_SKU",
        "Consumer_Plan_Name",
        "Access_Tech",
        "Downstream_Mbps",
        "Upstream_Mbps",
        "Contention_Ratio",
        "WiFi_CPE_Bundle",
        "Best_Effort_SLA",
        "Monthly_Price_EUR",
        "Promo_Discount_EUR",
        "Finance_GL_Account",
        "Lifecycle_State",
    ]
    _style_worksheet_banner_and_headers(
        ws_res,
        "TELCO CONSUMER BROADBAND & FTTH PRODUCT CATALOG (FY2026)",
        "Tab 1: Residential GPON / XGS-PON Consumer Plans — Excluded from B2B Enterprise Assurance",
        res_headers,
        banner_color="2F5597",
    )

    for i in range(1, 16):
        down_bw = [100, 200, 400, 500, 1000, 2000, 4000, 8000][i % 8]
        up_bw = down_bw if i % 2 == 0 else down_bw // 2
        tech = "XGS-PON" if down_bw >= 2000 else "GPON"
        row_vals = [
            f"RES-FTTH-{down_bw}M-{i:02d}",
            f"HomeFiber {down_bw} Mbps {'Symmetrical' if up_bw == down_bw else 'Standard'} #{i}",
            tech,
            down_bw,
            up_bw,
            "1:32" if tech == "GPON" else "1:16",
            "WiFi-6E HomeBox v3",
            "Best-Effort (No Packet Loss SLA)",
            round(34.95 + (i * 3.5), 2),
            5.00 if i % 3 == 0 else 0.00,
            f"GL-RES-41{i:02d}",
            "ACTIVE",
        ]
        ws_res.append(row_vals)

    # Tab 2: B2B_Enterprise_SLA_Matrix (20 rows, 14 columns - TARGET TAB)
    s0 = config.stage0
    ws_b2b = wb.create_sheet(title="B2B_Enterprise_SLA_Matrix")
    b2b_headers = [
        "Product_SKU_Code",
        "Marketing_Name",
        "Service_Category",
        "Max_Packet_Loss_Pct",
        "Max_Jitter_ms",
        "MTTR_Target_Hours",
        "Eligible_Upgrade_SKU",
        "Auto_Remediation_Allowed",
        "Monthly_List_Price_EUR",
        "Internal_Finance_GL_Code",
        "Shadow_Lifecycle_Flag",
        "Min_Contract_Months",
        "SLA_Credit_Cap_Pct",
        "Engineering_Notes",
    ]
    _style_worksheet_banner_and_headers(
        ws_b2b,
        "TELCO B2B ENTERPRISE CONNECTIVITY & SLA THRESHOLD MATRIX (FY2026)",
        "Tab 2: Authoritative Enterprise SLA Tiers, Packet-Loss Bounds & Autonomous Remediation Rules",
        b2b_headers,
        banner_color="1F4E78",
    )

    b2b_rows = [
        ["ETH-1G-SILVER", "Enterprise Carrier Ethernet 1G Silver", "L2_CARRIER_ETHERNET", 0.25, 5.0, 8, s0.target_product_sku, "YES", 850.00, "GL-B2B-5001", "10_PROD", 24, 10.0, "Standard MEF E-Line 1G over SFP"],
        # Row 7 (Item 2 — TARGET SKU FOR UC-001: ETH-10G-GOLD)
        [s0.target_product_sku, "Enterprise Carrier Ethernet 10G Gold", "L2_CARRIER_ETHERNET", 0.1, 2.0, 4, s0.target_upgrade_sku, "YES", 2450.00, "GL-B2B-5002", "10_PROD", 36, 15.0, "VIP 10GBASE-LR 1310nm; DDM recalibration pre-authorized if Rx in [-25.0, -27.5 dBm]"],
        [s0.target_upgrade_sku, "Enterprise Carrier Ethernet 100G Platinum", "L2_CARRIER_ETHERNET", 0.01, 0.5, 2, "ETH-400G-ULTRA", "YES", 7900.00, "GL-B2B-5003", "10_PROD", 36, 25.0, "Dual-homed 100GBASE-LR4 mission-critical core trunk"],
        ["ETH-400G-ULTRA", "HyperScale Metro Ethernet 400G Ultra", "L2_CARRIER_ETHERNET", 0.005, 0.2, 2, "NONE", "NO", 18500.00, "GL-B2B-5004", "10_PROD", 60, 30.0, "Manual NOC optical engineering supervision required"],
        ["MPLS-VPN-STD", "Corporate IP-VPN MPLS Standard", "L3_IP_MPLS", 0.5, 10.0, 12, "MPLS-VPN-PREM", "NO", 620.00, "GL-B2B-5101", "10_PROD", 24, 10.0, "Best-effort L3 VPN class CoS-3"],
        ["MPLS-VPN-PREM", "Corporate IP-VPN MPLS Premium Voice/Video", "L3_IP_MPLS", 0.1, 3.0, 4, "SDWAN-PRO", "YES", 1350.00, "GL-B2B-5102", "10_PROD", 36, 15.0, "Strict EF queuing for real-time traffic"],
        ["SDWAN-PRO", "Managed Enterprise SD-WAN Pro Dual-Underlay", "MANAGED_SDWAN", 0.2, 8.0, 6, "SDWAN-ENTERPRISE-AI", "YES", 980.00, "GL-B2B-5201", "10_PROD", 24, 12.0, "Dynamic path steering over DIA + LTE/5G"],
        ["SDWAN-ENTERPRISE-AI", "Managed Enterprise SD-WAN AI-Assured", "MANAGED_SDWAN", 0.05, 2.5, 4, "NONE", "YES", 1690.00, "GL-B2B-5202", "10_PROD", 36, 20.0, "Automated FEC and dual-tunnel duplication"],
        ["DIA-1G-BIZ", "Dedicated Internet Access 1G Business", "L3_DIA", 0.3, 6.0, 8, "DIA-10G-BIZ", "NO", 790.00, "GL-B2B-5301", "10_PROD", 12, 10.0, "Uncontended 1:1 BGP/Static DIA"],
        ["DIA-10G-BIZ", "Dedicated Internet Access 10G Enterprise", "L3_DIA", 0.1, 2.5, 4, "DIA-100G-CORE", "YES", 2150.00, "GL-B2B-5302", "10_PROD", 24, 15.0, "DDoS Clean-Pipe scrubbing included"],
        ["DIA-100G-CORE", "Dedicated Internet Access 100G Carrier", "L3_DIA", 0.02, 1.0, 2, "NONE", "NO", 6800.00, "GL-B2B-5303", "10_PROD", 36, 20.0, "Direct peering handoff"],
        ["WAVELENGTH-10G-METRO", "DWDM Optical Wavelength 10G Metro", "L1_OPTICAL", 0.001, 0.1, 4, "WAVELENGTH-100G-METRO", "NO", 3100.00, "GL-B2B-5401", "10_PROD", 36, 20.0, "Transparent OTU2 optical lambda"],
        ["WAVELENGTH-100G-METRO", "DWDM Optical Wavelength 100G Metro", "L1_OPTICAL", 0.001, 0.05, 2, "NONE", "NO", 8400.00, "GL-B2B-5402", "10_PROD", 60, 25.0, "Coherent OTU4 wavelength"],
        ["5G-SLICE-URLLC", "Enterprise Private 5G Network Slice URLLC", "5G_NETWORK_SLICE", 0.05, 1.5, 4, "NONE", "YES", 2900.00, "GL-B2B-5501", "10_PROD", 24, 15.0, "Ultra-reliable low-latency campus slice"],
        ["5G-SLICE-EMBB", "Enterprise 5G Fixed Wireless Backup eMBB", "5G_NETWORK_SLICE", 0.5, 15.0, 12, "5G-SLICE-URLLC", "YES", 450.00, "GL-B2B-5502", "10_PROD", 12, 5.0, "Secondary backup wireless link"],
        ["GOV-SEC-ETH-10G", "Government Defense Encrypted 10G Ethernet", "L2_CARRIER_ETHERNET", 0.05, 1.0, 2, s0.target_upgrade_sku, "NO", 4200.00, "GL-GOV-5601", "10_PROD", 60, 25.0, "MACsec AES-256 hardware encryption mandatory"],
        ["CLOUD-CONNECT-10G", "Direct Cloud Express Interconnect 10G", "L2_CLOUD_FABRIC", 0.1, 2.0, 4, s0.target_upgrade_sku, "YES", 1950.00, "GL-B2B-5701", "10_PROD", 24, 15.0, "Dedicated VLAN handoff to AMS-IX cloud peering"],
        ["ETH-2.5G-MID", "Enterprise Carrier Ethernet 2.5G Mid-Tier", "L2_CARRIER_ETHERNET", 0.2, 4.0, 6, s0.target_product_sku, "YES", 1250.00, "GL-B2B-5009", "20_PILOT", 24, 10.0, "Sub-rate 10G port policed to 2.5 Gbps"],
        # Deliberate dirty rows for Track B pySHACL quarantine verification
        ["DARK-FIBER-METRO-X", "Unlit Metro Dark Fiber Pair (Dirty Row Test)", "L0_DARK_FIBER", -0.5, 0.0, 24, "WAVELENGTH-10G-METRO", "MAYBE_LEGACY", 1500.00, "GL-ERR-9901", "99_INVALID", 36, 10.0, "DIRTY DATA TEST: Negative packet loss & invalid enum for pySHACL quarantine"],
        ["SDWAN-LEGACY-99", "Unmigrated Legacy Velo Box (Dirty Row Test)", "MANAGED_SDWAN", 125.0, -5.0, None, "SDWAN-PRO", "UNKNOWN", -100.00, "GL-ERR-9902", "99_OBS_SHADOW", 12, 0.0, "DIRTY DATA TEST: Loss > 100% and NULL MTTR for pySHACL quarantine"],
    ]

    for r in b2b_rows:
        ws_b2b.append(r)

    # Tab 3: Deprecated_Legacy_SKUs (15 rows - Distractor Tab)
    ws_dep = wb.create_sheet(title="Deprecated_Legacy_SKUs")
    dep_headers = [
        "Legacy_SKU_ID",
        "Legacy_Product_Name",
        "Obsolete_Tech_Type",
        "Nominal_Rate_Kbps",
        "End_Of_Sale_Date",
        "End_Of_Support_Date",
        "Replacement_Target_SKU",
        "Shadow_Archive_Code",
        "Historical_GL_Code",
        "Decommission_Notes",
    ]
    _style_worksheet_banner_and_headers(
        ws_dep,
        "DEPRECATED & END-OF-LIFE TELECOM PRODUCT ARCHIVE (DO NOT PROVISION)",
        "Tab 3: Legacy ATM, Frame-Relay, ISDN & PDH E1/T1 Services — Excluded from Active Catalog",
        dep_headers,
        banner_color="7B2C2C",
    )

    legacy_techs = ["ATM_PVC", "FRAME_RELAY", "ISDN_PRI_30B", "PDH_E1_2M", "SDH_STM1_155M"]
    for i in range(1, 16):
        t_type = legacy_techs[i % len(legacy_techs)]
        ws_dep.append(
            [
                f"OBS-{t_type[:4]}-{1998 + (i % 10)}-{i:02d}",
                f"Legacy {t_type.replace('_', ' ')} Corporate Circuit #{i}",
                t_type,
                64 * (2 ** (i % 6)),
                f"201{(i % 6) + 2}-12-31",
                f"202{(i % 4) + 1}-06-30",
                "ETH-1G-SILVER" if i % 2 == 0 else "MPLS-VPN-STD",
                "99_DECOMMISSIONED",
                f"GL-OLD-19{i:02d}",
                "Historical billing reference only; physical TDM switch retired.",
            ]
        )

    wb.save(str(excel_path))

    return ExcelArtifactResult(
        excel_path=excel_path,
        tab_counts=ExcelTabCounts(
            Residential_FTTH_Plans=15,
            B2B_Enterprise_SLA_Matrix=len(b2b_rows),
            Deprecated_Legacy_SKUs=15,
        ),
    )


# ============================================================================
# 3. PRONG 3 — TWO MULTI-CHAPTER UNSTRUCTURED PDFs
# ============================================================================
def _build_pdf_styles():
    """Build custom ReportLab paragraph styles for engineering & legal PDFs."""
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DocTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1F4E78"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#44546A"),
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ChapterHeader",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1F4E78"),
            spaceBefore=8,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyJustified",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CalloutBox",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13.5,
            backColor=colors.HexColor("#EDF2F8"),
            borderColor=colors.HexColor("#1F4E78"),
            borderWidth=1,
            borderPadding=6,
            spaceBefore=6,
            spaceAfter=10,
        )
    )
    return styles


def generate_pdfs(
    base_dir: Path, config: AppConfig, logger: logging.Logger
) -> PdfArtifactResult:
    """
    Create the 5-page `Vendor_Optical_Hardware_Manual_v4.pdf` and 4-page
    `MSA_Contract_A_Corporate_Enterprise_2026.pdf` unstructured PDF files.
    """
    pdf_dir = base_dir / Path(config.paths.pdf_subdir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    styles = _build_pdf_styles()
    s0 = config.stage0

    # PDF 1: Vendor_Optical_Hardware_Manual_v4.pdf (5 pages)
    hw_pdf_path = pdf_dir / s0.hw_manual_pdf_filename
    logger.info("Creating Prong 3A Hardware Manual PDF at %s", hw_pdf_path)
    hw_doc = SimpleDocTemplate(
        str(hw_pdf_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Multi-Vendor Carrier Ethernet & Optical CPE Hardware Engineering Reference Manual v4.0",
        author="Telco Transport Engineering Standards Group",
    )

    hw_story = []

    # PAGE 1: Chapter 1
    hw_story.append(Paragraph("MULTI-VENDOR CARRIER ETHERNET & OPTICAL CPE HARDWARE MANUAL (REV 4.0)", styles["DocTitle"]))
    hw_story.append(
        Paragraph(
            f"Document ID: ENG-HW-OPT-MAN-V4 | Scope: Cisco ASR-920, Juniper ACX2100, and Nokia 7210 SAS-Mxp ({s0.target_cpe_model_sku}) Platforms",
            styles["DocSubTitle"],
        )
    )
    hw_story.append(Paragraph("Chapter 1: General Safety, Rack Mounting & Power Supply Specifications", styles["ChapterHeader"]))
    hw_story.append(
        Paragraph(
            "1.1 Purpose and Scope: This engineering manual defines the physical installation, electrical power, thermal management, "
            "copper interface, and optical SFP+/XFP transceiver operating parameters for enterprise demarcation and access aggregation routers "
            "deployed across the national Carrier Ethernet footprint. All field technicians and automated NOC assurance systems must adhere "
            "strictly to the hardware tolerances specified herein.",
            styles["BodyJustified"],
        )
    )
    hw_story.append(
        Paragraph(
            "1.2 Laser Safety Compliance (IEC 60825-1 Class 1): Optical transceivers deployed in access and metro chassis emit invisible "
            "infrared laser radiation at 850 nm, 1310 nm, or 1550 nm wavelengths. Never inspect open fiber patch cords or LC/UPC bulkhead "
            "adapters without an approved optical power meter and attenuation filter.",
            styles["BodyJustified"],
        )
    )
    hw_story.append(
        Paragraph(
            "1.3 Chassis Rack Mounting & Grounding: All CPE and aggregation shelves must be mounted in standard EIA-310 19-inch two-post "
            "or four-post telecom racks using dual M6 lug earthing straps bonded to the central station ground bus (< 1.0 Ohm resistance).",
            styles["BodyJustified"],
        )
    )
    psu_table_data = [
        ["Chassis Platform SKU", "Form Factor", "Redundant PSU Input", "Max Power Draw", "Chassis Ground Lug"],
        ["CISCO-ASR-920-10G", "1 RU Fixed", "-48V DC Dual Feed / 110-240V AC", "145 W", "Dual M6 Ring Terminal"],
        ["JUNIPER-ACX-10G", "1 RU Hardened", "-48V DC Dual Feed", "160 W", "Dual M6 Ring Terminal"],
        [s0.target_cpe_model_sku, "1.5 RU Extended", "-48V DC / +24V DC Modular", "185 W", "Dual M6 Ring Terminal"],
    ]
    t_psu = Table(psu_table_data, colWidths=[38 * mm, 26 * mm, 48 * mm, 28 * mm, 34 * mm])
    t_psu.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8EA9DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    hw_story.append(Spacer(1, 4 * mm))
    hw_story.append(t_psu)
    hw_story.append(PageBreak())

    # PAGE 2: Chapter 2
    hw_story.append(Paragraph("Chapter 2: Environmental, Thermal & Fan Tray Thresholds", styles["ChapterHeader"]))
    hw_story.append(
        Paragraph(
            "2.1 Ambient Operating Temperature & Humidity: Enterprise demarcation units installed in unconditioned street cabinets or "
            "customer basement MDF rooms must support extended industrial temperature envelopes (-40C to +65C for passive cooled variants; "
            "-5C to +55C for fan-cooled optical shelves) at 5% to 95% non-condensing relative humidity.",
            styles["BodyJustified"],
        )
    )
    hw_story.append(
        Paragraph(
            "2.2 Fan Tray RPM Telemetry & Thermal Shutdown: Each chassis houses hot-swappable PWM fan trays monitored via SNMP ENTITY-SENSOR-MIB "
            "and gNMI /components/component/state/temperature. If exhaust ASIC temperature exceeds +78C, the shelf raises a MINOR thermal alarm "
            "and forces fan speed to 100% duty cycle. Thermal shutdown engages automatically at +92C to prevent silicon damage.",
            styles["BodyJustified"],
        )
    )
    thermal_table = [
        ["Platform SKU", "Normal Intake Temp", "Minor Thermal Alarm", "Critical Shutdown", "Fan Tray FRU SKU"],
        ["CISCO-ASR-920-10G", "0C to +45C", "+72C", "+88C", "ASR-920-FAN-M"],
        ["JUNIPER-ACX-10G", "-20C to +55C", "+78C", "+92C", "ACX2100-PASSIVE"],
        [s0.target_cpe_model_sku, "-5C to +50C", "+75C", "+90C", "3HE09152AA-FAN"],
    ]
    t_therm = Table(thermal_table, colWidths=[38 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm])
    t_therm.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8EA9DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]),
            ]
        )
    )
    hw_story.append(Spacer(1, 4 * mm))
    hw_story.append(t_therm)
    hw_story.append(PageBreak())

    # PAGE 3: Chapter 3
    hw_story.append(
        Paragraph("Chapter 3: Copper RJ-45 & Electrical Interface Specifications (Cisco ASR-920 & Juniper ACX2100)", styles["ChapterHeader"])
    )
    hw_story.append(
        Paragraph(
            "3.1 10/100/1000BASE-T RJ-45 Client Handoff Ports: For legacy sub-1G enterprise LAN handoffs, Cisco ASR-920 and Juniper ACX2100 "
            "chassis provide integrated IEEE 802.3ab auto-negotiating RJ-45 copper ports supporting Cat5e/Cat6 structured cabling up to 100 meters.",
            styles["BodyJustified"],
        )
    )
    hw_story.append(
        Paragraph(
            "3.2 Electrical MDI/MDI-X & TDR Cable Diagnostics: Time Domain Reflectometry (TDR) can be invoked on copper ports ONLY to detect "
            "open/short pair faults. Note: Copper RJ-45 electrical parameters do NOT apply to 10GBASE-LR optical fiber circuits and must be "
            "ignored by optical fiber assurance workflows.",
            styles["BodyJustified"],
        )
    )
    copper_table = [
        ["Platform Model", "Port Range", "Media Standard", "Max Distance", "PoE+ Support", "Auto-MDIX"],
        ["CISCO-ASR-920-10G", "Gi0/0/0 - Gi0/0/11", "1000BASE-T Cat6", "100 m", "No", "Enabled"],
        ["JUNIPER-ACX-10G", "ge-0/0/0 - ge-0/0/15", "1000BASE-T Cat6", "100 m", "802.3at (Ports 0-3)", "Enabled"],
    ]
    t_cop = Table(copper_table, colWidths=[36 * mm, 32 * mm, 32 * mm, 24 * mm, 28 * mm, 22 * mm])
    t_cop.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8EA9DB")),
            ]
        )
    )
    hw_story.append(Spacer(1, 4 * mm))
    hw_story.append(t_cop)
    hw_story.append(PageBreak())

    # PAGE 4: Chapter 4 — TARGET CHAPTER FOR UC-001
    hw_story.append(Paragraph("Chapter 4: Optical SFP+/XFP Transceiver Operating Parameters", styles["ChapterHeader"]))
    hw_story.append(
        Paragraph(
            f"4.1 Multi-Vendor 10GBASE-LR Optical Transceiver Overview: Enterprise 10 Gbps Carrier Ethernet circuits (including service spec "
            f"{s0.target_product_sku}) terminate on 10GBASE-LR (1310 nm single-mode fiber, up to 10 km reach) SFP+/XFP optical transceivers with SFF-8472 "
            "Digital Diagnostics Monitoring (DDM) enabled. Each vendor platform enforces distinct photodiode receive sensitivity windows.",
            styles["BodyJustified"],
        )
    )
    hw_story.append(
        Paragraph(
            f"4.2 Nokia 7210 SAS-Mxp (SKU: {s0.target_cpe_model_sku}) Optical Operating Envelope & DDM Recalibration Rules: "
            f"For physical CPE model SKU {s0.target_cpe_model_sku} equipped with 10GBASE-LR 1310nm optics, the authoritative optical power thresholds are:\n"
            "- Nominal Transmit (Tx) Power: -1.0 dBm\n"
            "- Receiver Overload Cutoff (Max Rx): -1.0 dBm\n"
            "- Normal Operating Rx Power Range: -14.0 dBm to -24.9 dBm (optimal FEC-free window)\n"
            "- Soft Degradation / DDM Recalibration Window: -25.0 dBm to -27.5 dBm (elevated BER/packet loss caused by photodiode AGC bias drift; "
            "eligible for non-intrusive remote TMF640 DDM optical transceiver recalibration)\n"
            "- Critical Loss-of-Signal (LOS) / Hard Attenuation Cutoff: < -27.5 dBm (physical macro-bend, dirty splice, or fiber cut; remote DDM "
            "recalibration is strictly ineffective and forbidden — mandatory TMF621 field fiber technician dispatch required).",
            styles["CalloutBox"],
        )
    )
    opt_table_data = [
        [
            "Hardware Model SKU",
            "Optical Standard",
            "Nominal Tx",
            "Overload Rx",
            "Normal Rx Range",
            "DDM Recalibration Window",
            "Critical LOS Cutoff (Min Rx)",
        ],
        [
            "CISCO-ASR-920-10G",
            "10GBASE-LR 1310nm",
            "-0.5 dBm",
            "-0.5 dBm",
            "-12.0 to -22.9 dBm",
            "-23.0 to -25.5 dBm",
            "< -25.5 dBm",
        ],
        [
            "JUNIPER-ACX-10G",
            "10GBASE-LR 1310nm",
            "-1.0 dBm",
            "-0.5 dBm",
            "-13.0 to -23.9 dBm",
            "-24.0 to -26.5 dBm",
            "< -26.5 dBm",
        ],
        [
            s0.target_cpe_model_sku,
            "10GBASE-LR 1310nm",
            "-1.0 dBm",
            "-1.0 dBm",
            "-14.0 to -24.9 dBm",
            "-25.0 to -27.5 dBm",
            "< -27.5 dBm",
        ],
    ]
    t_opt = Table(opt_table_data, colWidths=[30 * mm, 26 * mm, 18 * mm, 18 * mm, 28 * mm, 28 * mm, 26 * mm])
    t_opt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8EA9DB")),
                ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#FFF2CC")),
                ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    hw_story.append(t_opt)
    hw_story.append(PageBreak())

    # PAGE 5: Chapter 5
    hw_story.append(
        Paragraph("Chapter 5: Transceiver Diagnostics, DDM Polling & Field Fiber Cleaning Procedures", styles["ChapterHeader"])
    )
    hw_story.append(
        Paragraph(
            "5.1 Real-Time Singleton DDM Telemetry Probing: Cached NMS performance graphs poll every 15 minutes and must NEVER be used to authorize "
            "an optical laser/AGC recalibration. Automated assurance agents must invoke a synchronous, non-cached gNMI/REST singleton optical "
            "probe (bypass_cache=true) against the terminating OLT/CPE port prior to issuing any TMF640 service configuration action.",
            styles["BodyJustified"],
        )
    )
    hw_story.append(
        Paragraph(
            f"5.2 Field OTDR Testing & End-Face Inspection: When live optical Rx power falls strictly below -27.5 dBm on a {s0.target_cpe_model_sku} "
            "interface, dispatched field engineers must perform bidirectional OTDR traces at 1310 nm and 1625 nm and inspect LC/UPC ferrules "
            "per IEC 61300-3-35 before replacing the SFP+ module.",
            styles["BodyJustified"],
        )
    )

    hw_doc.build(hw_story)

    # PDF 2: MSA_Contract_A_Corporate_Enterprise_2026.pdf (4 pages)
    msa_pdf_path = pdf_dir / s0.msa_contract_pdf_filename
    logger.info("Creating Prong 3B MSA Contract PDF at %s", msa_pdf_path)
    msa_doc = SimpleDocTemplate(
        str(msa_pdf_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Master Service Agreement - {s0.target_customer_bv_name} (2026)",
        author="Telco Enterprise Legal & Commercial Contracting",
    )

    msa_story = []

    # PAGE 1: Clauses 1-3
    msa_story.append(Paragraph("B2B MASTER TELECOMMUNICATIONS SERVICE AGREEMENT (MSA-2026-NL-409)", styles["DocTitle"]))
    msa_story.append(
        Paragraph(
            f"Effective Date: 01 January 2026 | Legal Counterparty: {s0.target_customer_bv_name} (KvK Registration: {s0.target_customer_kvk})",
            styles["DocSubTitle"],
        )
    )
    msa_story.append(Paragraph("Clause 1: Contracting Parties & Corporate Identity", styles["ChapterHeader"]))
    msa_story.append(
        Paragraph(
            'This Master Telecommunications Service Agreement ("Agreement") is entered into by and between National Telecom Operator B.V. '
            f'("Provider") and "{s0.target_customer_bv_name}", a private limited liability company incorporated under the laws of the Netherlands '
            f"with Chamber of Commerce (KvK) registration number {s0.target_customer_kvk} and headquarters at Beatrixlaan 400, 2595 BM Den Haag "
            f'(tracked in Provider OSS/CMDB systems under customer code {s0.target_customer_id} / "{s0.target_customer_legal_name}").',
            styles["BodyJustified"],
        )
    )
    msa_story.append(Paragraph("Clause 2: Agreement Term & Renewal", styles["ChapterHeader"]))
    msa_story.append(
        Paragraph(
            "This Agreement commences on 01 January 2026 for an initial committed term of thirty-six (36) months and automatically renews "
            "for successive twelve (12) month periods unless terminated with ninety (90) days prior written notice.",
            styles["BodyJustified"],
        )
    )
    msa_story.append(Paragraph("Clause 3: Invoicing, Currency & Disputed Charges", styles["ChapterHeader"]))
    msa_story.append(
        Paragraph(
            "Monthly recurring charges (MRC) for all subscribed Carrier Ethernet and IP-VPN services shall be invoiced in Euros (EUR) "
            "net thirty (30) days via SEPA corporate direct debit.",
            styles["BodyJustified"],
        )
    )
    msa_story.append(PageBreak())

    # PAGE 2: Clauses 4-5
    msa_story.append(Paragraph("Clause 4: Limitation of Corporate Liability & Indemnification", styles["ChapterHeader"]))
    msa_story.append(
        Paragraph(
            "Except for gross negligence or willful misconduct, neither Party's aggregate annual liability under this Agreement shall exceed "
            f"one hundred percent (100%) of the total annual recurring charges paid by {s0.target_customer_bv_name} during the preceding "
            "twelve (12) calendar months. Indirect, consequential, or punitive damages are expressly excluded.",
            styles["BodyJustified"],
        )
    )
    msa_story.append(Paragraph("Clause 5: Force Majeure & Excavations", styles["ChapterHeader"]))
    msa_story.append(
        Paragraph(
            "Neither Party shall be liable for service interruptions caused by catastrophic natural disasters, sovereign grid blackouts, "
            "or third-party municipal civil excavation cuts; provided, however, that Provider dispatches emergency fiber splicing crews "
            "within the contracted MTTR window.",
            styles["BodyJustified"],
        )
    )
    msa_story.append(PageBreak())

    # PAGE 3: Clause 6 (Annex A)
    msa_story.append(Paragraph("Clause 6 (Annex A): Subscribed Enterprise Circuit Schedule", styles["ChapterHeader"]))
    msa_story.append(
        Paragraph(
            f"{s0.target_customer_bv_name} (Registration {s0.target_customer_kvk} / {s0.target_customer_id}) subscribes to the following five (5) active corporate "
            "connectivity circuits across its Netherlands sites:",
            styles["BodyJustified"],
        )
    )
    annex_a_table = [
        ["Site #", "Circuit ID", "Site Location", "Product Spec SKU", "Committed BW", "Terminating CPE SKU", "Monthly Fee"],
        ["Site 1 (HQ)", s0.target_circuit_id, "Den Haag Beatrixlaan 400", s0.target_product_sku, "10 Gbps", s0.target_cpe_model_sku, "EUR 2,450.00"],
        ["Site 2", "CIR-994822", "Rotterdam Waalhaven 12", "ETH-1G-SILVER", "1000 Mbps", "CISCO-ASR-920-10G", "EUR 850.00"],
        ["Site 3", "CIR-994823", "Utrecht Stationsplein 8", "MPLS-VPN-STD", "500 Mbps", "JUNIPER-ACX-10G", "EUR 620.00"],
        ["Site 4", "CIR-994824", "Eindhoven HighTech Campus", "SDWAN-PRO", "250 Mbps", "CISCO-ISR-4431", "EUR 980.00"],
        ["Site 5 (DR)", "CIR-994890", "Amsterdam Science Park 104", s0.target_product_sku, "10 Gbps", s0.target_cpe_model_sku, "EUR 2,450.00"],
    ]
    t_annex_a = Table(annex_a_table, colWidths=[22 * mm, 24 * mm, 38 * mm, 28 * mm, 20 * mm, 28 * mm, 20 * mm])
    t_annex_a.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8EA9DB")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FFF2CC")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ]
        )
    )
    msa_story.append(Spacer(1, 3 * mm))
    msa_story.append(t_annex_a)
    msa_story.append(PageBreak())

    # PAGE 4: Clause 7 (Annex B)
    msa_story.append(
        Paragraph(
            f"Clause 7 (Annex B): Bespoke SLA Penalty & Autonomous Maintenance Rules for Circuit {s0.target_circuit_id}",
            styles["ChapterHeader"],
        )
    )
    msa_story.append(
        Paragraph(
            f"7.1 Enhanced Packet-Loss SLA & 15% Monthly Service Credit Penalty: Notwithstanding standard Gold tier terms, for primary headquarters "
            f"circuit {s0.target_circuit_id} (Product Spec: {s0.target_product_sku}), if frame/packet loss exceeds 0.1% continuously for more than thirty (30) minutes "
            f"during any calendar month, {s0.target_customer_bv_name} shall automatically receive a bespoke Service Level Agreement penalty credit "
            f"equal to fifteen percent (15%) of the Monthly Recurring Charge for circuit {s0.target_circuit_id}.",
            styles["CalloutBox"],
        )
    )
    msa_story.append(
        Paragraph(
            f"7.2 Pre-Authorized Autonomous Optical DDM Recalibration: To prevent packet-loss breaches exceeding the 30-minute SLA penalty window, "
            f"{s0.target_customer_bv_name} expressly grants Provider pre-authorized permission to execute automated, non-intrusive Digital Diagnostics "
            f"Monitoring (DDM) optical transceiver recalibration (via TMF640 Service Activation & Configuration) on circuit {s0.target_circuit_id} and its "
            f"terminating port {s0.target_olt_port} / CPE asset {s0.target_cpe_asset_id} ({s0.target_cpe_model_sku}) whenever live optical Rx power falls within the soft "
            "degradation window (-25.0 dBm to -27.5 dBm), PROVIDED THAT no active customer or network maintenance freeze lock "
            "(maintenance_lock == false) is present on the port.",
            styles["BodyJustified"],
        )
    )
    msa_story.append(
        Paragraph(
            f"7.3 Mandatory Field Dispatch Below Hardware Cutoff: If live optical Rx power on circuit {s0.target_circuit_id} drops strictly below -27.5 dBm, "
            "remote automated recalibration is prohibited and Provider must immediately generate a priority TMF621 field fiber repair dispatch.",
            styles["BodyJustified"],
        )
    )

    msa_doc.build(msa_story)

    return PdfArtifactResult(
        hw_pdf_path=hw_pdf_path,
        hw_pdf_pages=5,
        msa_pdf_path=msa_pdf_path,
        msa_pdf_pages=4,
    )


# ============================================================================
# 4. MULTI-PROCEDURE NOC SOP MANUAL (.docx and .md)
# ============================================================================
def generate_sop_runbook(
    base_dir: Path, config: AppConfig, logger: logging.Logger
) -> SopArtifactResult:
    """
    Create the 6-section operational runbook (`SOP_NOC_Master_Assurance_Runbook_v2026.docx`
    and `.md`) containing 5 distinct SOPs with `SOP-ASSUR-402` in Section 5.
    """
    sop_dir = base_dir / Path(config.paths.sop_subdir)
    sop_dir.mkdir(parents=True, exist_ok=True)
    s0 = config.stage0

    docx_path = sop_dir / s0.sop_runbook_docx_filename
    md_path = sop_dir / s0.sop_runbook_md_filename
    logger.info("Creating Multi-Procedure NOC SOP Runbook at %s and %s", docx_path, md_path)

    sections_data: List[Dict[str, object]] = [
        {
            "sec_num": "Section 1",
            "title": "Section 1: Purpose, General NOC Safety & Change Control Governance",
            "sop_id": "GOV-NOC-001",
            "etom": "eTOM 1.3 / 1.4 Cross-Domain Assurance Governance",
            "body": [
                "1.1 Purpose: This Master Network Operations Center (NOC) Assurance Runbook consolidates five (5) standard operating procedures across IP Core, 5G RAN, Residential GPON, Enterprise L2 Carrier Ethernet, and DWDM Optical Transport.",
                "1.2 Agentic & Human Safety Invariants: No automated worker agent or NOC engineer may execute a state mutation against production network elements without (a) verifying an active OAuth2 On-Behalf-Of (OBO) security token, (b) executing a live non-cached singleton hardware pre-check, (c) acquiring a short-lived Redis mutex resource lock, and (d) validating post-action knowledge writes against SHACL shapes.",
                "1.3 Scope Slicing Rule for SOP-to-Skill Compilation: When compiling a domain-specific Worker Agent skill, the SOP-to-Skill CI/CD pipeline must slice ONLY the target SOP section matching the requested procedure ID and discard unrelated sections.",
            ],
        },
        {
            "sec_num": "Section 2",
            "title": "Section 2 (SOP-ASSUR-101): BGP Peering Session Flap Triage & Dampening",
            "sop_id": "SOP-ASSUR-101",
            "etom": "eTOM 1.4.5 IP Core Routing Trouble Management (DISTRACTOR PROCEDURE)",
            "body": [
                "2.1 Trigger Condition: eBGP peering session experiences >= 5 state transitions (Established <-> Idle) within a 10-minute sliding window on core autonomous system border routers (ASBRs).",
                "2.2 Diagnostic Steps: Query NetFlow/BMP collector for prefix churn; verify IXP LAN ARP reachability; apply RFC 7196 route flap dampening profile (half-life=15m, suppress=2000, reuse=750, max-suppress=60m).",
                "2.3 Remediation Action: Invoke core BGP dampening RPC if peer is non-transit; otherwise escalate to Tier-3 IP Core Engineering.",
            ],
        },
        {
            "sec_num": "Section 3",
            "title": "Section 3 (SOP-ASSUR-205): 5G RAN gNodeB Sector Outage & Tilt Reset",
            "sop_id": "SOP-ASSUR-205",
            "etom": "eTOM 1.4.5 Mobile Radio Access Network Assurance (DISTRACTOR PROCEDURE)",
            "body": [
                "3.1 Trigger Condition: 3GPP n78 (3.5 GHz) gNodeB sector reports VSWR > 1.8 or complete RRC connection drop across > 50 active UEs.",
                "3.2 Diagnostic Steps: Check AISG v2.0 Remote Electrical Tilt (RET) actuator current draw and CPRI/eCPRI fronthaul optical link status.",
                "3.3 Remediation Action: If RET motor calibration fault is isolated, execute non-intrusive AISG tilt actuator soft reset; if VSWR > 2.2, lock RF carrier and dispatch tower rigger.",
            ],
        },
        {
            "sec_num": "Section 4",
            "title": "Section 4 (SOP-ASSUR-310): Residential GPON ONT Optical Dying-Gasp Handling",
            "sop_id": "SOP-ASSUR-310",
            "etom": "eTOM 1.3.7 Consumer FTTx Mass Assurance (DISTRACTOR PROCEDURE)",
            "body": [
                "4.1 Trigger Condition: Residential GPON ONT emits PLOAM Dying-Gasp message followed by OLT PON port LOSi alarm.",
                "4.2 Diagnostic Steps: Correlate across neighboring ONTs on the same 1:32 passive optical splitter; if < 3 ONTs affected and Dying-Gasp flag is true, classify as customer premises power outage.",
                "4.3 Remediation Action: Suppress field dispatch for 4 hours and send automated SMS power-check notification to residential subscriber.",
            ],
        },
        {
            "sec_num": "Section 5",
            "title": f"Section 5 ({s0.target_sop_id} — TARGET): Enterprise L2 Fiber Packet-Loss Triage & Optical DDM Recalibration",
            "sop_id": s0.target_sop_id,
            "etom": "eTOM 1.3.7 Problem Handling & 1.4.5 Resource Trouble Management (TARGET USE CASE UC-001)",
            "body": [
                f"5.1 Procedure Metadata: SOP ID: {s0.target_sop_id} | Revision: 4.1 | Target Skill ID: telco.assurance.l2_fiber_degradation | Approved By: Lead Transport Architect (j.vandijk@telco-arch.nl).",
                "5.2 Pre-Condition Gate (Guardrail GR-PRE-01): Verify that reported_packet_loss_pct >= 0.5%. If reported_packet_loss_pct < 0.5%, immediately abort the troubleshooting workflow and return status NO_ACTION_REQUIRED without querying downstream systems or mutating network state.",
                f"5.3 Step 1 — Multi-Pronged Semantic Context Lookup (STEP_1_SEMANTIC_CONTEXT): Invoke the Semantic Knowledge Layer (Layer 3/4 read-only SPARQL federation) for the target circuit_id (e.g., {s0.target_circuit_id}) to join:",
                f"  - Prong 1 (Virtual SQL CMDB <urn:telco:graph:virtual:ib>): Customer identity ({s0.target_customer_id} / '{s0.target_customer_legal_name}'), active CustomerFacingService ({s0.target_circuit_id}), linked ServiceSpecification ({s0.target_product_sku}), terminating OLT port ({s0.target_olt_port}), PE router ({s0.target_pe_router}), CPE asset ({s0.target_cpe_asset_id}), and CPE hardware model SKU ({s0.target_cpe_model_sku}).",
                f"  - Prong 2 (Materialized Excel Catalog <urn:telco:graph:ref:catalog>): ServiceSpecification SLA max packet loss threshold (0.1% for {s0.target_product_sku}), auto-remediation flag (YES), and eligible upgrade SKU ({s0.target_upgrade_sku}).",
                f"  - Prong 3 (BITES PDF Graphs <urn:telco:graph:bites:doc-hw-v4> & <urn:telco:graph:bites:doc-msa-v1>): Vendor optical transceiver operating ranges for {s0.target_cpe_model_sku} (normal Rx: -14.0 dBm to -24.9 dBm; DDM recalibration window: -25.0 dBm to -27.5 dBm; critical LOS cutoff: < -27.5 dBm) and MSA Annex B bespoke SLA penalty (15% monthly service credit if loss > 0.1% for >30m) + pre-authorized DDM recalibration clause.",
                f"5.4 Step 2 — Real-Time Singleton Optical Probe & Mutex Lock (STEP_2_SINGLETON_OPTICAL_PROBE): Invoke probe_live_optical_port on the CQRS Singleton Check MCP Server with bypass_cache=true for the terminating port ({s0.target_olt_port} / {s0.target_cpe_asset_id}). Retrieve instantaneous live optical Rx power (live_rx_dbm), verify maintenance window status (maintenance_lock), and acquire a short-lived Redis port mutex lock token (singleton_lock_token).",
                "5.5 Step 3 & Step 4 — Deterministic 3-Way Branching & Guardrail Enforcement:",
                f"  * Branch A (Soft Optical Degradation — Target Happy Path): IF reported_packet_loss_pct >= 0.5% AND live_rx_dbm is between -25.0 dBm and the hardware manual's minimum Rx threshold (-27.5 dBm for {s0.target_cpe_model_sku}, i.e., -27.5 <= live_rx_dbm <= -25.0) AND maintenance_lock == false:",
                "      1) Enforce Guardrail GR-INV-01 (verify maintenance_lock == false and active singleton_lock_token).",
                "      2) Invoke execute_tmf640_recalibration on the CQRS Transactional Write MCP Server to perform non-intrusive DDM optical transceiver AGC/bias recalibration.",
                "      3) Invoke record_verified_incident_resolution on the CQRS Transactional Write MCP Server to commit a pySHACL-validated TroubleTicket resolution triple into <urn:telco:graph:assurance:resolutions>.",
                "  * Branch B (Hard Fiber Cut / Severe Attenuation): IF reported_packet_loss_pct >= 0.5% AND live_rx_dbm is strictly below the hardware minimum (< -27.5 dBm):",
                "      1) Enforce Execution Invariant Guardrail GR-INV-02: STRICTLY FORBID all remote write/recalibration tools (execute_tmf640_recalibration).",
                "      2) Invoke create_tmf621_field_dispatch on the CQRS Transactional Write MCP Server to dispatch a field fiber splicing/OTDR technician crew.",
                "  * Branch C (Active Maintenance Freeze / Normal Optical Power / Low Loss): IF reported_packet_loss_pct < 0.5% OR maintenance_lock == true OR live_rx_dbm > -25.0 dBm:",
                "      1) Enforce Execution Invariant Guardrail GR-INV-01: Abort all remote network mutations.",
                "      2) Release the Redis port mutex lock and log a non-intrusive monitoring diagnostic note.",
            ],
        },
        {
            "sec_num": "Section 6",
            "title": "Section 6 (SOP-ASSUR-509): Core DWDM Erbium-Doped Fiber Amplifier (EDFA) Pump Laser Replacement",
            "sop_id": "SOP-ASSUR-509",
            "etom": "eTOM 1.4.5 Optical Transport Core Maintenance (DISTRACTOR PROCEDURE)",
            "body": [
                "6.1 Trigger Condition: Core DWDM line amplifier raises Pump-Laser-Bias-Current-High (> 950 mA) or Optical-Gain-Tilt alarm on 80-channel C-band span.",
                "6.2 Diagnostic Steps: Verify ROADM optical protection switching status on diverse path; confirm zero single-homed wavelengths on degraded EDFA degree.",
                "6.3 Remediation Action: Shift C-band optical multiplex section (OMS) traffic to protection fiber via GMPLS control plane and schedule planned chassis line-card swap.",
            ],
        },
    ]

    md_lines = [
        "# MASTER NOC ASSURANCE STANDARD OPERATING PROCEDURES RUNBOOK (v2026.4)",
        "",
        "**Document ID:** `SOP-NOC-MASTER-RUNBOOK-2026-V4`  ",
        "**Custodian:** Enterprise Network Operations & Transport Engineering  ",
        f"**Contained Procedures:** `SOP-ASSUR-101`, `SOP-ASSUR-205`, `SOP-ASSUR-310`, `{s0.target_sop_id}` (TARGET UC-001), `SOP-ASSUR-509`",
        "",
        "---",
        "",
    ]

    for sec in sections_data:
        md_lines.append(f"## {sec['title']}")
        md_lines.append(f"- **Procedure / Governance ID:** `{sec['sop_id']}`")
        md_lines.append(f"- **TM Forum eTOM Alignment:** {sec['etom']}")
        md_lines.append("")
        for p_text in sec["body"]:  # type: ignore[attr-defined]
            md_lines.append(str(p_text))
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    doc = Document()
    title_heading = doc.add_heading("MASTER NOC ASSURANCE STANDARD OPERATING PROCEDURES RUNBOOK (v2026.4)", level=0)
    for run in title_heading.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

    meta_p = doc.add_paragraph(
        "Document ID: SOP-NOC-MASTER-RUNBOOK-2026-V4 | Custodian: Enterprise Network Operations & Transport Engineering | "
        f"Procedures: SOP-ASSUR-101, SOP-ASSUR-205, SOP-ASSUR-310, {s0.target_sop_id} (TARGET UC-001), SOP-ASSUR-509"
    )
    meta_p.runs[0].italic = True

    summary_table = doc.add_table(rows=1, cols=4)
    summary_table.style = "Table Grid"
    hdr_cells = summary_table.rows[0].cells
    hdr_cells[0].text = "Section"
    hdr_cells[1].text = "Procedure ID"
    hdr_cells[2].text = "eTOM Alignment"
    hdr_cells[3].text = "UC-001 Slicing Disposition"

    for sec in sections_data:
        row_cells = summary_table.add_row().cells
        row_cells[0].text = str(sec["sec_num"])
        row_cells[1].text = str(sec["sop_id"])
        row_cells[2].text = str(sec["etom"])
        row_cells[3].text = "TARGET — COMPILE TO SKILL" if sec["sop_id"] == s0.target_sop_id else "DISTRACTOR — FILTER OUT"

    for sec in sections_data:
        doc.add_heading(str(sec["title"]), level=1)
        sub_p = doc.add_paragraph(f"Procedure ID: {sec['sop_id']} | eTOM Domain: {sec['etom']}")
        sub_p.runs[0].bold = True
        for p_text in sec["body"]:  # type: ignore[attr-defined]
            doc.add_paragraph(str(p_text))

    doc.save(str(docx_path))

    return SopArtifactResult(
        docx_path=docx_path,
        md_path=md_path,
        section_count=len(sections_data),
        target_sop_id=s0.target_sop_id,
    )


# ============================================================================
# 5. STAGE 0 ARTIFACT MANIFEST & UPDATED GOVERNANCE LOGS
# ============================================================================
def generate_manifest(
    base_dir: Path,
    config: AppConfig,
    sql_stats: SqlArtifactResult,
    excel_stats: ExcelArtifactResult,
    pdf_stats: PdfArtifactResult,
    sop_stats: SopArtifactResult,
    logger: logging.Logger,
) -> Path:
    """Write `STAGE0_ARTIFACT_MANIFEST.md` including the UCDIL and Observation Notepad."""
    manifest_path = base_dir / config.paths.manifest_filename
    logger.info("Writing Stage 0 Artifact Manifest to %s", manifest_path)
    tc = sql_stats.table_counts

    content = f"""# Stage 0 (Activity 0.2) Frozen Source Artifact Manifest — Use Case UC-001

**Document ID:** `MANIFEST-TELCO-UC001-ACT02-V1`  
**Use Case:** `{config.project.use_case_id}` — *{config.project.use_case_title}*  
**Target Customer:** `{config.stage0.target_customer_legal_name}` (`{config.stage0.target_customer_id}` in SQL CMDB / `"{config.stage0.target_customer_bv_name}"`, KvK `{config.stage0.target_customer_kvk}` in MSA PDF)  
**Target Circuit & Resources:** Circuit `{config.stage0.target_circuit_id}` (`{config.stage0.target_product_sku}`) $\\rightarrow$ PE Router `{config.stage0.target_pe_router}` $\\rightarrow$ OLT Port `{config.stage0.target_olt_port}` (`{config.stage0.target_rfs_id}`) $\\rightarrow$ CPE Asset `{config.stage0.target_cpe_asset_id}` (Hardware SKU `{config.stage0.target_cpe_model_sku}`)  
**Generator Module:** `src/stage0_generator.py` via `scripts/generate_stage0_raw_sources.py` (Deterministic Seed = `{config.stage0.seed}`)

---

## 1. Summary of Generated Raw Data Artifacts

| Prong / Source Type | Artifact File Path | Volume / Noise Profile | Exact Location of Target `UC-001` Data Points |
| :--- | :--- | :--- | :--- |
| **Prong 1 (SQLite CMDB)** | `data/raw_sources/sql/{sql_stats.db_path.name}` | 4 tables, **{tc.total_rows} total rows**, nullable FKs, shadow enums (`'10'`,`'20'`,`'99'`), mixed units (`Gbps`,`Mbps`,`Kbps`), SCD2 history | `T_OSS_CUST_PARTY` (`PARTY_SURR_ID=1009`, `CUST_EXT_REF='{config.stage0.target_customer_id}'`); `T_CMDB_CFS_CIRCUIT` (`CFS_ROW_ID=2001` active `{config.stage0.target_circuit_id}`, `CFS_ROW_ID=2000` superseded SCD2 row); `T_CMDB_RFS_RESOURCE` (`RFS_ID='{config.stage0.target_rfs_id}'`) |
| **Prong 1 (SQL Dump)** | `data/raw_sources/sql/{sql_stats.dump_path.name}` | Full DDL + DML export of all 4 tables (`T_OSS_CUST_PARTY`, `T_CMDB_CFS_CIRCUIT`, `T_CMDB_RFS_RESOURCE`, `T_BILLING_AUDIT_NOISE`) | Same as `{sql_stats.db_path.name}` |
| **Prong 2 (Excel SLA Catalog)** | `data/raw_sources/excel/{excel_stats.excel_path.name}` | **3 tabs**, merged banners (rows 1–3), empty row 4, headers in row 5, **{excel_stats.tab_counts.total_skus} total SKUs**, 14 columns in Tab 2 + 2 dirty SHACL quarantine test rows | **Tab 2 (`B2B_Enterprise_SLA_Matrix`), Row 7**: `Product_SKU_Code='{config.stage0.target_product_sku}'`, `Max_Packet_Loss_Pct=0.1`, `Eligible_Upgrade_SKU='{config.stage0.target_upgrade_sku}'`, `Auto_Remediation_Allowed='YES'` |
| **Prong 3A (Hardware Manual PDF)** | `data/raw_sources/pdf/{pdf_stats.hw_pdf_path.name}` | **{pdf_stats.hw_pdf_pages} pages / 5 chapters** covering power, thermal, RJ-45 copper, and multi-vendor optical transceivers (`Cisco`, `Juniper`, `Nokia`) | **Page 4, Chapter 4 (Section 4.2 & Specification Table Row 3)**: `{config.stage0.target_cpe_model_sku}` (10GBASE-LR 1310nm): Nominal Tx `-1.0 dBm`, Overload Rx `-1.0 dBm`, Normal Rx `-14.0 to -24.9 dBm`, DDM Recalibration Window `-25.0 to -27.5 dBm`, Critical LOS Cutoff `< -27.5 dBm` |
| **Prong 3B (MSA Contract PDF)** | `data/raw_sources/pdf/{pdf_stats.msa_pdf_path.name}` | **{pdf_stats.msa_pdf_pages} pages / 7 clauses** covering corporate parties, term, invoicing, liability, force majeure, 5 site schedules (Annex A), and Annex B SLA rules | **Page 1 (Clause 1)**: `"{config.stage0.target_customer_bv_name}"` (`{config.stage0.target_customer_kvk}` / `{config.stage0.target_customer_id}`); **Page 3 (Clause 6 / Annex A, Site 1)**: `{config.stage0.target_circuit_id}` on `{config.stage0.target_product_sku}`; **Page 4 (Clause 7 / Annex B)**: `15%` monthly credit if packet loss `> 0.1%` for `> 30 min` + pre-authorized remote DDM recalibration if `maintenance_lock == false` |
| **Multi-Procedure SOP (DOCX)** | `data/raw_sources/sop/{sop_stats.docx_path.name}` | **{sop_stats.section_count} sections** (1 governance + 4 distractor SOPs `101`, `205`, `310`, `509` + 1 target SOP `402`) | **Section 5 (`{sop_stats.target_sop_id}`)**: 4-step workflow, `reported_packet_loss_pct >= 0.5%` pre-condition, semantic context join, live singleton optical probe (`bypass_cache=true`), and deterministic **Branches A, B, and C** |
| **Multi-Procedure SOP (Markdown)** | `data/raw_sources/sop/{sop_stats.md_path.name}` | Markdown mirror of the 6-section Master Runbook for direct inspection and diffing | **Section 5 (`{sop_stats.target_sop_id}`)** |

---

## 2. Detailed Breakdown by Prong & Noise Filtering Verification

### 2.1 Prong 1: Relational SQL CMDB (`{sql_stats.db_path.name}` & `{sql_stats.dump_path.name}`)
- **`T_OSS_CUST_PARTY` ({tc.T_OSS_CUST_PARTY} rows, 7 columns)**:
  - Columns: `PARTY_SURR_ID`, `CUST_EXT_REF`, `LEGAL_NAME`, `SEGMENT_CD`, `ACCT_MGR_ID`, `LEGACY_CRM_ID`, `CREATED_TS`
  - **Target Row**: `PARTY_SURR_ID=1009`, `CUST_EXT_REF='{config.stage0.target_customer_id}'`, `LEGAL_NAME='{config.stage0.target_customer_legal_name}'`, `SEGMENT_CD='ENT_VIP'`
- **`T_CMDB_CFS_CIRCUIT` ({tc.T_CMDB_CFS_CIRCUIT} rows, 11 columns)**:
  - Columns: `CFS_ROW_ID`, `CIRCUIT_ID`, `CUST_REF_ID`, `PROD_SPEC_CODE`, `OPER_STATUS_CD`, `BW_VAL`, `BW_UNIT_CD`, `INSTALL_DT`, `VALID_FROM_TS`, `VALID_TO_TS`, `LEGACY_BILL_TAG`
  - **Target Active Row**: `CFS_ROW_ID=2001`, `CIRCUIT_ID='{config.stage0.target_circuit_id}'`, `CUST_REF_ID='{config.stage0.target_customer_id}'`, `PROD_SPEC_CODE='{config.stage0.target_product_sku}'`, `OPER_STATUS_CD='10'` (Active), `BW_VAL=10`, `BW_UNIT_CD='Gbps'`, `VALID_FROM_TS='2025-06-01T00:00:00Z'`, `VALID_TO_TS=NULL`
  - **Target Historical SCD2 Row (Superseded)**: `CFS_ROW_ID=2000`, `CIRCUIT_ID='{config.stage0.target_circuit_id}'`, `PROD_SPEC_CODE='ETH-1G-SILVER'`, `VALID_FROM_TS='2023-01-15T00:00:00Z'`, `VALID_TO_TS='2025-06-01T00:00:00Z'`
- **`T_CMDB_RFS_RESOURCE` ({tc.T_CMDB_RFS_RESOURCE} rows, 9 columns)**:
  - Columns: `RFS_ID`, `PARENT_CFS_ID`, `PE_ROUTER_HOSTNAME`, `OLT_PORT_ID`, `CPE_ASSET_ID`, `CPE_MODEL_SKU`, `VLAN_TAG`, `FIBER_SPAN_ID`, `LAST_SYNC_UTC`
  - **Target Row**: `RFS_ID='{config.stage0.target_rfs_id}'`, `PARENT_CFS_ID='{config.stage0.target_circuit_id}'`, `PE_ROUTER_HOSTNAME='{config.stage0.target_pe_router}'`, `OLT_PORT_ID='{config.stage0.target_olt_port}'`, `CPE_ASSET_ID='{config.stage0.target_cpe_asset_id}'`, `CPE_MODEL_SKU='{config.stage0.target_cpe_model_sku}'`, `VLAN_TAG=2409`, `FIBER_SPAN_ID='FBR-HAG-RING02-S14'`
- **`T_BILLING_AUDIT_NOISE` ({tc.T_BILLING_AUDIT_NOISE} rows, 10 columns)**:
  - Columns: `INV_ID`, `CUST_REF_ID`, `BILL_CYCLE_CD`, `GROSS_AMT_EUR`, `TAX_CD`, `VAT_PCT`, `GL_POST_DT`, `DUNNING_LVL`, `ERP_BATCH_REF`, `AUDIT_HASH`
  - Purpose: Completely excluded by Layer 4 R2RML/SMS2 virtual graph mappings during schema pruning.

### 2.2 Prong 2: Multi-Tab Excel Catalog (`{excel_stats.excel_path.name}`)
- **Formatting Noise**: Merged banner across rows 1–3, empty separator row 4, table headers in row 5.
- **Tab 1 (`Residential_FTTH_Plans`)**: {excel_stats.tab_counts.Residential_FTTH_Plans} consumer GPON/XGS-PON plans (distractor worksheet ignored by ingestion).
- **Tab 2 (`B2B_Enterprise_SLA_Matrix`)**: {excel_stats.tab_counts.B2B_Enterprise_SLA_Matrix} B2B SKUs across 14 columns:
  - **Row 7 (Target)**: `{config.stage0.target_product_sku}` | `Max_Packet_Loss_Pct = 0.1` | `Max_Jitter_ms = 2.0` | `MTTR_Target_Hours = 4` | `Eligible_Upgrade_SKU = '{config.stage0.target_upgrade_sku}'` | `Auto_Remediation_Allowed = 'YES'`
  - **Row 8 (Upgrade Target)**: `{config.stage0.target_upgrade_sku}` | `Max_Packet_Loss_Pct = 0.01` | `MTTR_Target_Hours = 2`
  - **Rows 24 & 25 (SHACL Quarantine Test Rows)**: `DARK-FIBER-METRO-X` (`Max_Packet_Loss_Pct = -0.5`, `Shadow_Lifecycle_Flag = '99_INVALID'`) and `SDWAN-LEGACY-99` (`Max_Packet_Loss_Pct = 125.0`, `MTTR_Target_Hours = NULL`).
- **Tab 3 (`Deprecated_Legacy_SKUs`)**: {excel_stats.tab_counts.Deprecated_Legacy_SKUs} obsolete ATM/Frame-Relay/ISDN SKUs (distractor worksheet ignored by ingestion).

### 2.3 Prong 3: Unstructured PDFs (`{pdf_stats.hw_pdf_path.name}` & `{pdf_stats.msa_pdf_path.name}`)
- **`{pdf_stats.hw_pdf_path.name}` ({pdf_stats.hw_pdf_pages} Pages)**:
  - Pages 1–3 (Chapters 1–3) & Page 5 (Chapter 5): Power, thermal, copper RJ-45, and field cleaning distractors.
  - **Page 4 (Chapter 4)**: `{config.stage0.target_cpe_model_sku}` 10GBASE-LR 1310nm thresholds: Nominal Tx `-1.0 dBm`, Overload Rx `-1.0 dBm`, Normal Rx `-14.0 dBm to -24.9 dBm`, Soft Degradation / DDM Recalibration Window `-25.0 dBm to -27.5 dBm`, Critical LOS Cutoff `< -27.5 dBm`.
- **`{pdf_stats.msa_pdf_path.name}` ({pdf_stats.msa_pdf_pages} Pages)**:
  - **Page 1 (Clause 1)**: Links legal entity `"{config.stage0.target_customer_bv_name}"` (Registration `{config.stage0.target_customer_kvk}`) to OSS ID `{config.stage0.target_customer_id}` (`"{config.stage0.target_customer_legal_name}"`).
  - **Page 3 (Clause 6 / Annex A)**: Lists `{config.stage0.target_circuit_id}` (`{config.stage0.target_product_sku}`, `{config.stage0.target_cpe_model_sku}`) alongside 4 distractor corporate sites.
  - **Page 4 (Clause 7 / Annex B)**: Specifies `15%` monthly service credit if packet loss exceeds `0.1%` for `>30 minutes` on `{config.stage0.target_circuit_id}`, and grants pre-authorized remote TMF640 DDM optical recalibration when `maintenance_lock == false`.

---

## 3. Living Governance Logs (Updated for Activity 0.2 Completion)

### 3.1 Use Case Design & Implementation Log (UCDIL — Baseline v2)

| Design Dimension | Parameter / Artifact | Locked Specification for UC-001 | Status |
| :--- | :--- | :--- | :--- |
| **1. Scope & eTOM** | Use Case ID & Title | `{config.project.use_case_id}`: {config.project.use_case_title} | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | TM Forum eTOM / SID | eTOM `1.3.7` & `1.4.5` \\| SID: `Customer -> CFS -> ServiceSpec -> RFS -> PhysicalResource -> Spec` | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | Customer & Circuit | Customer: `'{config.stage0.target_customer_legal_name}'` (`{config.stage0.target_customer_id}` / `'{config.stage0.target_customer_bv_name}'`, `{config.stage0.target_customer_kvk}`) \\| Circuit: `{config.stage0.target_circuit_id}` | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | Hardware & Port | CPE Asset: `{config.stage0.target_cpe_asset_id}` \\| Model SKU: `{config.stage0.target_cpe_model_sku}` \\| OLT Port: `{config.stage0.target_olt_port}` \\| Router: `{config.stage0.target_pe_router}` | **LOCKED (Act 0.1)** |
| **1. Scope & eTOM** | SOP & Branches | Source: `SOP_NOC_Master_Assurance_Runbook_v2026` (Section 5: `{config.stage0.target_sop_id}`) $\\rightarrow$ Branches A, B, C | **LOCKED (Act 0.1)** |
| **2. Data Footprint** | Prong 1 (SQL CMDB) | `data/raw_sources/sql/{sql_stats.db_path.name}` & `{sql_stats.dump_path.name}` (4 tables, {tc.total_rows} rows, SCD2 + shadow enums) | **LOCKED (Act 0.2)** |
| **2. Data Footprint** | Prong 2 (Excel SLA) | `data/raw_sources/excel/{excel_stats.excel_path.name}` (3 tabs, {excel_stats.tab_counts.total_skus} SKUs, 2 dirty SHACL test rows) | **LOCKED (Act 0.2)** |
| **2. Data Footprint** | Prong 3 (PDF Docs) | `{pdf_stats.hw_pdf_path.name}` ({pdf_stats.hw_pdf_pages}p) & `{pdf_stats.msa_pdf_path.name}` ({pdf_stats.msa_pdf_pages}p) | **LOCKED (Act 0.2)** |
| **2. Data Footprint** | Multi-SOP Runbook | `{sop_stats.docx_path.name}` & `{sop_stats.md_path.name}` ({sop_stats.section_count} sections; target `{sop_stats.target_sop_id}` in Section 5) | **LOCKED (Act 0.2)** |

### 3.2 Observation Notepad (Findings Through Activity 0.2)

| ID & Activity | Observation / Friction Encountered | Impact Target | Remediation Applied |
| :--- | :--- | :--- | :--- |
| **OBS-00 (Setup)** | Implementation Plan needed a living Use Case Design & Implementation Log (UCDIL) across Stages 0–3. | Implementation Plan (Sections 2 & 6) | Maintained UCDIL in Activity 0.1 Charter and updated to Baseline v2 in `STAGE0_ARTIFACT_MANIFEST.md`. |
| **OBS-01 (Act 0.1)** | Telecom SOPs are multi-procedure runbooks; compiler must slice out only the target procedure. | Architecture Blueprint (Section 3.2) | Generated 6-section Master Runbook with 4 distractor SOPs (`101`, `205`, `310`, `509`) and target `{sop_stats.target_sop_id}` in Section 5. |
| **OBS-02 (Act 0.1)** | Enterprise data buries target parameters inside wide SQL tables, multi-tab spreadsheets, and multi-chapter PDFs. | Implementation Plan (Sections 2.2 & 4.3) | Generated wide 4-table SQLite DB, 3-tab Excel with merged banners, and 2 multi-page PDFs with chapter/clause noise. |
| **OBS-03 (Act 0.2)** | Testing Layer 4 temporal window filtering (`SCD Type 2`) and Track B `pySHACL` quarantine requires explicit historical and malformed distractor records in the frozen Stage 0 dataset. | Stage 0 Raw Data & Track B Ingestion | Added 1 superseded SCD2 row (`CFS_ROW_ID=2000`) for `{config.stage0.target_circuit_id}` in `T_CMDB_CFS_CIRCUIT` and 2 malformed distractor rows (`Rows 24–25`) in `B2B_Enterprise_SLA_Matrix`. |
"""
    manifest_path.write_text(content, encoding="utf-8")
    return manifest_path


# ============================================================================
# 6. VERIFICATION & SUMMARY BUILDER
# ============================================================================
def verify_and_summarize(
    base_dir: Path,
    config: AppConfig,
    sql_stats: SqlArtifactResult,
    excel_stats: ExcelArtifactResult,
    pdf_stats: PdfArtifactResult,
    sop_stats: SopArtifactResult,
    manifest_path: Path,
    logger: logging.Logger,
    workspace_root: Optional[Path] = None,
) -> Stage0GenerationSummary:
    """
    Execute fail-fast verification queries across the generated Stage 0 artifacts,
    log the verification summary, and return a validated `Stage0GenerationSummary`.
    """
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()

    conn = sqlite3.connect(str(sql_stats.db_path))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.CUST_EXT_REF, p.LEGAL_NAME, c.CIRCUIT_ID, c.PROD_SPEC_CODE, c.OPER_STATUS_CD,
               c.BW_VAL, c.BW_UNIT_CD, r.PE_ROUTER_HOSTNAME, r.OLT_PORT_ID, r.CPE_ASSET_ID, r.CPE_MODEL_SKU
        FROM T_OSS_CUST_PARTY p
        JOIN T_CMDB_CFS_CIRCUIT c ON p.CUST_EXT_REF = c.CUST_REF_ID
        JOIN T_CMDB_RFS_RESOURCE r ON c.CIRCUIT_ID = r.PARENT_CFS_ID
        WHERE c.CIRCUIT_ID = ? AND c.VALID_TO_TS IS NULL;
        """,
        (config.stage0.target_circuit_id,),
    )
    target_sql_row = cur.fetchone()
    conn.close()

    if target_sql_row is None:
        raise RuntimeError(
            f"Verification failed: Active circuit '{config.stage0.target_circuit_id}' not found in SQLite CMDB."
        )

    wb = openpyxl.load_workbook(str(excel_stats.excel_path), data_only=True)
    ws_b2b = wb["B2B_Enterprise_SLA_Matrix"]
    eth_gold_row = None
    for row in ws_b2b.iter_rows(min_row=6, values_only=True):
        if row[0] == config.stage0.target_product_sku:
            eth_gold_row = row
            break
    wb.close()

    if eth_gold_row is None:
        raise RuntimeError(
            f"Verification failed: Target SKU '{config.stage0.target_product_sku}' not found in B2B_Enterprise_SLA_Matrix."
        )

    summary = Stage0GenerationSummary(
        base_dir=base_dir,
        sql=sql_stats,
        excel=excel_stats,
        pdf=pdf_stats,
        sop=sop_stats,
        manifest_path=manifest_path,
        verified_sql_join=(
            str(target_sql_row[0]),
            str(target_sql_row[1]),
            str(target_sql_row[2]),
            str(target_sql_row[3]),
            str(target_sql_row[4]),
            int(target_sql_row[5]),
            str(target_sql_row[6]),
            str(target_sql_row[7]),
            str(target_sql_row[8]),
            str(target_sql_row[9]),
            str(target_sql_row[10]),
        ),
        verified_eth_gold_loss_pct=float(eth_gold_row[3]),
        verified_eth_gold_upgrade_sku=str(eth_gold_row[6]),
        verified_eth_gold_auto_remediation=str(eth_gold_row[7]),
    )

    def _rel(p: Path) -> Path:
        try:
            return p.relative_to(root_dir)
        except ValueError:
            return p

    logger.info("=" * 88)
    logger.info("STAGE 0 (ACTIVITY 0.2) RAW DATA SOURCES GENERATION & VERIFICATION SUMMARY")
    logger.info("=" * 88)
    logger.info("Workspace Base Directory : %s", base_dir)
    logger.info("-" * 88)
    logger.info("[1] PRONG 1 — WIDE RELATIONAL SQL CMDB:")
    logger.info("    - SQLite DB   : %s (%d bytes)", _rel(sql_stats.db_path), sql_stats.db_path.stat().st_size)
    logger.info("    - SQL Dump    : %s (%d bytes)", _rel(sql_stats.dump_path), sql_stats.dump_path.stat().st_size)
    for tbl, cnt in sql_stats.table_counts.model_dump().items():
        logger.info("      * %-24s: %3d rows", tbl, cnt)
    logger.info("    - Verified Active Target Join (%s): %s", config.stage0.target_circuit_id, summary.verified_sql_join)
    logger.info("-" * 88)
    logger.info("[2] PRONG 2 — MULTI-TAB EXCEL WORKBOOK:")
    logger.info("    - Excel File  : %s (%d bytes)", _rel(excel_stats.excel_path), excel_stats.excel_path.stat().st_size)
    for tab, cnt in excel_stats.tab_counts.model_dump().items():
        logger.info("      * Tab '%s' : %d data rows (merged banner rows 1-3, empty row 4, headers row 5)", tab, cnt)
    logger.info(
        "    - Verified Target SKU '%s': Max_Packet_Loss_Pct=%s%%, Upgrade='%s', Auto_Remediation='%s'",
        config.stage0.target_product_sku,
        summary.verified_eth_gold_loss_pct,
        summary.verified_eth_gold_upgrade_sku,
        summary.verified_eth_gold_auto_remediation,
    )
    logger.info("-" * 88)
    logger.info("[3] PRONG 3 — UNSTRUCTURED MULTI-CHAPTER PDFs:")
    logger.info(
        "    - Hardware PDF: %s (%d pages, %d bytes)",
        _rel(pdf_stats.hw_pdf_path),
        pdf_stats.hw_pdf_pages,
        pdf_stats.hw_pdf_path.stat().st_size,
    )
    logger.info(
        "      * Target Spec (Ch. 4): %s | Normal [-14.0, -24.9 dBm] | Recalibration [-25.0, -27.5 dBm] | Cutoff < -27.5 dBm",
        config.stage0.target_cpe_model_sku,
    )
    logger.info(
        "    - MSA PDF     : %s (%d pages, %d bytes)",
        _rel(pdf_stats.msa_pdf_path),
        pdf_stats.msa_pdf_pages,
        pdf_stats.msa_pdf_path.stat().st_size,
    )
    logger.info(
        "      * Target Clauses: '%s' (%s) | Annex A: %s | Annex B: 15%% credit (>0.1%% loss >30m) + pre-authorized DDM recalibration",
        config.stage0.target_customer_bv_name,
        config.stage0.target_customer_kvk,
        config.stage0.target_circuit_id,
    )
    logger.info("-" * 88)
    logger.info("[4] MULTI-PROCEDURE NOC SOP MASTER RUNBOOK:")
    logger.info("    - DOCX Runbook: %s (%d bytes)", _rel(sop_stats.docx_path), sop_stats.docx_path.stat().st_size)
    logger.info("    - MD Runbook  : %s (%d bytes)", _rel(sop_stats.md_path), sop_stats.md_path.stat().st_size)
    logger.info("      * Sections  : %d sections (Target Procedure: %s in Section 5)", sop_stats.section_count, sop_stats.target_sop_id)
    logger.info("-" * 88)
    logger.info("[5] STAGE 0 ARTIFACT MANIFEST & GOVERNANCE LOGS:")
    logger.info("    - Manifest    : %s (%d bytes)", _rel(manifest_path), manifest_path.stat().st_size)
    logger.info("=" * 88)

    return summary


def run_stage0_generation(
    config: AppConfig,
    logger: logging.Logger,
    workspace_root: Optional[Path] = None,
) -> Stage0GenerationSummary:
    """
    Orchestrate end-to-end Stage 0 (Activity 0.2) raw data source generation
    and verification using relative paths resolved against `workspace_root`.
    """
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()
    base_dir = root_dir / Path(config.paths.raw_sources_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    sql_stats = generate_sql_cmdb(base_dir, config, logger)
    excel_stats = generate_excel_catalog(base_dir, config, logger)
    pdf_stats = generate_pdfs(base_dir, config, logger)
    sop_stats = generate_sop_runbook(base_dir, config, logger)
    manifest_path = generate_manifest(base_dir, config, sql_stats, excel_stats, pdf_stats, sop_stats, logger)

    return verify_and_summarize(
        base_dir=base_dir,
        config=config,
        sql_stats=sql_stats,
        excel_stats=excel_stats,
        pdf_stats=pdf_stats,
        sop_stats=sop_stats,
        manifest_path=manifest_path,
        logger=logger,
        workspace_root=root_dir,
    )

