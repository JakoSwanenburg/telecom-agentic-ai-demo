"""
Unit Tests for Step 3 (`DT-01b`): Prong 2 Multi-Tab Excel Catalog Dynamic Profiler,
Declarative RML Mapping Generator & Row-Level `pySHACL` Quarantine Gate.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import warnings

import pytest
from rdflib import Dataset, Literal, Namespace, RDF, URIRef, XSD

from src.config_loader import get_workspace_root, load_config
from src.llm_client import resolve_model_for_component
from src.models import (
    ExcelCatalogMappingProposal,
    ExcelColumnMappingSpec,
    ExcelValueMapEntry,
    ExcelWorksheetClassification,
)
from src.state_inspector import inspect_system_state
from src.state_manager import reset_to_clean_slate
from src.track_b.s2_excel_shacl_ingestor import (
    GRAPH_REF_CATALOG,
    GRAPH_TBOX_URI,
    GRAPH_VIRTUAL_IB,
    introspect_excel_workbook,
    run_dt01b_excel_quarantine,
)

TMF_NS = Namespace("http://tmforum.org/sid/")
TELCO_NS = Namespace("http://telco.enterprise.org/ontology/")


def _build_mock_proposal() -> ExcelCatalogMappingProposal:
    """Construct a realistic Gemini-equivalent proposal for the B2B catalog workbook."""
    return ExcelCatalogMappingProposal(
        target_sheet_name="B2B_Enterprise_SLA_Matrix",
        target_class_qname="tmf:ServiceSpecification",
        canonical_iri_template="urn:telco:catalog:spec:{Product_SKU_Code}",
        sku_column_header="Product_SKU_Code",
        header_row_index=5,
        data_start_row_index=6,
        worksheet_classifications=[
            ExcelWorksheetClassification(
                sheet_name="Residential_FTTH_Plans",
                classification="EXCLUDED_DISTRACTOR_TAB",
                rationale="Consumer residential FTTH plans outside B2B Enterprise SLA scope.",
                header_row_index=5,
                data_start_row_index=6,
                banner_rows_detected=[1, 2, 3, 4],
            ),
            ExcelWorksheetClassification(
                sheet_name="B2B_Enterprise_SLA_Matrix",
                classification="TARGET_INGEST_TAB",
                rationale="Authoritative B2B Enterprise SLA catalog matching Use Case Charter.",
                header_row_index=5,
                data_start_row_index=6,
                banner_rows_detected=[1, 2, 3, 4],
            ),
            ExcelWorksheetClassification(
                sheet_name="Deprecated_Legacy_SKUs",
                classification="EXCLUDED_DISTRACTOR_TAB",
                rationale="Obsolete end-of-support legacy SKUs excluded from active catalog.",
                header_row_index=5,
                data_start_row_index=6,
                banner_rows_detected=[1, 2, 3, 4],
            ),
        ],
        column_mappings=[
            ExcelColumnMappingSpec(
                source_column_header="Product_SKU_Code",
                column_index=1,
                mapping_status="MAPPED",
                target_property_qname="tmf:skuCode",
                datatype_qname="xsd:string",
                is_sku_identifier=True,
                rationale="Primary B2B SKU identifier.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Marketing_Name",
                column_index=2,
                mapping_status="MAPPED",
                target_property_qname="tmf:specName",
                datatype_qname="xsd:string",
                rationale="Product display name.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Service_Category",
                column_index=3,
                mapping_status="MAPPED",
                target_property_qname="telco:serviceCategory",
                datatype_qname="xsd:string",
                rationale="B2B service category.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Max_Packet_Loss_Pct",
                column_index=4,
                mapping_status="MAPPED",
                target_property_qname="telco:maxPacketLossPct",
                datatype_qname="xsd:double",
                rationale="Maximum allowed packet loss percentage.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Max_Jitter_ms",
                column_index=5,
                mapping_status="MAPPED",
                target_property_qname="telco:maxJitterMs",
                datatype_qname="xsd:double",
                rationale="Maximum allowed jitter in milliseconds.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="MTTR_Target_Hours",
                column_index=6,
                mapping_status="MAPPED",
                target_property_qname="telco:mttrHours",
                datatype_qname="xsd:double",
                rationale="Mean Time To Repair SLA target.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Eligible_Upgrade_SKU",
                column_index=7,
                mapping_status="MAPPED",
                target_property_qname="telco:eligibleUpgradeSpec",
                is_iri_reference=True,
                iri_reference_template="urn:telco:catalog:spec:{value}",
                rationale="Link to eligible upgrade ServiceSpecification.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Auto_Remediation_Allowed",
                column_index=8,
                mapping_status="MAPPED",
                target_property_qname="telco:autoRemediationAllowed",
                datatype_qname="xsd:boolean",
                value_map=[
                    ExcelValueMapEntry(source_value="YES", target_value="true"),
                    ExcelValueMapEntry(source_value="NO", target_value="false"),
                ],
                rationale="Boolean authorization for autonomous remediation.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Monthly_List_Price_EUR",
                column_index=9,
                mapping_status="EXCLUDED_NOISE",
                rationale="Commercial pricing excluded from technical SLA graph.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Internal_Finance_GL_Code",
                column_index=10,
                mapping_status="EXCLUDED_NOISE",
                rationale="Internal finance general ledger code.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Shadow_Lifecycle_Flag",
                column_index=11,
                mapping_status="MAPPED",
                target_property_qname="telco:lifecycleStatus",
                datatype_qname="xsd:string",
                value_map=[
                    ExcelValueMapEntry(source_value="10_PROD", target_value="ACTIVE"),
                    ExcelValueMapEntry(source_value="20_PILOT", target_value="PILOT"),
                ],
                rationale="Catalog lifecycle status translated from ERP shadow flag.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Min_Contract_Months",
                column_index=12,
                mapping_status="MAPPED",
                target_property_qname="telco:minContractMonths",
                datatype_qname="xsd:integer",
                rationale="Minimum contract commitment in months.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="SLA_Credit_Cap_Pct",
                column_index=13,
                mapping_status="MAPPED",
                target_property_qname="telco:slaCreditCapPct",
                datatype_qname="xsd:double",
                rationale="Maximum SLA penalty credit percentage.",
            ),
            ExcelColumnMappingSpec(
                source_column_header="Engineering_Notes",
                column_index=14,
                mapping_status="MAPPED",
                target_property_qname="rdfs:comment",
                datatype_qname="xsd:string",
                rationale="Optical and operational engineering notes.",
            ),
        ],
        mapping_rationale="B2B Enterprise SLA Matrix mapped to tmf:ServiceSpecification.",
    )


def _setup_isolated_workspace(tmp_path: Path) -> Path:
    """Copy required Stage 0/2/3 inputs into an isolated temporary workspace."""
    repo_root = get_workspace_root()
    files_to_copy = [
        "config.yaml",
        "data/raw_sources/uc001_use_case_charter.md",
        "data/raw_sources/excel/Telco_Master_Product_SLA_Catalog_2026.xlsx",
        "data/semantic_store/tbox_sid_etom.ttl",
        "data/semantic_store/knowledge_graph.trig",
        "shapes/service_spec_shape.ttl",
        "prompts/s2_excel_catalog_profiler_prompt.md",
        "reports/hitl_gate1_ontology_mapping_review.html",
        "config/mcp_primitives_catalog.json",
    ]
    for rel in files_to_copy:
        src = repo_root / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


def test_zero_hardcoded_excel_tab_or_column_names() -> None:
    """Verify s2_excel_shacl_ingestor.py contains zero hardcoded tab names or headers."""
    source_path = get_workspace_root() / "src" / "track_b" / "s2_excel_shacl_ingestor.py"
    source_text = source_path.read_text(encoding="utf-8")

    forbidden_literals = [
        "B2B_Enterprise_SLA_Matrix",
        "Residential_FTTH_Plans",
        "Deprecated_Legacy_SKUs",
        "Product_SKU_Code",
        "Max_Packet_Loss_Pct",
        "Internal_Finance_GL_Code",
        "Shadow_Lifecycle_Flag",
        "Auto_Remediation_Allowed",
        "SLA_Credit_Cap_Pct",
        "Min_Contract_Months",
    ]
    for literal in forbidden_literals:
        assert literal not in source_text, (
            f"Hardcoded Excel identifier '{literal}' found in s2_excel_shacl_ingestor.py"
        )


def test_resolve_model_for_component_supports_per_component_overrides() -> None:
    """Verify shared llm_client resolves distinct models per component with fallback."""
    config = load_config()
    assert resolve_model_for_component(config, "track_b_excel_profiler") == "gemini-3.8-flash"
    assert resolve_model_for_component(config, "unlisted_component") == config.ai.model_name

    overridden_ai = config.ai.model_copy(
        update={"component_models": {"track_b_excel_profiler": "gemini-3.8-pro"}}
    )
    overridden_cfg = config.model_copy(update={"ai": overridden_ai})
    assert resolve_model_for_component(overridden_cfg, "track_b_excel_profiler") == "gemini-3.8-pro"
    assert resolve_model_for_component(overridden_cfg, "track_b_cmdb_profiler") == config.ai.model_name


def test_dt01b_fails_fast_when_dt01a_prerequisites_missing(tmp_path: Path) -> None:
    """Verify DT-01b fails fast if Step 2 artifacts are missing or not LOCKED_APPROVED."""
    config = load_config()
    logger = logging.getLogger("test_dt01b_prereq")

    with pytest.raises(FileNotFoundError, match="DT-01a"):
        run_dt01b_excel_quarantine(config=config, logger=logger, root_dir=tmp_path)

    ws = _setup_isolated_workspace(tmp_path)
    gate1_path = ws / config.track_b_ingestion_and_er.hitl_gate1_report_path
    gate1_path.write_text("<html><body>CANDIDATE_PROPOSED</body></html>", encoding="utf-8")

    with pytest.raises(RuntimeError, match="LOCKED_APPROVED"):
        run_dt01b_excel_quarantine(config=config, logger=logger, root_dir=ws)


def test_dt01b_dynamic_introspection_and_pyshacl_quarantine_e2e(tmp_path: Path) -> None:
    """
    Verify end-to-end DT-01b execution:
      - Dynamic openpyxl introspection detects 3 tabs
      - Mocked Gemini client returns ExcelCatalogMappingProposal
      - 18 valid B2B SKUs promoted into <urn:telco:graph:ref:catalog>
      - 2 dirty rows deterministically quarantined across 3 SHACL constraints
      - <urn:telco:graph:virtual:ib> remains at 0 triples
      - SYS-01 transitions Element 3 to LOADED_WITH_QUARANTINE and DT-00 resets it
    """
    ws = _setup_isolated_workspace(tmp_path)
    config = load_config()
    logger = logging.getLogger("test_dt01b_e2e")

    excel_path = (
        ws
        / config.paths.raw_sources_dir
        / config.paths.excel_subdir
        / config.stage0.excel_catalog_filename
    )
    introspection = introspect_excel_workbook(excel_path)
    assert introspection.sheet_count == 3
    assert len(introspection.sheets[1].preview_rows) == 10

    mock_proposal = _build_mock_proposal()
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = SimpleNamespace(
        text=mock_proposal.model_dump_json()
    )

    with patch(
        "src.track_b.s2_excel_shacl_ingestor.create_genai_client",
        return_value=mock_client,
    ):
        result = run_dt01b_excel_quarantine(config=config, logger=logger, root_dir=ws)

    assert result.target_sheet_name == "B2B_Enterprise_SLA_Matrix"
    assert result.excluded_distractor_tabs_count == 2
    assert result.total_data_rows_evaluated == 20
    assert result.valid_skus_loaded_count == 18
    assert result.quarantined_rows_count == 2
    assert result.virtual_ib_triples_count == 0
    assert result.catalog_triples_materialized > 0
    assert result.rml_mapping_path.exists()
    assert result.quarantine_html_report_path.exists()
    assert result.quarantine_markdown_report_path.exists()
    assert result.quarantine_summary_json_path.exists()

    # Verify TriG store contents
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(result.trig_dataset_path), format="trig")

    assert len(ds.graph(GRAPH_TBOX_URI)) > 0
    assert len(ds.graph(GRAPH_VIRTUAL_IB)) == 0
    catalog_graph = ds.graph(GRAPH_REF_CATALOG)
    specs = set(catalog_graph.subjects(RDF.type, TMF_NS.ServiceSpecification))
    assert len(specs) == 18

    eth10g = URIRef("urn:telco:catalog:spec:ETH-10G-GOLD")
    assert eth10g in specs
    assert (eth10g, TELCO_NS.maxPacketLossPct, Literal(0.1, datatype=XSD.double)) in catalog_graph
    assert (eth10g, TELCO_NS.autoRemediationAllowed, Literal(True, datatype=XSD.boolean)) in catalog_graph
    assert (eth10g, TELCO_NS.lifecycleStatus, Literal("ACTIVE")) in catalog_graph

    # Ensure quarantined SKUs never entered <urn:telco:graph:ref:catalog>
    assert URIRef("urn:telco:catalog:spec:DARK-FIBER-METRO-X") not in specs
    assert URIRef("urn:telco:catalog:spec:SDWAN-LEGACY-99") not in specs

    # Verify both quarantined rows and multi-constraint violations
    quarantined_skus = {q.sku_code: q for q in result.quarantined_rows}
    assert set(quarantined_skus.keys()) == {"DARK-FIBER-METRO-X", "SDWAN-LEGACY-99"}
    for qrow in quarantined_skus.values():
        assert "maxPacketLossPct" in (qrow.result_path or "")
        assert "autoRemediationAllowed" in (qrow.result_path or "")
        assert "lifecycleStatus" in (qrow.result_path or "")

    # Verify SYS-01 Element 3 status
    sys_report = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    elem3 = next(e for e in sys_report.elements if e.element_number == 3)
    assert elem3.state == "LOADED_WITH_QUARANTINE"
    assert "Valid B2B SKUs loaded: 18" in elem3.metrics_summary
    assert "Excluded distractor tabs: 2" in elem3.metrics_summary
    assert "pySHACL quarantined rows: 2" in elem3.metrics_summary

    # Verify DT-00 reset cleans Step 3 artifacts and resets Element 3 to EMPTY
    reset_to_clean_slate(config=config, logger=logger, workspace_root=ws)
    assert not result.rml_mapping_path.exists()
    assert not result.quarantine_html_report_path.exists()
    assert not result.quarantine_summary_json_path.exists()
    sys_after_reset = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    elem3_after = next(e for e in sys_after_reset.elements if e.element_number == 3)
    assert elem3_after.state == "EMPTY"
