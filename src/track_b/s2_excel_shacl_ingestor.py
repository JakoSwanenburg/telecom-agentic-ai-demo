"""
Scenario `DT-01b` — 100% Workbook-Schema & Use-Case Independent Prong 2 Multi-Tab
Excel Catalog Dynamic Profiler, Declarative RML Mapping Generator & Row-Level
`pySHACL` Quarantine Gate (`src/track_b/s2_excel_shacl_ingestor.py`).

Architectural Invariants (`IMP-005`):
  1. Zero hardcoded worksheet tab names or Excel column headers exist in this module.
  2. Fails fast if Step 2 (`DT-01a`) locked artifacts or `LOCKED_APPROVED` status are
     missing; never auto-executes `DT-01a`.
  3. Dynamically introspects the workbook with `openpyxl` (all tabs, merged cell
     ranges, and first 10 preview rows) and invokes Gemini via `src/llm_client.py`
     with zero heuristic fallback.
  4. Materializes each data row into an isolated `rdflib.Graph` and validates it
     individually via `pyshacl.validate()` against `shapes/service_spec_shape.ttl`.
  5. Idempotently repopulates `<urn:telco:graph:ref:catalog>` in
     `data/semantic_store/knowledge_graph.trig` with valid rows while keeping
     `<urn:telco:graph:tbox:sid-etom>` intact and `<urn:telco:graph:virtual:ib>` at 0
     persisted triples.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"^google\.genai\.")
    from google.genai import types as genai_types
import openpyxl
import pyshacl
from rdflib import Dataset, Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD
from rdflib.namespace import OWL, SH, SKOS
import yaml

from src.config_loader import get_workspace_root
from src.llm_client import (
    create_genai_client,
    resolve_model_for_component,
    strip_unsupported_vertex_schema_keys,
)
from src.models import (
    AppConfig,
    Dt01bExecutionResult,
    ExcelCatalogMappingProposal,
    ExcelColumnMappingSpec,
    ExcelSheetIntrospection,
    ExcelWorkbookIntrospection,
    PromotedSkuSummary,
    QuarantinedRowRecord,
    ShaclQuarantineSummary,
)

GRAPH_TBOX_URI = URIRef("urn:telco:graph:tbox:sid-etom")
GRAPH_REF_CATALOG = URIRef("urn:telco:graph:ref:catalog")
GRAPH_VIRTUAL_IB = URIRef("urn:telco:graph:virtual:ib")

DEFAULT_PREFIXES: Dict[str, Namespace] = {
    "tmf": Namespace("http://tmforum.org/sid/"),
    "telco": Namespace("http://telco.enterprise.org/ontology/"),
    "rdfs": RDFS,
    "rdf": RDF,
    "owl": OWL,
    "skos": SKOS,
    "xsd": XSD,
}


# ============================================================================
# 1. Fail-Fast Step 2 (`DT-01a`) Pre-Condition Verification
# ============================================================================
def validate_dt01a_prerequisites(config: AppConfig, root_dir: Path) -> None:
    """
    Verify all Step 2 (`DT-01a`) locked artifacts exist and HITL Gate 1 is
    `LOCKED_APPROVED`. Fails fast with explicit operator guidance if missing.
    """
    tbox_path = root_dir / Path(config.layer4_compiler_federation.tbox_path)
    trig_path = root_dir / Path(config.layer4_compiler_federation.dataset_trig_path)
    shape_path = (
        root_dir
        / Path(config.layer4_compiler_federation.shapes_dir)
        / "service_spec_shape.ttl"
    )
    gate1_report_path = root_dir / Path(config.track_b_ingestion_and_er.hitl_gate1_report_path)

    missing_files = [
        str(path)
        for path in (tbox_path, trig_path, shape_path, gate1_report_path)
        if not path.exists()
    ]
    if missing_files:
        raise FileNotFoundError(
            "DT-01b prerequisite check failed: missing Step 2 (DT-01a) artifacts: "
            f"{missing_files}. Run and approve DT-01a first: "
            "`python scripts/run_dt01a_cmdb_gate1.py --mode approve`."
        )

    gate1_html = gate1_report_path.read_text(encoding="utf-8")
    if "LOCKED_APPROVED" not in gate1_html:
        raise RuntimeError(
            "DT-01b prerequisite check failed: HITL Gate 1 is not LOCKED_APPROVED in "
            f"{gate1_report_path}. Approve DT-01a first: "
            "`python scripts/run_dt01a_cmdb_gate1.py --mode approve`."
        )


# ============================================================================
# 2. Dynamic Multi-Tab Excel Workbook Introspection (Zero Hardcoding)
# ============================================================================
def introspect_excel_workbook(
    excel_path: Path,
    preview_row_limit: int = 10,
) -> ExcelWorkbookIntrospection:
    """
    Dynamically inspect all worksheets, merged cell ranges, and first N rows of
    an Excel workbook using `openpyxl` without assuming any sheet names or columns.
    """
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel catalog workbook not found: {excel_path}")

    wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=False)
    try:
        sheets_info: List[ExcelSheetIntrospection] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            max_row = ws.max_row or 0
            max_col = ws.max_column or 0
            merged_ranges = [str(rng) for rng in ws.merged_cells.ranges]

            preview_rows: List[List[str]] = []
            rows_to_read = min(preview_row_limit, max_row)
            for row_idx in range(1, rows_to_read + 1):
                row_values: List[str] = []
                for col_idx in range(1, max_col + 1):
                    cell_val = ws.cell(row=row_idx, column=col_idx).value
                    row_values.append("" if cell_val is None else str(cell_val).strip())
                preview_rows.append(row_values)

            sheets_info.append(
                ExcelSheetIntrospection(
                    sheet_name=sheet_name,
                    max_row=max_row,
                    max_col=max_col,
                    merged_cell_ranges=merged_ranges,
                    preview_rows=preview_rows,
                )
            )

        return ExcelWorkbookIntrospection(
            workbook_path=str(excel_path),
            sheet_count=len(sheets_info),
            sheets=sheets_info,
        )
    finally:
        wb.close()


# ============================================================================
# 3. Gemini AI Excel Profiler & Declarative RML Mapping Generator
# ============================================================================
def profile_excel_catalog_via_llm(
    introspection: ExcelWorkbookIntrospection,
    use_case_charter_text: str,
    tbox_turtle_text: str,
    config: AppConfig,
    logger: logging.Logger,
    prompt_template_text: Optional[str] = None,
) -> Tuple[ExcelCatalogMappingProposal, str]:
    """
    Invoke Gemini (`google-genai` via `src/llm_client.py`) with:
      1. Use Case Charter markdown
      2. Locked Conceptual TBox (`tbox_sid_etom.ttl`)
      3. Dynamic `ExcelWorkbookIntrospection` JSON
    to synthesize a validated `ExcelCatalogMappingProposal`. Zero heuristic fallback.
    """
    if prompt_template_text is None:
        prompt_path = get_workspace_root() / Path(
            config.track_b_ingestion_and_er.excel_profiler_prompt_template_path
        )
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Excel profiler prompt template not found: {prompt_path}"
            )
        prompt_template_text = prompt_path.read_text(encoding="utf-8")

    client = create_genai_client(config, logger)
    model_id = resolve_model_for_component(config, "track_b_excel_profiler")

    user_payload = (
        f"{prompt_template_text}\n\n"
        f"=== INPUT 1: USE CASE CHARTER (`{config.use_case.use_case_id}`) ===\n"
        f"{use_case_charter_text}\n\n"
        f"=== INPUT 2: LOCKED CONCEPTUAL TBOX (`tbox_sid_etom.ttl`) ===\n"
        f"{tbox_turtle_text}\n\n"
        f"=== INPUT 3: DYNAMICALLY INTROSPECTED EXCEL WORKBOOK ===\n"
        f"{json.dumps(introspection.model_dump(), indent=2)}\n"
    )

    clean_response_schema = strip_unsupported_vertex_schema_keys(
        ExcelCatalogMappingProposal.model_json_schema()
    )

    logger.info(
        "Invoking Gemini Excel Catalog Profiler (model=%s) across %d worksheets...",
        model_id,
        introspection.sheet_count,
    )
    response = client.models.generate_content(
        model=model_id,
        contents=user_payload,
        config=genai_types.GenerateContentConfig(
            temperature=config.ai.temperature,
            response_mime_type="application/json",
            response_schema=clean_response_schema,
        ),
    )

    if not response.text or not response.text.strip():
        raise RuntimeError(
            "Gemini Excel Catalog Profiler returned an empty response; failing fast."
        )

    proposal = ExcelCatalogMappingProposal.model_validate_json(response.text)
    _validate_proposal_against_introspection(proposal, introspection)
    return proposal, model_id


def _validate_proposal_against_introspection(
    proposal: ExcelCatalogMappingProposal,
    introspection: ExcelWorkbookIntrospection,
) -> None:
    """Ensure the LLM proposal references an actual introspected sheet and valid row indices."""
    sheet_names = {sheet.sheet_name for sheet in introspection.sheets}
    if proposal.target_sheet_name not in sheet_names:
        raise ValueError(
            f"Proposal target_sheet_name '{proposal.target_sheet_name}' does not exist "
            f"in workbook sheets: {sorted(sheet_names)}"
        )
    if proposal.data_start_row_index <= proposal.header_row_index:
        raise ValueError(
            f"Invalid row indices: data_start_row_index ({proposal.data_start_row_index}) "
            f"must be > header_row_index ({proposal.header_row_index})."
        )
    mapped_skus = [c for c in proposal.column_mappings if c.is_sku_identifier]
    if not mapped_skus:
        raise ValueError(
            "Proposal must designate at least one column with `is_sku_identifier=True`."
        )


def write_excel_catalog_rml_yaml(
    proposal: ExcelCatalogMappingProposal,
    workbook_rel_path: str,
    model_used: str,
    output_path: Path,
) -> None:
    """Persist the declarative Excel-to-RDF RML mapping specification to YAML."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rml_doc = {
        "mapping_id": "excel_catalog_rml_v1",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_used": model_used,
        "source_workbook": workbook_rel_path,
        "target_named_graph": str(GRAPH_REF_CATALOG),
        "target_sheet_name": proposal.target_sheet_name,
        "header_row_index": proposal.header_row_index,
        "data_start_row_index": proposal.data_start_row_index,
        "target_class_qname": proposal.target_class_qname,
        "canonical_iri_template": proposal.canonical_iri_template,
        "sku_column_header": proposal.sku_column_header,
        "prefixes": {prefix: str(ns) for prefix, ns in DEFAULT_PREFIXES.items()},
        "worksheet_classifications": [
            wc.model_dump() for wc in proposal.worksheet_classifications
        ],
        "column_mappings": [cm.model_dump() for cm in proposal.column_mappings],
        "mapping_rationale": proposal.mapping_rationale,
    }
    output_path.write_text(
        yaml.safe_dump(rml_doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


# ============================================================================
# 4. Row-Level RDF Materialization & Deterministic `pySHACL` Quarantine Gate
# ============================================================================
def _extract_tbox_prefixes(tbox_graph: Graph) -> Dict[str, Namespace]:
    """Build prefix lookup table from DEFAULT_PREFIXES plus namespaces bound in TBox."""
    prefixes: Dict[str, Namespace] = dict(DEFAULT_PREFIXES)
    for prefix, uri in tbox_graph.namespace_manager.namespaces():
        if prefix:
            prefixes[str(prefix)] = Namespace(str(uri))
    return prefixes


def _resolve_qname(qname: str, prefixes: Dict[str, Namespace]) -> URIRef:
    """Resolve a QName (e.g. `tmf:ServiceSpecification`) or full IRI into a URIRef."""
    cleaned = qname.strip()
    if cleaned.startswith("http://") or cleaned.startswith("https://") or cleaned.startswith("urn:"):
        return URIRef(cleaned)
    if ":" not in cleaned:
        raise ValueError(f"Invalid QName or IRI '{qname}': missing prefix separator.")
    prefix, local_name = cleaned.split(":", 1)
    if prefix not in prefixes:
        raise ValueError(
            f"Unknown prefix '{prefix}' in QName '{qname}'. Known prefixes: {sorted(prefixes)}"
        )
    return prefixes[prefix][local_name]


def _coerce_typed_literal(raw_value: Any, datatype_qname: Optional[str]) -> Literal:
    """Coerce an Excel cell value into a strongly-typed rdflib Literal for SHACL validation."""
    text_val = str(raw_value).strip()
    dt = (datatype_qname or "xsd:string").strip()

    if dt in {"xsd:double", "xsd:decimal", "xsd:float"}:
        numeric_text = text_val.rstrip("%").strip()
        try:
            float_val = float(numeric_text)
        except ValueError:
            return Literal(text_val)
        target_dt = XSD.double if dt == "xsd:double" else (
            XSD.decimal if dt == "xsd:decimal" else XSD.float
        )
        return Literal(float_val, datatype=target_dt)

    if dt in {"xsd:integer", "xsd:int"}:
        try:
            int_val = int(float(text_val))
        except ValueError:
            return Literal(text_val)
        return Literal(int_val, datatype=XSD.integer)

    if dt == "xsd:boolean":
        lowered = text_val.lower()
        if lowered in {"true", "1", "yes", "y"}:
            return Literal(True, datatype=XSD.boolean)
        if lowered in {"false", "0", "no", "n"}:
            return Literal(False, datatype=XSD.boolean)
        return Literal(text_val)

    return Literal(text_val)


def _extract_shacl_violation_details(
    results_graph: Graph,
    results_text: str,
    subject_iri: URIRef,
) -> Tuple[str, str, Optional[str], str]:
    """Extract all violated constraint components, paths, and messages from pySHACL output."""
    constraints: List[str] = []
    paths: List[str] = []
    messages: List[str] = []
    focus_str = str(subject_iri)

    for result_node in results_graph.subjects(RDF.type, SH.ValidationResult):
        constraint = results_graph.value(result_node, SH.sourceConstraintComponent)
        focus = results_graph.value(result_node, SH.focusNode)
        path = results_graph.value(result_node, SH.resultPath)
        message = results_graph.value(result_node, SH.resultMessage)
        if focus:
            focus_str = str(focus)
        if constraint and str(constraint) not in constraints:
            constraints.append(str(constraint))
        if path and str(path) not in paths:
            paths.append(str(path))
        if message and str(message) not in messages:
            messages.append(str(message))

    if constraints or messages:
        return (
            "; ".join(constraints) if constraints else "sh:ValidationConstraint",
            focus_str,
            "; ".join(paths) if paths else None,
            "; ".join(messages) if messages else results_text.strip(),
        )
    return (
        "sh:ValidationConstraint",
        focus_str,
        None,
        results_text.strip() or "SHACL validation failed.",
    )


def materialize_and_quarantine_excel_rows(
    excel_path: Path,
    proposal: ExcelCatalogMappingProposal,
    tbox_path: Path,
    shape_path: Path,
    logger: logging.Logger,
) -> Tuple[Graph, List[PromotedSkuSummary], List[QuarantinedRowRecord]]:
    """
    Iterate row-by-row over the target Excel worksheet, construct a candidate RDF
    graph per row, validate individually via `pyshacl.validate()`, and partition into
    promoted triples vs. quarantined row records.
    """
    tbox_graph = Graph()
    tbox_graph.parse(str(tbox_path), format="turtle")
    prefixes = _extract_tbox_prefixes(tbox_graph)

    shapes_graph = Graph()
    shapes_graph.parse(str(shape_path), format="turtle")

    promoted_graph = Graph()
    for prefix, ns in prefixes.items():
        promoted_graph.bind(prefix, ns)

    promoted_skus: List[PromotedSkuSummary] = []
    quarantined_rows: List[QuarantinedRowRecord] = []

    target_class_uri = _resolve_qname(proposal.target_class_qname, prefixes)
    mapped_columns: List[ExcelColumnMappingSpec] = [
        col for col in proposal.column_mappings if col.mapping_status == "MAPPED"
    ]
    sku_col = next(
        (col for col in proposal.column_mappings if col.is_sku_identifier),
        None,
    )
    if sku_col is None:
        raise ValueError("No SKU identifier column found in proposal.column_mappings.")

    wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=False)
    try:
        ws = wb[proposal.target_sheet_name]
        for row_idx in range(proposal.data_start_row_index, (ws.max_row or 0) + 1):
            raw_row_values: Dict[str, Any] = {}
            non_empty = False
            for col in proposal.column_mappings:
                cell_val = ws.cell(row=row_idx, column=col.column_index).value
                if cell_val is not None and str(cell_val).strip() != "":
                    non_empty = True
                raw_row_values[col.source_column_header] = (
                    None if cell_val is None else (
                        cell_val if isinstance(cell_val, (int, float, bool)) else str(cell_val).strip()
                    )
                )

            if not non_empty:
                continue

            raw_sku = raw_row_values.get(sku_col.source_column_header)
            sku_str = str(raw_sku).strip() if raw_sku is not None else f"ROW_{row_idx}"
            subject_iri_str = proposal.canonical_iri_template.replace(
                f"{{{proposal.sku_column_header}}}", sku_str
            ).replace("{value}", sku_str)
            subject_iri = URIRef(subject_iri_str)

            row_graph = Graph()
            for prefix, ns in prefixes.items():
                row_graph.bind(prefix, ns)
            row_graph.add((subject_iri, RDF.type, target_class_uri))

            parsed_packet_loss: Optional[float] = None
            parsed_availability: Optional[float] = None
            parsed_lifecycle: Optional[str] = None
            parsed_auto_remediation: Optional[bool] = None

            for col in mapped_columns:
                if not col.target_property_qname:
                    continue
                cell_val = raw_row_values.get(col.source_column_header)
                if cell_val is None or str(cell_val).strip() == "":
                    continue

                prop_uri = _resolve_qname(col.target_property_qname, prefixes)
                if col.is_iri_reference and col.iri_reference_template:
                    target_ref = URIRef(
                        col.iri_reference_template.replace("{value}", str(cell_val).strip())
                    )
                    row_graph.add((subject_iri, prop_uri, target_ref))
                else:
                    effective_val: Any = cell_val
                    if col.value_map:
                        lookup = {entry.source_value: entry.target_value for entry in col.value_map}
                        effective_val = lookup.get(str(cell_val).strip(), str(cell_val).strip())
                    lit = _coerce_typed_literal(effective_val, col.datatype_qname)
                    row_graph.add((subject_iri, prop_uri, lit))

                    if col.target_property_qname == "telco:maxPacketLossPct" and isinstance(
                        lit.toPython(), float
                    ):
                        parsed_packet_loss = float(lit.toPython())
                    elif col.target_property_qname == "telco:availabilityTargetPct" and isinstance(
                        lit.toPython(), float
                    ):
                        parsed_availability = float(lit.toPython())
                    elif col.target_property_qname == "telco:lifecycleStatus":
                        parsed_lifecycle = str(lit)
                    elif col.target_property_qname == "telco:autoRemediationAllowed" and isinstance(
                        lit.toPython(), bool
                    ):
                        parsed_auto_remediation = bool(lit.toPython())

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
                conforms, results_graph, results_text = pyshacl.validate(
                    data_graph=row_graph,
                    shacl_graph=shapes_graph,
                    ont_graph=tbox_graph,
                    inference="none",
                    abort_on_first=False,
                    meta_shacl=False,
                    advanced=False,
                    js=False,
                )

            if conforms:
                for triple in row_graph:
                    promoted_graph.add(triple)
                promoted_skus.append(
                    PromotedSkuSummary(
                        excel_row_number=row_idx,
                        sku_code=sku_str,
                        subject_iri=str(subject_iri),
                        triple_count=len(row_graph),
                        max_packet_loss_pct=parsed_packet_loss,
                        availability_target_pct=parsed_availability,
                        lifecycle_status=parsed_lifecycle,
                        auto_remediation_allowed=parsed_auto_remediation,
                    )
                )
            else:
                constraint_comp, focus_node, result_path, shacl_msg = (
                    _extract_shacl_violation_details(results_graph, results_text, subject_iri)
                )
                logger.warning(
                    "pySHACL QUARANTINE row=%d sku=%s constraint=%s msg=%s",
                    row_idx,
                    sku_str,
                    constraint_comp,
                    shacl_msg,
                )
                quarantined_rows.append(
                    QuarantinedRowRecord(
                        excel_row_number=row_idx,
                        sku_code=sku_str if raw_sku is not None else None,
                        raw_row_values=raw_row_values,
                        violated_constraint_component=constraint_comp,
                        focus_node=focus_node,
                        result_path=result_path,
                        shacl_message=shacl_msg,
                        shacl_report_text=results_text.strip(),
                    )
                )
    finally:
        wb.close()

    return promoted_graph, promoted_skus, quarantined_rows


def update_knowledge_graph_catalog(
    trig_path: Path,
    promoted_graph: Graph,
) -> Tuple[int, int]:
    """
    Idempotently clear and repopulate `<urn:telco:graph:ref:catalog>` inside
    `knowledge_graph.trig`, preserving `<urn:telco:graph:tbox:sid-etom>` and
    verifying `<urn:telco:graph:virtual:ib>` stays at 0 persisted triples.
    """
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(trig_path), format="trig")

    for prefix, uri in promoted_graph.namespace_manager.namespaces():
        ds.bind(prefix, uri)

    ds.remove((None, None, None, GRAPH_REF_CATALOG))
    catalog_ctx = ds.graph(GRAPH_REF_CATALOG)
    for triple in promoted_graph:
        catalog_ctx.add(triple)

    virtual_ib_count = len(ds.graph(GRAPH_VIRTUAL_IB))
    if virtual_ib_count != 0:
        raise RuntimeError(
            f"Invariant violation: <{GRAPH_VIRTUAL_IB}> must remain at 0 persisted triples, "
            f"found {virtual_ib_count}."
        )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.serialize(destination=str(trig_path), format="trig")
    return len(catalog_ctx), virtual_ib_count


