"""
Scenario `DT-01c` — 100% Document-Independent Prong 3 PDF BITES Extractor,
Fuzzy Entity Resolution (`rapidfuzz`) & Two-Phase Mandatory HITL Gate 2 Lock
(`src/track_b/s3_pdf_bites_er_ingestor.py`).

Architectural Invariants (`IMP-006`):
  1. Zero hardcoded page numbers, chapter numbers, hardware SKUs, or customer
     names exist anywhere in this module.
  2. Fails fast ONLY if Step 2 (`DT-01a`) is not `LOCKED_APPROVED`; handles
     optional Step 3 (`DT-01b`) artifacts gracefully. Never auto-runs `DT-01a`
     or `DT-01b`.
  3. Dynamically introspects all PDFs via `pypdf` and discovers canonical CMDB
     entities from SQLite via `mappings/cmdb_r2rml.ttl`.
  4. Invokes Gemini via `src/llm_client.py` (`track_b_pdf_bites`) with zero
     heuristic fallback.
  5. Enforces Two-Phase HITL Gate 2 (`--mode candidate` -> `--mode approve`),
     keeping `<urn:telco:graph:virtual:ib>` at 0 persisted triples.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
import logging
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Any, Dict, List, Literal, Optional, Tuple
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"^google\.genai\.")
    from google.genai import types as genai_types
from pypdf import PdfReader
from rapidfuzz import fuzz
from rdflib import Dataset, Graph, Literal as RdfLiteral, Namespace, RDF, RDFS, URIRef, XSD
from rdflib.namespace import OWL, SKOS

from src.config_loader import get_workspace_root
from src.llm_client import (
    create_genai_client,
    resolve_model_for_component,
    strip_unsupported_vertex_schema_keys,
)
from src.models import (
    AppConfig,
    BitAndErGate2CandidateProposal,
    CanonicalCustomerRecord,
    CustomerMentionCandidate,
    Dt01cExecutionResult,
    ExtractedBitesTriple,
    FuzzyErMatchProposal,
    PdfBitesLlmProposal,
    PdfCorpusIntrospection,
    PdfDocumentExtractionProposal,
    PdfDocumentIntrospection,
    PdfPageIntrospection,
    ShaclQuarantineSummary,
)

GRAPH_TBOX_URI = URIRef("urn:telco:graph:tbox:sid-etom")
GRAPH_REF_CATALOG = URIRef("urn:telco:graph:ref:catalog")
GRAPH_VIRTUAL_IB = URIRef("urn:telco:graph:virtual:ib")
GRAPH_META_DOC_LIFECYCLE = URIRef("urn:telco:graph:meta:doc-lifecycle")
GRAPH_BRIDGE_ER = URIRef("urn:telco:graph:bridge:er")

RR_NS = Namespace("http://www.w3.org/ns/r2rml#")
TMF_NS = Namespace("http://tmforum.org/sid/")
TELCO_NS = Namespace("http://telco.enterprise.org/ontology/")

DEFAULT_PREFIXES: Dict[str, Namespace] = {
    "tmf": TMF_NS,
    "telco": TELCO_NS,
    "rdfs": RDFS,
    "rdf": RDF,
    "owl": OWL,
    "skos": SKOS,
    "xsd": XSD,
}

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(b\.?v\.?|n\.?v\.?|inc\.?|ltd\.?|llc|gmbh|corp\.?|s\.?a\.?|plc)\b",
    re.IGNORECASE,
)


# ============================================================================
# 1. Fail-Fast Step 2 (`DT-01a`) Pre-Condition Verification
# ============================================================================
def validate_dt01a_prerequisite(config: AppConfig, root_dir: Path) -> None:
    """
    Verify Step 2 (`DT-01a`) is `LOCKED_APPROVED`. Fails fast with an explicit
    `RuntimeError` if required Step 2 artifacts or approval are missing.
    """
    tbox_path = root_dir / Path(config.layer4_compiler_federation.tbox_path)
    trig_path = root_dir / Path(config.layer4_compiler_federation.dataset_trig_path)
    r2rml_path = root_dir / Path(config.layer4_compiler_federation.r2rml_path)
    gate1_report_path = root_dir / Path(config.track_b_ingestion_and_er.hitl_gate1_report_path)

    missing_files = [
        str(path)
        for path in (tbox_path, trig_path, r2rml_path, gate1_report_path)
        if not path.exists()
    ]
    if missing_files:
        raise RuntimeError(
            "DT-01c prerequisite check failed: missing Step 2 (DT-01a) locked artifacts: "
            f"{missing_files}. Run and approve DT-01a first: "
            "`python scripts/run_dt01a_cmdb_gate1.py --mode approve`."
        )

    gate1_html = gate1_report_path.read_text(encoding="utf-8")
    if "LOCKED_APPROVED" not in gate1_html:
        raise RuntimeError(
            "DT-01c prerequisite check failed: HITL Gate 1 is not LOCKED_APPROVED in "
            f"{gate1_report_path}. Approve DT-01a first: "
            "`python scripts/run_dt01a_cmdb_gate1.py --mode approve`."
        )


def load_optional_quarantine_summary(
    config: AppConfig, root_dir: Path
) -> Optional[ShaclQuarantineSummary]:
    """Load Step 3 (`DT-01b`) quarantine summary if present; return None otherwise."""
    summary_path = root_dir / Path(
        config.track_b_ingestion_and_er.shacl_quarantine_summary_path
    )
    if not summary_path.exists():
        return None
    return ShaclQuarantineSummary.model_validate_json(
        summary_path.read_text(encoding="utf-8")
    )


# ============================================================================
# 2. Dynamic PDF Corpus Introspection (`pypdf` + SHA-256)
# ============================================================================
def introspect_pdf_corpus(pdf_dir: Path, root_dir: Path) -> PdfCorpusIntrospection:
    """
    Dynamically inspect all `.pdf` files in `pdf_dir` using `pypdf`, extracting
    page counts, page-by-page text, and SHA-256 digests with zero hardcoding.
    """
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in directory: {pdf_dir}")

    documents: List[PdfDocumentIntrospection] = []
    for pdf_path in pdf_files:
        sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        reader = PdfReader(str(pdf_path))
        pages: List[PdfPageIntrospection] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages.append(
                PdfPageIntrospection(
                    page_number=idx,
                    char_count=len(text),
                    extracted_text=text,
                )
            )
        try:
            rel_path = pdf_path.relative_to(root_dir).as_posix()
        except ValueError:
            rel_path = pdf_path.name
        documents.append(
            PdfDocumentIntrospection(
                pdf_filename=pdf_path.name,
                relative_path=rel_path,
                sha256_hash=sha256,
                page_count=len(pages),
                pages=pages,
            )
        )

    return PdfCorpusIntrospection(
        pdf_dir=str(pdf_dir),
        document_count=len(documents),
        documents=documents,
    )


# ============================================================================
# 3. Dynamic CMDB & Catalog Entity Discovery (`cmdb_r2rml.ttl` + SQLite)
# ============================================================================
def _extract_template_placeholders(template: str) -> List[str]:
    """Extract `{col}` placeholder names from an R2RML subject template."""
    return re.findall(r"\{([^}]+)\}", template)


def _render_r2rml_template(template: str, row_dict: Dict[str, Any]) -> str:
    """Substitute `{col}` placeholders in an R2RML template with SQLite row values."""
    rendered = template
    for placeholder in _extract_template_placeholders(template):
        rendered = rendered.replace(f"{{{placeholder}}}", str(row_dict.get(placeholder, "")))
    return rendered


def discover_canonical_entities(
    r2rml_path: Path,
    sqlite_path: Path,
    trig_path: Path,
) -> Tuple[List[CanonicalCustomerRecord], Dict[str, List[str]]]:
    """
    Parse `mappings/cmdb_r2rml.ttl` to dynamically locate the `tmf:Customer`
    R2RML TriplesMap and hardware/service tables in SQLite, plus optional
    valid `tmf:ServiceSpecification` SKUs in `<urn:telco:graph:ref:catalog>`.
    """
    r2rml_graph = Graph()
    r2rml_graph.parse(str(r2rml_path), format="turtle")

    customers: List[CanonicalCustomerRecord] = []
    entity_inventory: Dict[str, List[str]] = {"catalog_skus": [], "cmdb_samples": []}

    if not sqlite_path.exists():
        raise FileNotFoundError(f"CMDB SQLite database not found: {sqlite_path}")

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        for tm in r2rml_graph.subjects(RDF.type, RR_NS.TriplesMap):
            logical_table = r2rml_graph.value(tm, RR_NS.logicalTable)
            subject_map = r2rml_graph.value(tm, RR_NS.subjectMap)
            if logical_table is None or subject_map is None:
                continue

            table_name_lit = r2rml_graph.value(logical_table, RR_NS.tableName)
            sql_query_lit = r2rml_graph.value(logical_table, RR_NS.sqlQuery)
            target_class = r2rml_graph.value(subject_map, RR_NS["class"])
            subject_template_lit = r2rml_graph.value(subject_map, RR_NS.template)
            if (table_name_lit is None and sql_query_lit is None) or target_class is None:
                continue

            if sql_query_lit is not None:
                query_sql = str(sql_query_lit).strip()
            else:
                table_name = str(table_name_lit).strip()
                query_sql = f'SELECT * FROM "{table_name}"'

            subject_template = (
                str(subject_template_lit).strip() if subject_template_lit else ""
            )

            pred_to_col: Dict[str, str] = {}
            for pom in r2rml_graph.objects(tm, RR_NS.predicateObjectMap):
                pred = r2rml_graph.value(pom, RR_NS.predicate)
                obj_map = r2rml_graph.value(pom, RR_NS.objectMap)
                if pred is not None and obj_map is not None:
                    col_lit = r2rml_graph.value(obj_map, RR_NS.column)
                    if col_lit is not None:
                        pred_to_col[str(pred)] = str(col_lit)

            rows = conn.execute(query_sql).fetchall()
            if str(target_class) == str(TMF_NS.Customer):
                id_cols = _extract_template_placeholders(subject_template)
                id_col = id_cols[0] if id_cols else next(iter(pred_to_col.values()), "")
                name_col = next(
                    (
                        col
                        for pred_uri, col in pred_to_col.items()
                        if "name" in pred_uri.lower() or "label" in pred_uri.lower()
                    ),
                    next(iter(pred_to_col.values()), id_col),
                )
                reg_col = next(
                    (
                        col
                        for pred_uri, col in pred_to_col.items()
                        if "reg" in pred_uri.lower() or "kvk" in pred_uri.lower()
                    ),
                    None,
                )
                for row in rows:
                    row_dict = dict(row)
                    cust_id = str(row_dict.get(id_col, "")).strip()
                    cust_name = str(row_dict.get(name_col, "")).strip()
                    if not cust_id or not cust_name:
                        continue
                    subject_iri = (
                        _render_r2rml_template(subject_template, row_dict)
                        if subject_template
                        else f"urn:telco:cmdb:customer:{cust_id}"
                    )
                    reg_val = (
                        str(row_dict.get(reg_col)).strip()
                        if reg_col and row_dict.get(reg_col) is not None
                        else None
                    )
                    customers.append(
                        CanonicalCustomerRecord(
                            customer_id=cust_id,
                            customer_name=cust_name,
                            subject_iri=subject_iri,
                            registration_number=reg_val,
                        )
                    )
            else:
                for row in rows[:10]:
                    row_dict = dict(row)
                    if subject_template:
                        entity_inventory["cmdb_samples"].append(
                            _render_r2rml_template(subject_template, row_dict)
                        )
    finally:
        conn.close()

    if trig_path.exists():
        ds = Dataset()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
            ds.parse(str(trig_path), format="trig")
        catalog_ctx = ds.graph(GRAPH_REF_CATALOG)
        for sku_lit in catalog_ctx.objects(None, TMF_NS.skuCode):
            entity_inventory["catalog_skus"].append(str(sku_lit))

    return customers, entity_inventory


# ============================================================================
# 4. Gemini AI PDF BITES Extractor (`src/llm_client.py`, Zero Fallback)
# ============================================================================
def generate_bites_proposal_via_llm(
    corpus: PdfCorpusIntrospection,
    use_case_charter_text: str,
    tbox_turtle_text: str,
    canonical_customers: List[CanonicalCustomerRecord],
    entity_inventory: Dict[str, List[str]],
    config: AppConfig,
    logger: logging.Logger,
    prompt_template_text: Optional[str] = None,
) -> Tuple[PdfBitesLlmProposal, str]:
    """
    Invoke Gemini via `src/llm_client.py` (`track_b_pdf_bites`) to classify PDF
    pages, extract scoped BITES triples, and identify customer mentions.
    """
    if prompt_template_text is None:
        prompt_path = get_workspace_root() / Path(
            config.track_b_ingestion_and_er.pdf_bites_prompt_template_path
        )
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"PDF BITES prompt template not found: {prompt_path}"
            )
        prompt_template_text = prompt_path.read_text(encoding="utf-8")

    client = create_genai_client(config, logger)
    model_id = resolve_model_for_component(config, "track_b_pdf_bites")

    inventory_payload = {
        "canonical_customers": [c.model_dump() for c in canonical_customers],
        "entity_inventory": entity_inventory,
    }

    user_payload = (
        f"{prompt_template_text}\n\n"
        f"=== INPUT 1: USE CASE CHARTER (`{config.use_case.use_case_id}`) ===\n"
        f"{use_case_charter_text}\n\n"
        f"=== INPUT 2: LOCKED CONCEPTUAL TBOX (`tbox_sid_etom.ttl`) ===\n"
        f"{tbox_turtle_text}\n\n"
        f"=== INPUT 3: CANONICAL ENTITY INVENTORY ===\n"
        f"{json.dumps(inventory_payload, indent=2)}\n\n"
        f"=== INPUT 4: DYNAMICALLY INTROSPECTED PDF CORPUS ===\n"
        f"{json.dumps(corpus.model_dump(), indent=2)}\n"
    )

    clean_schema = strip_unsupported_vertex_schema_keys(
        PdfBitesLlmProposal.model_json_schema()
    )

    logger.info(
        "Invoking Gemini PDF BITES Extractor (model=%s) across %d PDFs...",
        model_id,
        corpus.document_count,
    )
    response = client.models.generate_content(
        model=model_id,
        contents=user_payload,
        config=genai_types.GenerateContentConfig(
            temperature=config.ai.temperature,
            response_mime_type="application/json",
            response_schema=clean_schema,
        ),
    )

    if not response.text or not response.text.strip():
        raise RuntimeError(
            "Gemini PDF BITES Extractor returned an empty response; failing fast."
        )

    proposal = PdfBitesLlmProposal.model_validate_json(response.text)
    return proposal, model_id


# ============================================================================
# 5. Deterministic Fuzzy Entity Resolution (`rapidfuzz`)
# ============================================================================
def _strip_legal_suffix(name: str) -> str:
    """Normalize organization names by stripping common corporate legal suffixes."""
    cleaned = _LEGAL_SUFFIX_RE.sub("", name)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def resolve_customer_mentions_fuzzy(
    document_extractions: List[PdfDocumentExtractionProposal],
    canonical_customers: List[CanonicalCustomerRecord],
    review_band_min: float = 0.85,
    review_band_max: float = 0.95,
) -> List[FuzzyErMatchProposal]:
    """
    Score unlinked `DOCUMENT_SCOPE` customer mentions against canonical CMDB
    `tmf:Customer` records using `rapidfuzz` raw + legal-suffix-normalized similarity.
    """
    if not canonical_customers:
        return []

    matches: List[FuzzyErMatchProposal] = []
    for doc in document_extractions:
        for mention in doc.customer_mentions:
            best_customer: Optional[CanonicalCustomerRecord] = None
            best_raw = 0.0
            best_norm = 0.0
            best_composite = -1.0

            mention_norm = _strip_legal_suffix(mention.mention_text)
            for cand in canonical_customers:
                raw_sim = fuzz.ratio(mention.mention_text, cand.customer_name) / 100.0
                cand_norm = _strip_legal_suffix(cand.customer_name)
                norm_sim = fuzz.token_sort_ratio(mention_norm, cand_norm) / 100.0
                composite = 0.75 * raw_sim + 0.25 * norm_sim
                if composite > best_composite:
                    best_composite = composite
                    best_raw = raw_sim
                    best_norm = norm_sim
                    best_customer = cand

            if best_customer is None:
                continue

            rounded_comp = round(best_composite, 4)
            if review_band_min <= rounded_comp <= review_band_max:
                status: Literal["CURATION_PENDING", "AUTO_MATCHED", "REJECTED"] = (
                    "CURATION_PENDING"
                )
            elif rounded_comp > review_band_max:
                status = "AUTO_MATCHED"
            else:
                status = "REJECTED"

            matches.append(
                FuzzyErMatchProposal(
                    source_pdf_filename=doc.pdf_filename,
                    mention_text=mention.mention_text,
                    mention_subject_iri=mention.mention_subject_iri,
                    registration_number=mention.registration_number,
                    canonical_customer_id=best_customer.customer_id,
                    canonical_customer_name=best_customer.customer_name,
                    canonical_subject_iri=best_customer.subject_iri,
                    raw_similarity=round(best_raw, 4),
                    normalized_similarity=round(best_norm, 4),
                    composite_confidence=rounded_comp,
                    curation_status=status,
                    proposed_bridge_predicates=[
                        "owl:sameAs",
                        "skos:exactMatch",
                        "telco:resolvedToCanonicalCustomer",
                    ],
                )
            )

    return matches


# ============================================================================
# 6. RDF Compilation & Idempotent TriG Promotion (`--mode approve`)
# ============================================================================
def _resolve_qname(qname: str, prefixes: Dict[str, Namespace]) -> URIRef:
    """Resolve QName or full IRI to rdflib.URIRef."""
    cleaned = qname.strip()
    if cleaned.startswith(("http://", "https://", "urn:")):
        return URIRef(cleaned)
    if ":" not in cleaned:
        raise ValueError(f"Invalid QName or IRI '{qname}': missing prefix separator.")
    prefix, local_name = cleaned.split(":", 1)
    if prefix not in prefixes:
        raise ValueError(
            f"Unknown prefix '{prefix}' in QName '{qname}'. Known: {sorted(prefixes)}"
        )
    return prefixes[prefix][local_name]


def _coerce_literal(value: str, datatype_qname: Optional[str]) -> RdfLiteral:
    """Coerce an extracted triple's literal value to an RDF 1.1 typed Literal."""
    dt = (datatype_qname or "xsd:string").strip()
    if dt in {"xsd:double", "xsd:decimal", "xsd:float"}:
        try:
            return RdfLiteral(float(value), datatype=XSD.double)
        except ValueError:
            return RdfLiteral(value)
    if dt in {"xsd:integer", "xsd:int"}:
        try:
            return RdfLiteral(int(float(value)), datatype=XSD.integer)
        except ValueError:
            return RdfLiteral(value)
    if dt == "xsd:boolean":
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return RdfLiteral(True, datatype=XSD.boolean)
        if lowered in {"false", "0", "no"}:
            return RdfLiteral(False, datatype=XSD.boolean)
        return RdfLiteral(value)
    return RdfLiteral(value)


