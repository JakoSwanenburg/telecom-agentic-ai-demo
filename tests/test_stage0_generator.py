"""
Unit tests for `src/stage0_generator.py`.

Verifies deterministic end-to-end generation of all 4 prongs/sources, SQL SCD Type 2
and shadow enum integrity, Excel 3-tab structure & dirty SHACL test rows, PDF generation,
SOP 6-section runbook structure, manifest generation, and fail-fast error handling.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl
import pytest
from docx import Document

from src.config import load_config
from src.logger import setup_logger
from src.stage0_generator import run_stage0_generation, verify_and_summarize


def test_end_to_end_stage0_generation_and_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run full Stage 0 generator in an isolated temp workspace and verify all outputs."""
    monkeypatch.setenv("ENV", "cloud")  # avoid file lock in tmp_path during test
    cfg = load_config()
    logger = setup_logger(config=cfg, logger_name="test.stage0", workspace_root=tmp_path)

    summary = run_stage0_generation(config=cfg, logger=logger, workspace_root=tmp_path)

    # 1. Verify Prong 1 SQL CMDB
    assert summary.sql.db_path.exists()
    assert summary.sql.dump_path.exists()
    assert summary.sql.table_counts.T_OSS_CUST_PARTY == 15
    assert summary.sql.table_counts.T_CMDB_CFS_CIRCUIT == 32
    assert summary.sql.table_counts.T_CMDB_RFS_RESOURCE == 32
    assert summary.sql.table_counts.T_BILLING_AUDIT_NOISE == 25
    assert summary.sql.table_counts.total_rows == 104

    assert summary.verified_sql_join == (
        "CUST-ENT-409",
        "A Corporate Enterprise",
        "CIR-994821",
        "ETH-10G-GOLD",
        "10",
        10,
        "Gbps",
        "NLD-HAG-PE02",
        "OLT04-P12",
        "CPE-ASN-7741",
        "NOK-7210-SAS-Mxp",
    )

    # Check SCD Type 2 superseded historical row for CIR-994821
    conn = sqlite3.connect(str(summary.sql.db_path))
    cur = conn.cursor()
    cur.execute(
        "SELECT CFS_ROW_ID, PROD_SPEC_CODE, VALID_TO_TS FROM T_CMDB_CFS_CIRCUIT WHERE CIRCUIT_ID='CIR-994821' ORDER BY CFS_ROW_ID;"
    )
    cir_rows = cur.fetchall()
    conn.close()
    assert len(cir_rows) == 2
    assert cir_rows[0] == (2000, "ETH-1G-SILVER", "2025-06-01T00:00:00Z")
    assert cir_rows[1] == (2001, "ETH-10G-GOLD", None)

    # 2. Verify Prong 2 Excel Catalog
    assert summary.excel.excel_path.exists()
    assert summary.excel.tab_counts.total_skus == 50
    assert summary.verified_eth_gold_loss_pct == pytest.approx(0.1)
    assert summary.verified_eth_gold_upgrade_sku == "ETH-100G-PLATINUM"
    assert summary.verified_eth_gold_auto_remediation == "YES"

    wb = openpyxl.load_workbook(str(summary.excel.excel_path), data_only=True)
    assert wb.sheetnames == [
        "Residential_FTTH_Plans",
        "B2B_Enterprise_SLA_Matrix",
        "Deprecated_Legacy_SKUs",
    ]
    ws_b2b = wb["B2B_Enterprise_SLA_Matrix"]
    assert ws_b2b.cell(row=4, column=1).value is None  # Row 4 is empty
    assert ws_b2b.cell(row=5, column=1).value == "Product_SKU_Code"
    # Verify deliberate dirty SHACL test rows at rows 24 and 25
    assert ws_b2b.cell(row=24, column=1).value == "DARK-FIBER-METRO-X"
    assert ws_b2b.cell(row=24, column=4).value == pytest.approx(-0.5)
    assert ws_b2b.cell(row=25, column=1).value == "SDWAN-LEGACY-99"
    assert ws_b2b.cell(row=25, column=6).value is None
    wb.close()

    # 3. Verify Prong 3 PDFs
    assert summary.pdf.hw_pdf_path.exists()
    assert summary.pdf.hw_pdf_path.stat().st_size > 5000
    assert summary.pdf.hw_pdf_pages == 5
    assert summary.pdf.msa_pdf_path.exists()
    assert summary.pdf.msa_pdf_path.stat().st_size > 4000
    assert summary.pdf.msa_pdf_pages == 4

    # 4. Verify Multi-Procedure SOP Runbook (.docx and .md)
    assert summary.sop.docx_path.exists()
    assert summary.sop.md_path.exists()
    assert summary.sop.section_count == 6
    assert summary.sop.target_sop_id == "SOP-ASSUR-402"

    md_text = summary.sop.md_path.read_text(encoding="utf-8")
    for sop_code in ["SOP-ASSUR-101", "SOP-ASSUR-205", "SOP-ASSUR-310", "SOP-ASSUR-402", "SOP-ASSUR-509"]:
        assert sop_code in md_text
    assert "execute_tmf640_recalibration" in md_text
    assert "create_tmf621_field_dispatch" in md_text

    docx_obj = Document(str(summary.sop.docx_path))
    full_docx_text = "\n".join(p.text for p in docx_obj.paragraphs)
    assert "SOP-ASSUR-402" in full_docx_text
    assert "-27.5 dBm" in full_docx_text

    # 5. Verify Stage 0 Manifest & Governance Logs
    assert summary.manifest_path.exists()
    manifest_text = summary.manifest_path.read_text(encoding="utf-8")
    assert "UCDIL — Baseline v2" in manifest_text
    assert "OBS-03 (Act 0.2)" in manifest_text


def test_verify_and_summarize_fails_fast_when_target_circuit_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify `verify_and_summarize` raises `RuntimeError` if target circuit is deleted."""
    monkeypatch.setenv("ENV", "cloud")
    cfg = load_config()
    logger = setup_logger(config=cfg, logger_name="test.stage0.failfast", workspace_root=tmp_path)
    summary = run_stage0_generation(config=cfg, logger=logger, workspace_root=tmp_path)

    # Delete CIR-994821 from SQLite DB to trigger fail-fast verification error
    conn = sqlite3.connect(str(summary.sql.db_path))
    conn.execute("DELETE FROM T_CMDB_CFS_CIRCUIT WHERE CIRCUIT_ID = 'CIR-994821';")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="Active circuit 'CIR-994821' not found"):
        verify_and_summarize(
            base_dir=summary.base_dir,
            config=cfg,
            sql_stats=summary.sql,
            excel_stats=summary.excel,
            pdf_stats=summary.pdf,
            sop_stats=summary.sop,
            manifest_path=summary.manifest_path,
            logger=logger,
            workspace_root=tmp_path,
        )