# ============================================================================
# 5. Quarantine & Audit Reports (HTML, Markdown, Machine-Readable JSON)
# ============================================================================
def write_quarantine_reports(
    proposal: ExcelCatalogMappingProposal,
    summary: ShaclQuarantineSummary,
    promoted_skus: List[PromotedSkuSummary],
    html_path: Path,
    md_path: Path,
    json_path: Path,
) -> None:
    """Write HTML, Markdown, and JSON audit reports for Scenario `DT-01b`."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    # Markdown report
    md_lines: List[str] = [
        "# Scenario DT-01b: Prong 2 Excel Catalog & Row-Level `pySHACL` Quarantine Report",
        "",
        f"- **Executed At (UTC):** `{summary.executed_at_utc}`",
        f"- **Workbook:** `{summary.workbook_path}`",
        f"- **Target Worksheet:** `{summary.target_sheet_name}` (Header Row: `{summary.header_row_index}`, Data Start Row: `{summary.data_start_row_index}`)",
        f"- **Excluded Distractor Tabs:** `{summary.excluded_distractor_tabs_count}` (`{', '.join(summary.excluded_distractor_tabs)}`)",
        f"- **Valid B2B SKUs Promoted:** `{summary.valid_skus_loaded_count}` (`{summary.catalog_triples_materialized}` triples in `<urn:telco:graph:ref:catalog>`)",
        f"- **Quarantined Rows Blocked:** `{summary.quarantined_rows_count}`",
        f"- **Persisted Triples in `<urn:telco:graph:virtual:ib>`:** `{summary.virtual_ib_triples_count}`",
        "",
        "## (a) Worksheet Tab & Banner Filtering Audit",
        "",
        "| Worksheet | Classification | Header Row | Data Start Row | Banner Rows | Rationale |",
        "|---|---|---:|---:|---|---|",
    ]
    for wc in proposal.worksheet_classifications:
        md_lines.append(
            f"| `{wc.sheet_name}` | `{wc.classification}` | "
            f"{wc.header_row_index or '-'} | {wc.data_start_row_index or '-'} | "
            f"{wc.banner_rows_detected or '-'} | {wc.rationale} |"
        )

    md_lines.extend([
        "",
        "## (b) Column-to-TBox RML Mapping Table",
        "",
        "| Col # | Source Column Header | Status | Target Property | Datatype | Notes |",
        "|---:|---|---|---|---|---|",
    ])
    for cm in proposal.column_mappings:
        md_lines.append(
            f"| {cm.column_index} | `{cm.source_column_header}` | `{cm.mapping_status}` | "
            f"`{cm.target_property_qname or '-'}` | `{cm.datatype_qname or '-'}` | {cm.rationale} |"
        )

    md_lines.extend([
        "",
        f"## (c) Promoted B2B SKUs Summary ({len(promoted_skus)} Valid SKUs)",
        "",
        "| Excel Row | SKU Code | Subject IRI | Triples | Max Packet Loss % | Availability % | Auto-Remediation | Lifecycle |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ])
    for sku in promoted_skus:
        md_lines.append(
            f"| {sku.excel_row_number} | `{sku.sku_code}` | `{sku.subject_iri}` | {sku.triple_count} | "
            f"{sku.max_packet_loss_pct if sku.max_packet_loss_pct is not None else '-'} | "
            f"{sku.availability_target_pct if sku.availability_target_pct is not None else '-'} | "
            f"{sku.auto_remediation_allowed if sku.auto_remediation_allowed is not None else '-'} | "
            f"`{sku.lifecycle_status or '-'}` |"
        )

    md_lines.extend([
        "",
        f"## (d) Detailed `pySHACL` Row Quarantine Table ({len(summary.quarantined_rows)} Quarantined Rows)",
        "",
        "| Excel Row | SKU Code | Violated SHACL Constraint | Result Path | SHACL Message | Raw Values |",
        "|---:|---|---|---|---|---|",
    ])
    for qrow in summary.quarantined_rows:
        md_lines.append(
            f"| {qrow.excel_row_number} | `{qrow.sku_code or '-'}` | "
            f"`{qrow.violated_constraint_component}` | `{qrow.result_path or '-'}` | "
            f"{qrow.shacl_message} | `{json.dumps(qrow.raw_row_values)}` |"
        )

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # HTML report
    tab_rows_html = "\n".join(
        f"<tr><td><code>{html.escape(wc.sheet_name)}</code></td>"
        f"<td><strong>{html.escape(wc.classification)}</strong></td>"
        f"<td>{wc.header_row_index or '-'}</td>"
        f"<td>{wc.data_start_row_index or '-'}</td>"
        f"<td>{html.escape(str(wc.banner_rows_detected))}</td>"
        f"<td>{html.escape(wc.rationale)}</td></tr>"
        for wc in proposal.worksheet_classifications
    )
    col_rows_html = "\n".join(
        f"<tr><td>{cm.column_index}</td>"
        f"<td><code>{html.escape(cm.source_column_header)}</code></td>"
        f"<td><code>{html.escape(cm.mapping_status)}</code></td>"
        f"<td><code>{html.escape(cm.target_property_qname or '-')}</code></td>"
        f"<td><code>{html.escape(cm.datatype_qname or '-')}</code></td>"
        f"<td>{html.escape(cm.rationale)}</td></tr>"
        for cm in proposal.column_mappings
    )
    promoted_rows_html = "\n".join(
        f"<tr><td>{sku.excel_row_number}</td>"
        f"<td><code>{html.escape(sku.sku_code)}</code></td>"
        f"<td><code>{html.escape(sku.subject_iri)}</code></td>"
        f"<td>{sku.triple_count}</td>"
        f"<td>{sku.max_packet_loss_pct if sku.max_packet_loss_pct is not None else '-'}</td>"
        f"<td>{sku.availability_target_pct if sku.availability_target_pct is not None else '-'}</td>"
        f"<td>{sku.auto_remediation_allowed if sku.auto_remediation_allowed is not None else '-'}</td>"
        f"<td><code>{html.escape(sku.lifecycle_status or '-')}</code></td></tr>"
        for sku in promoted_skus
    )
    quarantine_rows_html = "\n".join(
        f"<tr><td>{qrow.excel_row_number}</td>"
        f"<td><code>{html.escape(qrow.sku_code or '-')}</code></td>"
        f"<td><code>{html.escape(qrow.violated_constraint_component)}</code></td>"
        f"<td><code>{html.escape(qrow.result_path or '-')}</code></td>"
        f"<td>{html.escape(qrow.shacl_message)}</td>"
        f"<td><pre>{html.escape(json.dumps(qrow.raw_row_values, indent=2))}</pre></td>"
        f"<td><pre>{html.escape(qrow.shacl_report_text)}</pre></td></tr>"
        for qrow in summary.quarantined_rows
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>DT-01b Prong 2 Excel Catalog &amp; pySHACL Quarantine Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    h1, h2 {{ color: #0f172a; }}
    .metrics {{ background: #f8fafc; border: 1px solid #cbd5e1; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e2e8f0; }}
    pre {{ margin: 0; white-space: pre-wrap; font-size: 11px; }}
  </style>
</head>
<body>
  <h1>Scenario DT-01b: Prong 2 Excel Catalog &amp; Row-Level pySHACL Quarantine Report</h1>
  <div class="metrics">
    <p><strong>Executed At (UTC):</strong> <code>{html.escape(summary.executed_at_utc)}</code></p>
    <p><strong>Target Worksheet:</strong> <code>{html.escape(summary.target_sheet_name)}</code>
       (Header Row: {summary.header_row_index}, Data Start Row: {summary.data_start_row_index})</p>
    <p><strong>Excluded Distractor Tabs:</strong> {summary.excluded_distractor_tabs_count}
       (<code>{html.escape(', '.join(summary.excluded_distractor_tabs))}</code>)</p>
    <p><strong>Valid B2B SKUs Promoted:</strong> {summary.valid_skus_loaded_count}
       ({summary.catalog_triples_materialized} triples in <code>&lt;urn:telco:graph:ref:catalog&gt;</code>)</p>
    <p><strong>Quarantined Rows Blocked:</strong> {summary.quarantined_rows_count}</p>
    <p><strong>Virtual IB Persisted Triples:</strong> {summary.virtual_ib_triples_count}</p>
  </div>

  <h2>(a) Worksheet Tab &amp; Banner Filtering Audit</h2>
  <table>
    <thead><tr><th>Worksheet</th><th>Classification</th><th>Header Row</th><th>Data Start Row</th><th>Banner Rows</th><th>Rationale</th></tr></thead>
    <tbody>{tab_rows_html}</tbody>
  </table>

  <h2>(b) Column-to-TBox RML Mapping Table</h2>
  <table>
    <thead><tr><th>Col #</th><th>Source Header</th><th>Status</th><th>Target Property</th><th>Datatype</th><th>Rationale</th></tr></thead>
    <tbody>{col_rows_html}</tbody>
  </table>

  <h2>(c) Promoted B2B SKUs Summary ({len(promoted_skus)} Valid SKUs)</h2>
  <table>
    <thead><tr><th>Row</th><th>SKU</th><th>Subject IRI</th><th>Triples</th><th>Max Packet Loss %</th><th>Availability %</th><th>Auto-Remediation</th><th>Lifecycle</th></tr></thead>
    <tbody>{promoted_rows_html}</tbody>
  </table>

  <h2>(d) Detailed pySHACL Row Quarantine Table ({len(summary.quarantined_rows)} Quarantined Rows)</h2>
  <table>
    <thead><tr><th>Row</th><th>SKU</th><th>Violated Constraint</th><th>Path</th><th>Message</th><th>Raw Values</th><th>pySHACL Validation Report</th></tr></thead>
    <tbody>{quarantine_rows_html}</tbody>
  </table>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")


# ============================================================================
# 6. End-to-End Scenario `DT-01b` Orchestrator
# ============================================================================
def run_dt01b_excel_quarantine(
    config: AppConfig,
    logger: logging.Logger,
    root_dir: Optional[Path] = None,
) -> Dt01bExecutionResult:
    """Execute Scenario `DT-01b` end-to-end with fail-fast validation."""
    resolved_root = root_dir if root_dir is not None else get_workspace_root()
    validate_dt01a_prerequisites(config, resolved_root)

    excel_rel_path = (
        Path(config.paths.raw_sources_dir)
        / config.paths.excel_subdir
        / config.stage0.excel_catalog_filename
    )
    excel_path = resolved_root / excel_rel_path
    charter_path = resolved_root / Path(config.track_b_ingestion_and_er.use_case_charter_path)
    tbox_path = resolved_root / Path(config.layer4_compiler_federation.tbox_path)
    shape_path = (
        resolved_root
        / Path(config.layer4_compiler_federation.shapes_dir)
        / "service_spec_shape.ttl"
    )
    trig_path = resolved_root / Path(config.layer4_compiler_federation.dataset_trig_path)
    rml_path = resolved_root / Path(config.layer4_compiler_federation.excel_rml_path)
    html_path = resolved_root / Path(config.track_b_ingestion_and_er.shacl_quarantine_report_path)
    md_path = html_path.with_suffix(".md")
    json_path = resolved_root / Path(
        config.track_b_ingestion_and_er.shacl_quarantine_summary_path
    )

    if not charter_path.exists():
        raise FileNotFoundError(f"Use case charter not found: {charter_path}")

    introspection = introspect_excel_workbook(excel_path)
    charter_text = charter_path.read_text(encoding="utf-8")
    tbox_text = tbox_path.read_text(encoding="utf-8")

    proposal, model_used = profile_excel_catalog_via_llm(
        introspection=introspection,
        use_case_charter_text=charter_text,
        tbox_turtle_text=tbox_text,
        config=config,
        logger=logger,
    )

    write_excel_catalog_rml_yaml(
        proposal=proposal,
        workbook_rel_path=str(excel_rel_path.as_posix()),
        model_used=model_used,
        output_path=rml_path,
    )

    promoted_graph, promoted_skus, quarantined_rows = materialize_and_quarantine_excel_rows(
        excel_path=excel_path,
        proposal=proposal,
        tbox_path=tbox_path,
        shape_path=shape_path,
        logger=logger,
    )

    catalog_triples, virtual_ib_triples = update_knowledge_graph_catalog(
        trig_path=trig_path,
        promoted_graph=promoted_graph,
    )

    excluded_tabs = [
        wc.sheet_name
        for wc in proposal.worksheet_classifications
        if wc.classification == "EXCLUDED_DISTRACTOR_TAB"
    ]
    executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    summary = ShaclQuarantineSummary(
        executed_at_utc=executed_at,
        workbook_path=str(excel_rel_path.as_posix()),
        target_sheet_name=proposal.target_sheet_name,
        header_row_index=proposal.header_row_index,
        data_start_row_index=proposal.data_start_row_index,
        excluded_distractor_tabs_count=len(excluded_tabs),
        excluded_distractor_tabs=excluded_tabs,
        total_data_rows_evaluated=len(promoted_skus) + len(quarantined_rows),
        valid_skus_loaded_count=len(promoted_skus),
        quarantined_rows_count=len(quarantined_rows),
        catalog_triples_materialized=catalog_triples,
        virtual_ib_triples_count=virtual_ib_triples,
        rml_mapping_path=config.layer4_compiler_federation.excel_rml_path,
        quarantined_rows=quarantined_rows,
    )

    write_quarantine_reports(
        proposal=proposal,
        summary=summary,
        promoted_skus=promoted_skus,
        html_path=html_path,
        md_path=md_path,
        json_path=json_path,
    )

    logger.info(
        "DT-01b complete: target_tab=%s excluded_tabs=%d promoted_skus=%d "
        "quarantined_rows=%d catalog_triples=%d virtual_ib_triples=%d",
        proposal.target_sheet_name,
        len(excluded_tabs),
        len(promoted_skus),
        len(quarantined_rows),
        catalog_triples,
        virtual_ib_triples,
    )

    return Dt01bExecutionResult(
        executed_at_utc=executed_at,
        model_used=model_used,
        workbook_path=excel_path,
        rml_mapping_path=rml_path,
        trig_dataset_path=trig_path,
        quarantine_html_report_path=html_path,
        quarantine_markdown_report_path=md_path,
        quarantine_summary_json_path=json_path,
        target_sheet_name=proposal.target_sheet_name,
        excluded_distractor_tabs_count=len(excluded_tabs),
        total_data_rows_evaluated=len(promoted_skus) + len(quarantined_rows),
        valid_skus_loaded_count=len(promoted_skus),
        quarantined_rows_count=len(quarantined_rows),
        catalog_triples_materialized=catalog_triples,
        virtual_ib_triples_count=virtual_ib_triples,
        promoted_skus=promoted_skus,
        quarantined_rows=quarantined_rows,
    )