def compile_and_promote_gate2_graphs(
    proposal: BitAndErGate2CandidateProposal,
    trig_path: Path,
    tbox_path: Path,
) -> Tuple[int, int, int, int, int]:
    """
    Idempotently compile and populate `<urn:telco:graph:bites:*>`,
    `<urn:telco:graph:meta:doc-lifecycle>`, and `<urn:telco:graph:bridge:er>` in
    `knowledge_graph.trig`, preserving TBox & Catalog and verifying virtual IB = 0.
    """
    tbox_graph = Graph()
    tbox_graph.parse(str(tbox_path), format="turtle")
    prefixes = dict(DEFAULT_PREFIXES)
    for prefix, uri in tbox_graph.namespace_manager.namespaces():
        if prefix:
            prefixes[str(prefix)] = Namespace(str(uri))

    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(trig_path), format="trig")

    for prefix, ns in prefixes.items():
        ds.bind(prefix, ns)

    # Clear target BITES, lifecycle, and ER bridge graphs idempotently
    for doc in proposal.document_extractions:
        ds.remove((None, None, None, URIRef(doc.target_named_graph_uri)))
    ds.remove((None, None, None, GRAPH_META_DOC_LIFECYCLE))
    ds.remove((None, None, None, GRAPH_BRIDGE_ER))

    global_triples = 0
    doc_scope_triples = 0
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lifecycle_ctx = ds.graph(GRAPH_META_DOC_LIFECYCLE)
    for doc in proposal.document_extractions:
        target_ctx = ds.graph(URIRef(doc.target_named_graph_uri))
        for triple in doc.extracted_triples:
            subj = _resolve_qname(triple.subject_iri, prefixes)
            pred = _resolve_qname(triple.predicate_qname, prefixes)
            if triple.object_kind == "IRI":
                obj: Any = _resolve_qname(triple.object_value, prefixes)
            else:
                obj = _coerce_literal(triple.object_value, triple.datatype_qname)
            target_ctx.add((subj, pred, obj))

        if doc.assigned_scope == "GLOBAL_SCOPE":
            global_triples += len(target_ctx)
        else:
            doc_scope_triples += len(target_ctx)

        doc_uri = URIRef(f"urn:telco:doc:{doc.pdf_filename}")
        lifecycle_ctx.add((doc_uri, RDF.type, TELCO_NS.SourceDocument))
        lifecycle_ctx.add((doc_uri, RDFS.label, RdfLiteral(doc.pdf_filename)))
        lifecycle_ctx.add((doc_uri, TELCO_NS.lifecycleStatus, RdfLiteral("ACTIVE")))
        lifecycle_ctx.add((doc_uri, TELCO_NS.documentVersion, RdfLiteral(doc.document_version)))
        lifecycle_ctx.add((doc_uri, TELCO_NS.sha256Hash, RdfLiteral(doc.sha256_hash)))
        lifecycle_ctx.add((doc_uri, TELCO_NS.assignedScope, RdfLiteral(doc.assigned_scope)))
        lifecycle_ctx.add(
            (doc_uri, TELCO_NS.targetNamedGraph, URIRef(doc.target_named_graph_uri))
        )
        lifecycle_ctx.add((doc_uri, TELCO_NS.extractedAtUtc, RdfLiteral(extracted_at)))

    er_ctx = ds.graph(GRAPH_BRIDGE_ER)
    for match in proposal.fuzzy_er_matches:
        if match.curation_status == "REJECTED":
            continue
        mention_uri = _resolve_qname(match.mention_subject_iri, prefixes)
        canonical_uri = _resolve_qname(match.canonical_subject_iri, prefixes)
        for pred_qname in match.proposed_bridge_predicates:
            er_ctx.add((mention_uri, _resolve_qname(pred_qname, prefixes), canonical_uri))
        er_ctx.add(
            (
                mention_uri,
                TELCO_NS.erConfidenceScore,
                RdfLiteral(match.composite_confidence, datatype=XSD.double),
            )
        )
        er_ctx.add((mention_uri, TELCO_NS.erCurationStatus, RdfLiteral("APPROVED")))

    virtual_ib_count = len(ds.graph(GRAPH_VIRTUAL_IB))
    if virtual_ib_count != 0:
        raise RuntimeError(
            f"Invariant violation: <{GRAPH_VIRTUAL_IB}> must remain at 0 persisted triples, "
            f"found {virtual_ib_count}."
        )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.serialize(destination=str(trig_path), format="trig")

    return (
        global_triples,
        doc_scope_triples,
        len(lifecycle_ctx),
        len(er_ctx),
        virtual_ib_count,
    )


# ============================================================================
# 7. HITL Gate 2 Curation Reports (HTML & Markdown)
# ============================================================================
def write_gate2_curation_reports(
    proposal: BitAndErGate2CandidateProposal,
    quarantine_summary: Optional[ShaclQuarantineSummary],
    gate2_status: Literal["CURATION_PENDING", "PROMOTED"],
    html_path: Path,
    md_path: Path,
) -> None:
    """Write HITL Gate 2 curation review HTML and Markdown reports."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    quarantined_rows = quarantine_summary.quarantined_rows if quarantine_summary else []
    status_badge = (
        "PROMOTED (HITL Gate 2 Approved)"
        if gate2_status == "PROMOTED"
        else "CURATION_PENDING (Awaiting HITL Gate 2)"
    )

    md_lines: List[str] = [
        "# Scenario DT-01c: HITL Gate 2 PDF BITES, Quarantine Disposition & Fuzzy ER Curation",
        "",
        f"- **Gate 2 Status:** `{status_badge}`",
        f"- **Generated At (UTC):** `{proposal.generated_at_utc}`",
        f"- **Model Used:** `{proposal.model_used}`",
        f"- **Active PDFs Analyzed:** `{len(proposal.document_extractions)}`",
        f"- **Fuzzy ER Matches Proposed:** `{len(proposal.fuzzy_er_matches)}`",
        "",
        "## 1. Review & Disposition of `pySHACL`-Quarantined Excel Rows (DT-01b)",
        "",
        f"Quarantined rows on disk: `{len(quarantined_rows)}` (Recommended Disposition: `KEEP_QUARANTINED (Excluded from Catalog)`).",
        "",
        "| Excel Row | SKU Code | Disposition | Violated Constraint(s) |",
        "|---:|---|---|---|",
    ]
    for qrow in quarantined_rows:
        md_lines.append(
            f"| {qrow.excel_row_number} | `{qrow.sku_code or '-'}` | "
            "`KEEP_QUARANTINED (Excluded from Catalog)` | "
            f"`{qrow.violated_constraint_component}` |"
        )

    md_lines.extend([
        "",
        "## 2. PDF Page Relevance Filtering & Scoped BITES Triples",
        "",
    ])
    for doc in proposal.document_extractions:
        rel_pages = [p for p in doc.page_decisions if p.classification == "RELEVANT_EXTRACTED"]
        exc_pages = [p for p in doc.page_decisions if p.classification == "EXCLUDED_DISTRACTOR_PAGE"]
        md_lines.extend([
            f"### `{doc.pdf_filename}` (`{doc.assigned_scope}` -> `<{doc.target_named_graph_uri}>`)",
            f"- **Version:** `{doc.document_version}` | **SHA-256:** `{doc.sha256_hash[:16]}...` | **Lifecycle:** `ACTIVE`",
            f"- **Relevant Pages ({len(rel_pages)}):** {', '.join(str(p.page_number) for p in rel_pages)}",
            f"- **Excluded Distractor Pages ({len(exc_pages)}):** {', '.join(str(p.page_number) for p in exc_pages)}",
            f"- **Extracted BITES Triples:** `{len(doc.extracted_triples)}`",
            "",
        ])

    md_lines.extend([
        "## 3. Fuzzy Entity Resolution Curation Queue (`rapidfuzz`)",
        "",
        "| Source PDF | PDF Mention | Canonical CMDB Customer | Raw Sim | Norm Sim | Composite | Status | Proposed Bridge |",
        "|---|---|---|---:|---:|---:|---|---|",
    ])
    for match in proposal.fuzzy_er_matches:
        md_lines.append(
            f"| `{match.source_pdf_filename}` | `{match.mention_text}` | "
            f"`{match.canonical_customer_name}` (`{match.canonical_customer_id}`) | "
            f"{match.raw_similarity:.4f} | {match.normalized_similarity:.4f} | "
            f"**{match.composite_confidence:.4f}** | `{match.curation_status}` | "
            f"`{', '.join(match.proposed_bridge_predicates)}` |"
        )

    md_lines.extend([
        "",
        "## 4. HITL Gate 2 Steward / Architect Verification Questions",
        "",
    ])
    for idx, q in enumerate(proposal.architect_verification_questions, start=1):
        md_lines.append(f"{idx}. {q}")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # HTML report
    q_rows_html = "\n".join(
        f"<tr><td>{q.excel_row_number}</td><td><code>{html.escape(q.sku_code or '-')}</code></td>"
        f"<td><strong>KEEP_QUARANTINED (Excluded from Catalog)</strong></td>"
        f"<td><code>{html.escape(q.violated_constraint_component)}</code></td></tr>"
        for q in quarantined_rows
    )
    doc_sections_html = "\n".join(
        f"<div class='doc-card'><h3>{html.escape(doc.pdf_filename)} "
        f"(<code>{html.escape(doc.assigned_scope)}</code> &rarr; "
        f"<code>&lt;{html.escape(doc.target_named_graph_uri)}&gt;</code>)</h3>"
        f"<p><strong>Version:</strong> {html.escape(doc.document_version)} | "
        f"<strong>SHA-256:</strong> <code>{html.escape(doc.sha256_hash[:16])}...</code> | "
        f"<strong>Lifecycle:</strong> <code>ACTIVE</code> | "
        f"<strong>Extracted Triples:</strong> {len(doc.extracted_triples)}</p>"
        f"<p>{html.escape(doc.document_summary)}</p></div>"
        for doc in proposal.document_extractions
    )
    er_rows_html = "\n".join(
        f"<tr><td><code>{html.escape(m.source_pdf_filename)}</code></td>"
        f"<td>{html.escape(m.mention_text)}</td>"
        f"<td>{html.escape(m.canonical_customer_name)} (<code>{html.escape(m.canonical_customer_id)}</code>)</td>"
        f"<td>{m.raw_similarity:.4f}</td><td>{m.normalized_similarity:.4f}</td>"
        f"<td><strong>{m.composite_confidence:.4f}</strong></td>"
        f"<td><code>{html.escape(m.curation_status)}</code></td>"
        f"<td><code>{html.escape(', '.join(m.proposed_bridge_predicates))}</code></td></tr>"
        for m in proposal.fuzzy_er_matches
    )
    questions_html = "\n".join(
        f"<li>{html.escape(q)}</li>" for q in proposal.architect_verification_questions
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>DT-01c HITL Gate 2 Ingestion &amp; ER Curation</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    .status-banner {{ padding: 12px 16px; border-radius: 6px; background: #fef3c7; border: 1px solid #f59e0b; margin-bottom: 20px; }}
    .promoted {{ background: #dcfce7; border-color: #16a34a; }}
    .doc-card {{ border: 1px solid #cbd5e1; padding: 12px; border-radius: 6px; margin-bottom: 12px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; }}
    th {{ background: #e2e8f0; }}
  </style>
</head>
<body>
  <h1>Scenario DT-01c: HITL Gate 2 PDF BITES &amp; Fuzzy ER Curation</h1>
  <div class="status-banner {'promoted' if gate2_status == 'PROMOTED' else ''}">
    <strong>Gate 2 Status:</strong> <code>{html.escape(status_badge)}</code> |
    <strong>Model:</strong> <code>{html.escape(proposal.model_used)}</code> |
    <strong>Generated (UTC):</strong> <code>{html.escape(proposal.generated_at_utc)}</code>
  </div>

  <h2>1. Review &amp; Disposition of pySHACL-Quarantined Excel Rows (DT-01b)</h2>
  <table>
    <thead><tr><th>Row</th><th>SKU</th><th>Recommended Disposition</th><th>Violated Constraint(s)</th></tr></thead>
    <tbody>{q_rows_html}</tbody>
  </table>

  <h2>2. PDF Page Relevance Filtering &amp; Scoped BITES Triples</h2>
  {doc_sections_html}

  <h2>3. Fuzzy Entity Resolution Curation Queue (rapidfuzz)</h2>
  <table>
    <thead><tr><th>PDF</th><th>Mention</th><th>Canonical Customer</th><th>Raw</th><th>Norm</th><th>Composite</th><th>Status</th><th>Bridge Predicates</th></tr></thead>
    <tbody>{er_rows_html}</tbody>
  </table>

  <h2>4. HITL Gate 2 Steward / Architect Verification Questions</h2>
  <ol>{questions_html}</ol>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")


# ============================================================================
# 8. End-to-End Two-Phase Scenario `DT-01c` Orchestrator
# ============================================================================
def run_dt01c_pdf_bites_gate2(
    config: AppConfig,
    logger: logging.Logger,
    mode: Literal["candidate", "approve"] = "candidate",
    update_golden_ref: bool = False,
    root_dir: Optional[Path] = None,
) -> Dt01cExecutionResult:
    """Execute Scenario `DT-01c` in Phase 1 (`candidate`) or Phase 2 (`approve`)."""
    resolved_root = root_dir if root_dir is not None else get_workspace_root()
    validate_dt01a_prerequisite(config, resolved_root)

    pdf_dir = (
        resolved_root / config.paths.raw_sources_dir / config.paths.pdf_subdir
    )
    charter_path = resolved_root / Path(
        config.track_b_ingestion_and_er.use_case_charter_path
    )
    tbox_path = resolved_root / Path(config.layer4_compiler_federation.tbox_path)
    r2rml_path = resolved_root / Path(config.layer4_compiler_federation.r2rml_path)
    sqlite_path = resolved_root / Path(config.layer4_compiler_federation.sqlite_db_path)
    trig_path = resolved_root / Path(config.layer4_compiler_federation.dataset_trig_path)
    candidate_path = resolved_root / Path(
        config.track_b_ingestion_and_er.gate2_candidate_proposal_path
    )
    gate2_html_path = resolved_root / Path(
        config.track_b_ingestion_and_er.hitl_gate2_report_path
    )
    gate2_md_path = gate2_html_path.with_suffix(".md")
    quarantine_summary = load_optional_quarantine_summary(config, resolved_root)
    quarantined_count = (
        quarantine_summary.quarantined_rows_count if quarantine_summary else 0
    )

    if mode == "candidate":
        corpus = introspect_pdf_corpus(pdf_dir, resolved_root)
        canonical_customers, entity_inventory = discover_canonical_entities(
            r2rml_path=r2rml_path,
            sqlite_path=sqlite_path,
            trig_path=trig_path,
        )
        charter_text = charter_path.read_text(encoding="utf-8")
        tbox_text = tbox_path.read_text(encoding="utf-8")

        llm_proposal, model_used = generate_bites_proposal_via_llm(
            corpus=corpus,
            use_case_charter_text=charter_text,
            tbox_turtle_text=tbox_text,
            canonical_customers=canonical_customers,
            entity_inventory=entity_inventory,
            config=config,
            logger=logger,
        )

        fuzzy_matches = resolve_customer_mentions_fuzzy(
            document_extractions=llm_proposal.document_extractions,
            canonical_customers=canonical_customers,
            review_band_min=config.track_b_ingestion_and_er.er_review_band_min,
            review_band_max=config.track_b_ingestion_and_er.er_review_band_max,
        )

        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        gate2_proposal = BitAndErGate2CandidateProposal(
            generated_at_utc=executed_at,
            model_used=model_used,
            document_extractions=llm_proposal.document_extractions,
            fuzzy_er_matches=fuzzy_matches,
            quarantined_excel_rows_count=quarantined_count,
            architect_verification_questions=llm_proposal.architect_verification_questions,
        )
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text(
            gate2_proposal.model_dump_json(indent=2), encoding="utf-8"
        )

        write_gate2_curation_reports(
            proposal=gate2_proposal,
            quarantine_summary=quarantine_summary,
            gate2_status="CURATION_PENDING",
            html_path=gate2_html_path,
            md_path=gate2_md_path,
        )

        global_count = sum(
            len(d.extracted_triples)
            for d in gate2_proposal.document_extractions
            if d.assigned_scope == "GLOBAL_SCOPE"
        )
        doc_count = sum(
            len(d.extracted_triples)
            for d in gate2_proposal.document_extractions
            if d.assigned_scope == "DOCUMENT_SCOPE"
        )

        return Dt01cExecutionResult(
            gate2_mode="candidate",
            gate2_status="CURATION_PENDING",
            executed_at_utc=executed_at,
            model_used=model_used,
            active_pdfs_count=len(gate2_proposal.document_extractions),
            global_scope_triples_count=global_count,
            document_scope_triples_count=doc_count,
            doc_lifecycle_triples_count=0,
            er_bridge_triples_count=0,
            er_links_count=len(fuzzy_matches),
            quarantined_excel_rows_count=quarantined_count,
            virtual_ib_triples_count=0,
            candidate_proposal_path=candidate_path,
            trig_dataset_path=trig_path,
            gate2_html_report_path=gate2_html_path,
            gate2_markdown_report_path=gate2_md_path,
            architect_verification_questions=gate2_proposal.architect_verification_questions,
            golden_ref_updated=False,
        )

    # Phase 2: --mode approve
    if not candidate_path.exists():
        raise FileNotFoundError(
            f"Gate 2 candidate proposal not found at {candidate_path}. "
            "Run `--mode candidate` first before approving."
        )

    gate2_proposal = BitAndErGate2CandidateProposal.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )

    (
        global_triples,
        doc_scope_triples,
        lifecycle_triples,
        er_bridge_triples,
        virtual_ib_count,
    ) = compile_and_promote_gate2_graphs(
        proposal=gate2_proposal,
        trig_path=trig_path,
        tbox_path=tbox_path,
    )

    write_gate2_curation_reports(
        proposal=gate2_proposal,
        quarantine_summary=quarantine_summary,
        gate2_status="PROMOTED",
        html_path=gate2_html_path,
        md_path=gate2_md_path,
    )

    golden_updated = False
    if update_golden_ref:
        golden_dir = resolved_root / "data" / "golden_reference"
        golden_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(trig_path, golden_dir / trig_path.name)
        excel_rml_path = resolved_root / Path(
            config.layer4_compiler_federation.excel_rml_path
        )
        if excel_rml_path.exists():
            shutil.copy2(excel_rml_path, golden_dir / excel_rml_path.name)
        golden_updated = True

    executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active_er_links = sum(
        1 for m in gate2_proposal.fuzzy_er_matches if m.curation_status != "REJECTED"
    )
    return Dt01cExecutionResult(
        gate2_mode="approve",
        gate2_status="PROMOTED",
        executed_at_utc=executed_at,
        model_used=gate2_proposal.model_used,
        active_pdfs_count=len(gate2_proposal.document_extractions),
        global_scope_triples_count=global_triples,
        document_scope_triples_count=doc_scope_triples,
        doc_lifecycle_triples_count=lifecycle_triples,
        er_bridge_triples_count=er_bridge_triples,
        er_links_count=active_er_links,
        quarantined_excel_rows_count=quarantined_count,
        virtual_ib_triples_count=virtual_ib_count,
        candidate_proposal_path=candidate_path,
        trig_dataset_path=trig_path,
        gate2_html_report_path=gate2_html_path,
        gate2_markdown_report_path=gate2_md_path,
        architect_verification_questions=gate2_proposal.architect_verification_questions,
        golden_ref_updated=golden_updated,
    )
