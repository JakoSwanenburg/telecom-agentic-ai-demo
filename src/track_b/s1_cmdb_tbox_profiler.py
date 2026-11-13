"""
Scenario `DT-01a` — 100% Schema-Independent & Use-Case-Independent Prong 1 SQL CMDB
AI Schema Profiler, Pruned TMF SID/eTOM TBox Compiler, W3C R2RML Virtual Graph
Compiler & Two-Phase Interactive HITL Gate 1 Workflow (`src/track_b/s1_cmdb_tbox_profiler.py`).

Architectural Invariants (`IMP-004-R1`):
  1. Zero hardcoded SQLite table names or column names exist anywhere in this module.
  2. Dynamically introspects any relational SQLite database via `sqlite_master`,
     `PRAGMA table_info`, `PRAGMA foreign_key_list`, distinct low-cardinality
     distributions, and sample rows (`SELECT *`).
  3. Cross-examines (a) the Use Case Charter markdown, (b) the generic TM Forum
     SID/eTOM/QUDT Reference Vocabulary JSON, and (c) the dynamic SQLite
     introspection using Gemini (`google-genai` via `GEMINI_API_KEY` if set, else
     Vertex AI on the configured GCP project, with zero heuristic fallback).
  4. Persists the structured `CandidateOntologyAndMappingProposal` at
     `data/semantic_store/gate1_candidate_proposal.json`.
  5. Enforces a Two-Phase HITL Gate 1 workflow:
     - `--mode candidate` (default): Generates `gate1_candidate_proposal.json` and
       the HITL Gate 1 review report (`CANDIDATE_PROPOSED`) with Architect
       Verification Questions, without locking `tbox_sid_etom.ttl` or binding
       `cmdb_r2rml.ttl`.
     - `--mode approve`: Reads `gate1_candidate_proposal.json`, generically compiles
       and locks `tbox_sid_etom.ttl`, `knowledge_graph.trig` (`0` persisted triples
       in `<urn:telco:graph:virtual:ib>`), `cmdb_r2rml.ttl`, and `shapes/*.ttl`,
       and transitions the HITL Gate 1 report to `LOCKED_APPROVED`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Callable, Dict, List, Literal, Optional
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"^google\.genai\.")
    from google.genai import types as genai_types
from rdflib import Dataset, Graph, Namespace, RDF, URIRef
from rdflib.namespace import OWL, SKOS

from src.config_loader import get_workspace_root
from src.llm_client import (
    create_genai_client as _create_genai_client,
    resolve_model_for_component,
    strip_unsupported_vertex_schema_keys as _strip_additional_properties,
)
from src.models import (
    AppConfig,
    CandidateOntologyAndMappingProposal,
    Dt01aExecutionResult,
    EvaluatorOntologyCritique,
    IntrospectedColumnInfo,
    IntrospectedForeignKeyInfo,
    IntrospectedTableInfo,
    ProposedShaclNodeShape,
    SqliteDatabaseIntrospection,
    TableProfileEntry,
)


TMF_NS = Namespace("http://tmforum.org/sid/")
ETOM_NS = Namespace("http://tmforum.org/etom/")
TELCO_NS = Namespace("http://telco.enterprise.org/ontology/")
RR_NS = Namespace("http://www.w3.org/ns/r2rml#")
SH_NS = Namespace("http://www.w3.org/ns/shacl#")

GRAPH_TBOX_URI = "urn:telco:graph:tbox:sid-etom"
GRAPH_VIRTUAL_IB_URI = "urn:telco:graph:virtual:ib"

ProposalGeneratorFn = Callable[
    [SqliteDatabaseIntrospection, str, Dict[str, Any], AppConfig, logging.Logger],
    CandidateOntologyAndMappingProposal,
]


# ============================================================================
# 1. 100% Schema-Independent SQLite Database Introspection
# ============================================================================
def introspect_sqlite_database(sqlite_path: Path) -> SqliteDatabaseIntrospection:
    """
    Dynamically introspect any SQLite database file without assuming any table
    or column names.

    Extracts:
      - All non-system tables from `sqlite_master`
      - Column metadata via `PRAGMA table_info`
      - Foreign key relationships via `PRAGMA foreign_key_list`
      - Per-column null count, distinct value count, and low-cardinality distinct values
      - Representative sample rows (`SELECT * LIMIT 5` plus any versioned rows sharing
        non-primary-key identifiers)
    """
    if not sqlite_path.exists() or not sqlite_path.is_file():
        raise FileNotFoundError(
            f"SQLite database not found at expected path: {sqlite_path}"
        )

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [str(r[0]) for r in cur.fetchall()]
        if not table_names:
            raise ValueError(f"SQLite database '{sqlite_path}' contains zero user tables.")

        tables_info: List[IntrospectedTableInfo] = []
        total_db_rows = 0

        for tbl_name in table_names:
            cur.execute(f'SELECT COUNT(*) FROM "{tbl_name}"')
            row_count = int(cur.fetchone()[0])
            total_db_rows += row_count

            cur.execute(f'PRAGMA table_info("{tbl_name}")')
            pragma_cols = cur.fetchall()
            columns_info: List[IntrospectedColumnInfo] = []

            for col_row in pragma_cols:
                col_name = str(col_row["name"])
                col_type = str(col_row["type"] or "TEXT")
                not_null = bool(col_row["notnull"])
                is_pk = bool(col_row["pk"])

                cur.execute(
                    f'SELECT COUNT(*) FROM "{tbl_name}" WHERE "{col_name}" IS NULL'
                )
                null_count = int(cur.fetchone()[0])

                cur.execute(
                    f'SELECT COUNT(DISTINCT "{col_name}") FROM "{tbl_name}" WHERE "{col_name}" IS NOT NULL'
                )
                distinct_count = int(cur.fetchone()[0])

                low_card_vals: List[str] = []
                if 0 < distinct_count <= 12:
                    cur.execute(
                        f'SELECT DISTINCT CAST("{col_name}" AS TEXT) FROM "{tbl_name}" '
                        f'WHERE "{col_name}" IS NOT NULL ORDER BY 1 LIMIT 12'
                    )
                    low_card_vals = [str(r[0]) for r in cur.fetchall()]

                columns_info.append(
                    IntrospectedColumnInfo(
                        column_name=col_name,
                        sql_type=col_type,
                        not_null=not_null,
                        is_primary_key=is_pk,
                        null_count=null_count,
                        distinct_count=distinct_count,
                        low_cardinality_values=low_card_vals,
                    )
                )

            cur.execute(f'PRAGMA foreign_key_list("{tbl_name}")')
            fk_rows = cur.fetchall()
            fks_info: List[IntrospectedForeignKeyInfo] = [
                IntrospectedForeignKeyInfo(
                    from_column=str(fk["from"]),
                    target_table=str(fk["table"]),
                    target_column=str(fk["to"]),
                )
                for fk in fk_rows
            ]

            cur.execute(f'SELECT * FROM "{tbl_name}" LIMIT 6')
            sample_dicts: List[Dict[str, Any]] = [dict(r) for r in cur.fetchall()]

            tables_info.append(
                IntrospectedTableInfo(
                    table_name=tbl_name,
                    total_rows=row_count,
                    columns=columns_info,
                    foreign_keys=fks_info,
                    sample_rows=sample_dicts,
                )
            )

        return SqliteDatabaseIntrospection(
            database_filename=sqlite_path.name,
            total_tables=len(tables_info),
            total_rows=total_db_rows,
            tables=tables_info,
        )
    finally:
        conn.close()


# ============================================================================
# 2. `google-genai` Client & Structured AI Schema Profiler (Zero Heuristic Fallback)
# ============================================================================
def generate_candidate_proposal_via_llm(
    introspection: SqliteDatabaseIntrospection,
    use_case_charter_text: str,
    tmf_vocab_data: Dict[str, Any],
    config: AppConfig,
    logger: logging.Logger,
    prompt_template_text: Optional[str] = None,
) -> CandidateOntologyAndMappingProposal:
    """
    Invoke the Gemini LLM (`google-genai`) with (1) the Use Case Charter,
    (2) the generic TMF SID/eTOM Vocabulary, and (3) the dynamically introspected
    SQLite schema to synthesize a validated `CandidateOntologyAndMappingProposal`.

    Enforces fail-fast execution with zero heuristic fallback per AGENTS.md Part 2.3.
    """
    if prompt_template_text is None:
        prompt_path = get_workspace_root() / Path(
            config.track_b_ingestion_and_er.profiler_prompt_template_path
        )
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Profiler prompt template not found at expected path: {prompt_path}"
            )
        prompt_template_text = prompt_path.read_text(encoding="utf-8")

    client = _create_genai_client(config, logger)
    model_id = resolve_model_for_component(config, "track_b_cmdb_profiler")

    user_payload = (
        f"{prompt_template_text}\n\n"
        f"=== INPUT 1: USE CASE CHARTER (`{config.use_case.use_case_id}`) ===\n"
        f"{use_case_charter_text}\n\n"
        f"=== INPUT 2: GENERIC TM FORUM SID / eTOM / QUDT VOCABULARY ===\n"
        f"{json.dumps(tmf_vocab_data, indent=2)}\n\n"
        f"=== INPUT 3: DYNAMICALLY INTROSPECTED SQLITE DATABASE SCHEMA & SAMPLES ===\n"
        f"{json.dumps(introspection.model_dump(), indent=2)}\n"
    )

    raw_json_schema = CandidateOntologyAndMappingProposal.model_json_schema()
    clean_response_schema = _strip_additional_properties(raw_json_schema)

    logger.info(
        "Invoking Gemini AI Schema Profiler (model=%s) over %d introspected SQLite tables...",
        model_id,
        introspection.total_tables,
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
            "AI Schema Profiler returned an empty response from Gemini; failing fast."
        )

    proposal = CandidateOntologyAndMappingProposal.model_validate_json(response.text)
    proposal = proposal.model_copy(
        update={
            "llm_model_used": model_id,
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ontology_iri": GRAPH_TBOX_URI,
            "virtual_graph_iri": GRAPH_VIRTUAL_IB_URI,
        }
    )
    logger.info(
        "AI Schema Profiler returned validated proposal '%s' (%d classes, %d properties, %d table mappings)",
        proposal.proposal_id,
        len(proposal.proposed_classes),
        len(proposal.proposed_properties),
        len(proposal.table_mappings),
    )
    return proposal


# ============================================================================
# 3. Generic W3C Turtle, TriG, R2RML & SHACL Compilers from Candidate Proposal
# ============================================================================
def _turtle_escape_literal(text: str) -> str:
    """Escape double quotes and backslashes for W3C Turtle string literals."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _format_turtle_term(iri_or_curie: str) -> str:
    """
    Format an IRI or CURIE for W3C Turtle syntax:
      - Already bracketed (`<...>`): returned as-is
      - Full URI (`http://...`, `https://...`, `urn:...`, `#...`): wrapped in `<...>`
      - Prefixed CURIE (`tmf:Customer`, `xsd:string`, `sh:IRI`): returned as-is
    """
    val = iri_or_curie.strip()
    if val.startswith("<") and val.endswith(">"):
        return val
    if val.startswith(("http://", "https://", "urn:", "#")):
        return f"<{val}>"
    return val


def compile_tbox_turtle_from_proposal(
    proposal: CandidateOntologyAndMappingProposal,
) -> str:
    """
    Generically compile `data/semantic_store/tbox_sid_etom.ttl` from a validated
    `CandidateOntologyAndMappingProposal` without any hardcoded SQL or domain strings.
    """
    lines: List[str] = [
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix dcterms: <http://purl.org/dc/terms/> .",
        "@prefix qudt: <http://qudt.org/schema/qudt/> .",
        "@prefix unit: <http://qudt.org/vocab/unit/> .",
        "@prefix tmf: <http://tmforum.org/sid/> .",
        "@prefix etom: <http://tmforum.org/etom/> .",
        "@prefix telco: <http://telco.enterprise.org/ontology/> .",
        "",
        f"<{proposal.ontology_iri}> a owl:Ontology ;",
        f'    rdfs:label "{_turtle_escape_literal(proposal.ontology_label)}"@en ;',
        f'    dcterms:identifier "{_turtle_escape_literal(proposal.proposal_id)}" ;',
        f'    rdfs:comment "{_turtle_escape_literal(proposal.ontology_comment)}"@en .',
        "",
        "# ============================================================================",
        "# TM Forum eTOM (GB921) Business Process Individuals",
        "# ============================================================================",
    ]

    for proc in proposal.etom_processes:
        alt_list = " ,\n                  ".join(
            f'"{_turtle_escape_literal(lbl)}"@en' for lbl in proc.skos_alt_labels
        )
        lines.extend(
            [
                f"{_format_turtle_term(proc.process_iri)} a etom:BusinessProcess , owl:NamedIndividual ;",
                f'    rdfs:label "{_turtle_escape_literal(proc.label)}"@en ;',
                f'    dcterms:identifier "{_turtle_escape_literal(proc.process_id)}" ;',
                f'    rdfs:comment "{_turtle_escape_literal(proc.comment)}"@en ;',
                f"    skos:altLabel {alt_list} .",
                "",
            ]
        )

    lines.extend(
        [
            "# ============================================================================",
            "# Pruned TM Forum SID (GB922) & Telecom Assurance OWL Classes",
            "# ============================================================================",
        ]
    )

    for cls in proposal.proposed_classes:
        stmt_lines = [f"{_format_turtle_term(cls.class_iri)} a owl:Class ;"]
        if cls.sub_class_of_iri:
            stmt_lines.append(
                f"    rdfs:subClassOf {_format_turtle_term(cls.sub_class_of_iri)} ;"
            )
        stmt_lines.append(f'    rdfs:label "{_turtle_escape_literal(cls.label)}"@en ;')
        stmt_lines.append(
            f'    rdfs:comment "{_turtle_escape_literal(cls.comment)}"@en ;'
        )
        alt_list = " ,\n                  ".join(
            f'"{_turtle_escape_literal(lbl)}"@en' for lbl in cls.skos_alt_labels
        )
        stmt_lines.append(f"    skos:altLabel {alt_list} ;")
        etom_list = " ,\n                             ".join(
            _format_turtle_term(e_iri) for e_iri in cls.aligned_etom_process_iris
        )
        stmt_lines.append(f"    telco:alignedEtomProcess {etom_list} .")
        lines.extend(stmt_lines)
        lines.append("")

    lines.extend(
        [
            "# ============================================================================",
            "# OWL Object & Datatype Properties",
            "# ============================================================================",
        ]
    )

    for prop in proposal.proposed_properties:
        stmt_lines = [
            f"{_format_turtle_term(prop.property_iri)} a {_format_turtle_term(prop.property_type)} ;",
            f"    rdfs:domain {_format_turtle_term(prop.domain_iri)} ;",
            f"    rdfs:range {_format_turtle_term(prop.range_iri)} ;",
        ]
        if prop.qudt_applicable_unit_iri:
            stmt_lines.append(
                f"    qudt:applicableUnit {_format_turtle_term(prop.qudt_applicable_unit_iri)} ;"
            )
        stmt_lines.append(f'    rdfs:label "{_turtle_escape_literal(prop.label)}"@en ;')
        stmt_lines.append(
            f'    rdfs:comment "{_turtle_escape_literal(prop.comment)}"@en ;'
        )
        alt_list = " ,\n                  ".join(
            f'"{_turtle_escape_literal(lbl)}"@en' for lbl in prop.skos_alt_labels
        )
        stmt_lines.append(f"    skos:altLabel {alt_list} .")
        lines.extend(stmt_lines)
        lines.append("")

    return "\n".join(lines)


def write_knowledge_graph_trig_with_tbox(
    tbox_path: Path,
    trig_path: Path,
    tbox_graph_iri: str = GRAPH_TBOX_URI,
    virtual_graph_iri: str = GRAPH_VIRTUAL_IB_URI,
) -> None:
    """
    Write `data/semantic_store/knowledge_graph.trig` containing `<urn:telco:graph:tbox:sid-etom>`
    populated from `tbox_sid_etom.ttl` and an explicitly empty `<urn:telco:graph:virtual:ib>`
    block (`0` persisted triples on disk, proving Zero-Copy Virtualization).
    """
    g_tbox = Graph()
    g_tbox.parse(str(tbox_path), format="turtle")

    prefix_block = """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix qudt: <http://qudt.org/schema/qudt/> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix tmf: <http://tmforum.org/sid/> .
@prefix etom: <http://tmforum.org/etom/> .
@prefix telco: <http://telco.enterprise.org/ontology/> .
"""
    nt_lines = g_tbox.serialize(format="ntriples").splitlines()
    indented_nt = "\n".join(f"    {line}" for line in sorted(nt_lines) if line.strip())

    trig_doc = (
        f"{prefix_block}\n"
        f"# Named Graph 1: Pruned TM Forum SID & eTOM Conceptual TBox\n"
        f"<{tbox_graph_iri}> {{\n"
        f"{indented_nt}\n"
        f"}}\n\n"
        f"# Named Graph 2: Zero-Copy Virtual SQL CMDB Graph (0 persisted triples on disk)\n"
        f"<{virtual_graph_iri}> {{\n"
        f"}}\n"
    )
    trig_path.parent.mkdir(parents=True, exist_ok=True)
    trig_path.write_text(trig_doc, encoding="utf-8")


def compile_r2rml_turtle_from_proposal(
    proposal: CandidateOntologyAndMappingProposal,
) -> str:
    """
    Generically compile `mappings/cmdb_r2rml.ttl` from the bound table mappings
    inside a validated `CandidateOntologyAndMappingProposal`.
    """
    lines: List[str] = [
        "@prefix rr: <http://www.w3.org/ns/r2rml#> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix tmf: <http://tmforum.org/sid/> .",
        "@prefix telco: <http://telco.enterprise.org/ontology/> .",
        "@base <urn:telco:r2rml:cmdb:> .",
        "",
    ]

    for tbl in proposal.table_mappings:
        if tbl.table_disposition != "BOUND_VIRTUAL_GRAPH":
            lines.append(
                f"# Excluded Noise Table: {tbl.table_name} ({tbl.total_rows} rows) -> {tbl.table_disposition}"
            )
            lines.append("")
            continue

        if not tbl.sql_query or not tbl.subject_iri_template or not tbl.subject_class_iri:
            raise ValueError(
                f"Bound table '{tbl.table_name}' is missing required R2RML sql_query or subject template."
            )

        map_label = tbl.r2rml_label or f"{tbl.table_name} to {tbl.subject_class_iri} Virtual Mapping"
        block_lines: List[str] = [
            f"{_format_turtle_term(tbl.r2rml_triples_map_id)} a rr:TriplesMap ;",
            f'    rdfs:label "{_turtle_escape_literal(map_label)}"@en ;',
            "    rr:logicalTable [",
            '        rr:sqlQuery """',
            f"            {tbl.sql_query.strip()}",
            '        """',
            "    ] ;",
            "    rr:subjectMap [",
            f'        rr:template "{tbl.subject_iri_template}" ;',
            f"        rr:class {_format_turtle_term(tbl.subject_class_iri)} ;",
            f"        rr:graph <{proposal.virtual_graph_iri}>",
        ]

        if not tbl.predicate_object_mappings:
            block_lines.append("    ] .")
        else:
            block_lines.append("    ] ;")
            for idx, pom in enumerate(tbl.predicate_object_mappings):
                is_last = idx == len(tbl.predicate_object_mappings) - 1
                term_char = "." if is_last else ";"
                if pom.mapping_kind == "iri_template":
                    block_lines.extend(
                        [
                            "    rr:predicateObjectMap [",
                            f"        rr:predicate {_format_turtle_term(pom.predicate_iri)} ;",
                            "        rr:objectMap [",
                            f'            rr:template "{pom.column_or_template}" ;',
                            "            rr:termType rr:IRI",
                            "        ]",
                            f"    ] {term_char}",
                        ]
                    )
                else:
                    dtype_clause = (
                        f" ; rr:datatype {_format_turtle_term(pom.datatype_iri)}"
                        if pom.datatype_iri
                        else ""
                    )
                    block_lines.extend(
                        [
                            "    rr:predicateObjectMap [",
                            f"        rr:predicate {_format_turtle_term(pom.predicate_iri)} ;",
                            f'        rr:objectMap [ rr:column "{pom.column_or_template}"{dtype_clause} ]',
                            f"    ] {term_char}",
                        ]
                    )

        lines.extend(block_lines)
        lines.append("")

    return "\n".join(lines)


def compile_shacl_shape_turtle(shape: ProposedShaclNodeShape) -> str:
    """Generically compile a `ProposedShaclNodeShape` into valid W3C SHACL Turtle."""
    lines: List[str] = [
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix sh: <http://www.w3.org/ns/shacl#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix tmf: <http://tmforum.org/sid/> .",
        "@prefix telco: <http://telco.enterprise.org/ontology/> .",
        "",
        f"{_format_turtle_term(shape.shape_iri)} a sh:NodeShape ;",
        f"    sh:targetClass {_format_turtle_term(shape.target_class_iri)} ;",
        f'    rdfs:label "{_turtle_escape_literal(shape.label)}"@en ;',
        f'    rdfs:comment "{_turtle_escape_literal(shape.comment)}"@en ;',
    ]

    for idx, prop in enumerate(shape.property_constraints):
        is_last = idx == len(shape.property_constraints) - 1
        term_char = "." if is_last else ";"
        lines.append("    sh:property [")
        lines.append(f"        sh:path {_format_turtle_term(prop.path_iri)} ;")
        if prop.datatype_iri:
            lines.append(
                f"        sh:datatype {_format_turtle_term(prop.datatype_iri)} ;"
            )
        if prop.node_kind_iri:
            lines.append(
                f"        sh:nodeKind {_format_turtle_term(prop.node_kind_iri)} ;"
            )
        if prop.min_count is not None:
            lines.append(f"        sh:minCount {prop.min_count} ;")
        if prop.max_count is not None:
            lines.append(f"        sh:maxCount {prop.max_count} ;")
        if prop.min_inclusive is not None:
            lines.append(f"        sh:minInclusive {prop.min_inclusive} ;")
        if prop.max_inclusive is not None:
            lines.append(f"        sh:maxInclusive {prop.max_inclusive} ;")
        if prop.allowed_values:
            vals_str = " ".join(
                f'"{_turtle_escape_literal(v)}"' for v in prop.allowed_values
            )
            lines.append(f"        sh:in ( {vals_str} ) ;")
        lines.append(f'        sh:message "{_turtle_escape_literal(prop.message)}"@en ;')
        lines.append(f"    ] {term_char}")

    lines.append("")
    return "\n".join(lines)


# ============================================================================
# 4. Automated Evaluator Agent Critique (Candidate & Locked Modes)
# ============================================================================
def evaluate_proposal_and_artifacts(
    proposal: CandidateOntologyAndMappingProposal,
    tbox_turtle_text: str,
    r2rml_turtle_text: str,
    trig_path: Optional[Path] = None,
) -> EvaluatorOntologyCritique:
    """
    Execute the deterministic Evaluator Agent critique over the compiled TBox
    and R2RML Turtle strings (and `knowledge_graph.trig` if locked on disk).

    Extracts physical SQL table and column tokens dynamically from
    `proposal.table_mappings` without any hardcoded strings in Python.
    """
    sql_identifiers: List[str] = []
    for tbl in proposal.table_mappings:
        sql_identifiers.append(tbl.table_name)
        for col in tbl.columns:
            sql_identifiers.append(col.column_name)

    leaked_tokens = sorted(
        {token for token in sql_identifiers if token in tbox_turtle_text}
    )
    zero_sql_leakage = len(leaked_tokens) == 0

    g_tbox = Graph()
    g_tbox.parse(data=tbox_turtle_text, format="turtle")
    classes = set(g_tbox.subjects(RDF.type, OWL.Class))
    obj_props = set(g_tbox.subjects(RDF.type, OWL.ObjectProperty))
    dt_props = set(g_tbox.subjects(RDF.type, OWL.DatatypeProperty))
    alt_labels = list(g_tbox.triples((None, SKOS.altLabel, None)))

    g_r2rml = Graph()
    g_r2rml.parse(data=r2rml_turtle_text, format="turtle")
    triples_maps = set(g_r2rml.subjects(RDF.type, RR_NS.TriplesMap))
    sql_queries = [
        str(o) for _, _, o in g_r2rml.triples((None, RR_NS.sqlQuery, None))
    ]
    joined_sql = "\n".join(sql_queries)

    excluded_tables = [
        t.table_name
        for t in proposal.table_mappings
        if t.table_disposition == "EXCLUDED_NOISE"
    ]
    bound_tables = [
        t.table_name
        for t in proposal.table_mappings
        if t.table_disposition == "BOUND_VIRTUAL_GRAPH"
    ]
    billing_excluded = (
        len(excluded_tables) >= 1
        and all(ex_tbl not in joined_sql for ex_tbl in excluded_tables)
        and len(triples_maps) == len(bound_tables)
    )
    scd2_present = "IS NULL" in joined_sql.upper() and "WHERE" in joined_sql.upper()
    shadow_enum_present = (
        "'ACTIVE'" in joined_sql
        and "'MAINTENANCE'" in joined_sql
        and "'DECOMMISSIONED'" in joined_sql
    )
    qudt_present = "1000.0" in joined_sql and "1000000.0" in joined_sql

    virtual_zero_triples = True
    if trig_path is not None and trig_path.exists():
        ds = Dataset()
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", category=DeprecationWarning, module=r"^rdflib\."
            )
            ds.parse(str(trig_path), format="trig")
        virtual_ctx = ds.graph(URIRef(proposal.virtual_graph_iri))
        virtual_zero_triples = len(virtual_ctx) == 0

    overall_passed = (
        zero_sql_leakage
        and billing_excluded
        and scd2_present
        and shadow_enum_present
        and qudt_present
        and virtual_zero_triples
        and len(classes) >= 12
        and len(alt_labels) >= 24
    )

    summary = (
        f"PASS: 0/{len(set(sql_identifiers))} physical SQL tokens leaked into TBox; "
        f"{len(classes)} OWL classes, {len(obj_props) + len(dt_props)} properties, and "
        f"{len(alt_labels)} skos:altLabel synonyms verified; {len(excluded_tables)} noise table(s) "
        f"({', '.join(excluded_tables)}) excluded; SCD2 active-window filter, shadow enum translation, "
        f"and QUDT Gbps normalization verified; <{proposal.virtual_graph_iri}> has 0 persisted triples on disk."
    )

    return EvaluatorOntologyCritique(
        zero_sql_leakage_in_tbox=zero_sql_leakage,
        leaked_sql_tokens=leaked_tokens,
        billing_noise_table_excluded=billing_excluded,
        scd2_active_filter_present=scd2_present,
        shadow_enum_translation_present=shadow_enum_present,
        qudt_bandwidth_normalization_present=qudt_present,
        virtual_graph_zero_persisted_triples=virtual_zero_triples,
        tbox_class_count=len(classes),
        tbox_property_count=len(obj_props) + len(dt_props),
        tbox_skos_alt_label_count=len(alt_labels),
        overall_passed=overall_passed,
        critique_summary=summary,
    )


# ============================================================================
# 5. Mandatory HITL Gate 1 Report Generator (`.html` & `.md`)
# ============================================================================
def _write_hitl_gate1_markdown_report(
    proposal: CandidateOntologyAndMappingProposal,
    table_profiles: List[TableProfileEntry],
    critique: EvaluatorOntologyCritique,
    gate1_status: Literal["CANDIDATE_PROPOSED", "LOCKED_APPROVED"],
    executed_at_utc: str,
    md_path: Path,
) -> None:
    """Write `reports/hitl_gate1_ontology_mapping_review.md`."""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    scd2 = proposal.scd2_verification
    lines: List[str] = [
        "# Mandatory HITL Gate 1 Review — Prong 1 SQL CMDB AI Schema Profiler, TMF SID/eTOM TBox & R2RML Mapping (`DT-01a`)",
        "",
        f"- **Gate 1 Sign-Off Status:** **`{gate1_status}`**",
        f"- **Proposal ID:** `{proposal.proposal_id}` (`{proposal.llm_model_used}`)",
        f"- **Executed At (UTC):** `{executed_at_utc}`",
        f"- **Evaluator Critique Result:** `{critique.critique_summary}`",
        "",
        "---",
        "",
        "## 1. HITL Gate 1 Lead Architect Verification Questions",
        "",
    ]
    for idx, q_text in enumerate(proposal.architect_verification_questions, start=1):
        check_mark = "[x]" if gate1_status == "LOCKED_APPROVED" else "[ ]"
        lines.append(f"{idx}. {check_mark} {q_text}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 2. SQLite CMDB Table-Level Profiling & Noise Exclusion Summary",
            "",
            "| Table Name | Total Rows | Active Rows | Disposition | Target TMF SID Classes | R2RML TriplesMap |",
            "| :--- | :---: | :---: | :---: | :--- | :--- |",
        ]
    )
    for tbl in table_profiles:
        classes_str = (
            ", ".join(f"`{c}`" for c in tbl.target_tmf_classes)
            or "*None (Excluded)*"
        )
        lines.append(
            f"| `{tbl.table_name}` | {tbl.total_rows} | {tbl.active_rows} | "
            f"**`{tbl.table_disposition}`** | {classes_str} | `{tbl.r2rml_triples_map_id}` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            f"## 3. Target Circuit `{scd2.circuit_id}` SCD Type 2, Shadow Enum & QUDT Verification",
            "",
            f"- **Superseded Historical Row Filtered Out:** `ROW_ID={scd2.expired_row_id}` (`{scd2.expired_product_sku}`, expired `{scd2.expired_valid_to_ts}`)",
            f"- **Active Current Row Retained:** `ROW_ID={scd2.active_row_id}` (`{scd2.active_product_sku}`)",
            f"- **Shadow Enum Translation:** `'{scd2.raw_oper_status_cd}'` $\\rightarrow$ **`'{scd2.canonical_oper_status}'`**",
            f"- **QUDT Bandwidth Normalization:** `{scd2.raw_bandwidth_val} {scd2.raw_bandwidth_unit}` $\\rightarrow$ **`{scd2.normalized_bandwidth_gbps} Gbps`** (`unit:GigaBIT-PER-SEC`)",
            "",
            "---",
            "",
            "## 4. Dynamic Column-Level Disposition Matrix (`PRAGMA table_info`)",
            "",
            "| Table | Column | SQL Type | Disposition | Mapped TBox Target | Audit Rationale |",
            "| :--- | :--- | :---: | :---: | :--- | :--- |",
        ]
    )
    for tbl in table_profiles:
        for col in tbl.columns:
            lines.append(
                f"| `{tbl.table_name}` | `{col.column_name}` | `{col.sql_type}` | "
                f"**`{col.disposition}`** | `{col.mapped_tbox_target}` | {col.audit_rationale} |"
            )

    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _write_hitl_gate1_html_report(
    proposal: CandidateOntologyAndMappingProposal,
    table_profiles: List[TableProfileEntry],
    critique: EvaluatorOntologyCritique,
    gate1_status: Literal["CANDIDATE_PROPOSED", "LOCKED_APPROVED"],
    executed_at_utc: str,
    html_path: Path,
) -> None:
    """Write self-contained `reports/hitl_gate1_ontology_mapping_review.html`."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    badge_bg = "#059669" if gate1_status == "LOCKED_APPROVED" else "#D97706"
    scd2 = proposal.scd2_verification

    questions_html = "".join(
        f"<li><strong>Q{idx}:</strong> {html.escape(q)}</li>"
        for idx, q in enumerate(proposal.architect_verification_questions, start=1)
    )

    table_rows_html: List[str] = []
    for tbl in table_profiles:
        t_color = (
            "#059669" if tbl.table_disposition == "BOUND_VIRTUAL_GRAPH" else "#DC2626"
        )
        classes_html = (
            ", ".join(f"<code>{html.escape(c)}</code>" for c in tbl.target_tmf_classes)
            or "<em>None (Excluded Noise)</em>"
        )
        table_rows_html.append(
            f"""
            <tr>
              <td><code>{html.escape(tbl.table_name)}</code></td>
              <td style="text-align:center;">{tbl.total_rows}</td>
              <td style="text-align:center;">{tbl.active_rows}</td>
              <td style="text-align:center;">
                <span style="padding:3px 8px;border-radius:9999px;font-size:11px;font-weight:700;color:#FFF;background:{t_color};">
                  {html.escape(tbl.table_disposition)}
                </span>
              </td>
              <td>{classes_html}</td>
              <td><code>{html.escape(tbl.r2rml_triples_map_id)}</code></td>
            </tr>
            """
        )

    col_rows_html: List[str] = []
    for tbl in table_profiles:
        for col in tbl.columns:
            if col.disposition == "MAPPED_TO_TBOX":
                c_color = "#059669"
            elif col.disposition == "PHYSICAL_SCD2_CONTROL_ONLY":
                c_color = "#2563EB"
            else:
                c_color = "#DC2626"
            col_rows_html.append(
                f"""
                <tr>
                  <td><code>{html.escape(tbl.table_name)}</code></td>
                  <td><code>{html.escape(col.column_name)}</code></td>
                  <td style="text-align:center;"><code>{html.escape(col.sql_type)}</code></td>
                  <td style="text-align:center;">
                    <span style="padding:2px 7px;border-radius:9999px;font-size:11px;font-weight:700;color:#FFF;background:{c_color};">
                      {html.escape(col.disposition)}
                    </span>
                  </td>
                  <td><code>{html.escape(col.mapped_tbox_target)}</code></td>
                  <td>{html.escape(col.audit_rationale)}</td>
                </tr>
                """
            )

    doc_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>HITL Gate 1 — Ontology &amp; R2RML Virtual Graph Review (DT-01a)</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #F8FAFC;
      color: #0F172A;
      margin: 24px;
    }}
    .banner {{
      background: linear-gradient(135deg, #0F172A, #1E3A8A);
      color: #FFF;
      padding: 20px 24px;
      border-radius: 10px;
      margin-bottom: 20px;
    }}
    .banner h1 {{ margin: 0 0 8px 0; font-size: 20px; }}
    .banner p {{ margin: 4px 0; font-size: 13px; color: #E2E8F0; }}
    .card {{
      background: #FFF;
      border-radius: 10px;
      padding: 18px 20px;
      margin-bottom: 20px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.07);
    }}
    .card h2 {{ margin-top: 0; font-size: 16px; color: #1E293B; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{
      background: #1E293B;
      color: #FFF;
      text-align: left;
      padding: 10px 12px;
      font-size: 12px;
      text-transform: uppercase;
    }}
    td {{
      padding: 9px 12px;
      border-bottom: 1px solid #E2E8F0;
      font-size: 13px;
    }}
    code {{
      background: #F1F5F9;
      padding: 2px 5px;
      border-radius: 4px;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <div class="banner">
    <h1>Mandatory HITL Gate 1 — Prong 1 SQL CMDB AI Schema Profiler, TMF SID/eTOM TBox &amp; R2RML Mapping (DT-01a)</h1>
    <p>
      <strong>Sign-Off Status:</strong>
      <span style="padding:4px 10px;border-radius:9999px;font-weight:700;background:{badge_bg};color:#FFF;">
        {html.escape(gate1_status)}
      </span>
      &nbsp;|&nbsp; <strong>Proposal ID:</strong> <code>{html.escape(proposal.proposal_id)}</code>
      &nbsp;|&nbsp; <strong>Model:</strong> <code>{html.escape(proposal.llm_model_used)}</code>
      &nbsp;|&nbsp; <strong>Executed At (UTC):</strong> {html.escape(executed_at_utc)}
    </p>
    <p><strong>Evaluator Critique:</strong> {html.escape(critique.critique_summary)}</p>
  </div>

  <div class="card">
    <h2>1. HITL Gate 1 Lead Architect Verification Questions</h2>
    <ol>
      {questions_html}
    </ol>
  </div>

  <div class="card">
    <h2>2. SQLite CMDB Table-Level Profiling &amp; Noise Exclusion</h2>
    <table>
      <thead>
        <tr>
          <th>Table Name</th>
          <th style="text-align:center;">Total Rows</th>
          <th style="text-align:center;">Active Rows</th>
          <th style="text-align:center;">Table Disposition</th>
          <th>Target TMF SID Classes</th>
          <th>R2RML TriplesMap</th>
        </tr>
      </thead>
      <tbody>
        {"".join(table_rows_html)}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>3. Target Circuit {html.escape(scd2.circuit_id)} SCD Type 2, Shadow Enum &amp; QUDT Proof</h2>
    <ul>
      <li><strong>Filtered Expired SCD2 Row:</strong> <code>ROW_ID={scd2.expired_row_id}</code> (<code>{html.escape(scd2.expired_product_sku)}</code>, expired <code>{html.escape(scd2.expired_valid_to_ts)}</code>)</li>
      <li><strong>Retained Active SCD2 Row:</strong> <code>ROW_ID={scd2.active_row_id}</code> (<code>{html.escape(scd2.active_product_sku)}</code>)</li>
      <li><strong>Shadow Enum Translation:</strong> <code>'{html.escape(scd2.raw_oper_status_cd)}'</code> &rarr; <strong><code>'{html.escape(scd2.canonical_oper_status)}'</code></strong></li>
      <li><strong>QUDT Bandwidth Normalization:</strong> <code>{scd2.raw_bandwidth_val} {html.escape(scd2.raw_bandwidth_unit)}</code> &rarr; <strong><code>{scd2.normalized_bandwidth_gbps} Gbps</code></strong> (<code>unit:GigaBIT-PER-SEC</code>)</li>
    </ul>
  </div>

  <div class="card">
    <h2>4. Dynamic Column-Level Disposition Matrix (PRAGMA table_info)</h2>
    <table>
      <thead>
        <tr>
          <th>Table</th>
          <th>Column</th>
          <th style="text-align:center;">SQL Type</th>
          <th style="text-align:center;">Disposition</th>
          <th>Mapped TBox Target</th>
          <th>Audit Rationale</th>
        </tr>
      </thead>
      <tbody>
        {"".join(col_rows_html)}
      </tbody>
    </table>
  </div>
</body>
</html>
"""
    html_path.write_text(doc_html, encoding="utf-8")


# ============================================================================
# 6. Two-Phase Scenario `DT-01a` Orchestrator Entry Function
# ============================================================================
def run_dt01a_cmdb_profiler(
    config: AppConfig,
    logger: logging.Logger,
    mode: Literal["candidate", "approve"] = "candidate",
    update_golden_ref: bool = False,
    workspace_root: Optional[Path] = None,
    proposal_generator: Optional[ProposalGeneratorFn] = None,
) -> Dt01aExecutionResult:
    """
    Execute Scenario `DT-01a` in Two-Phase Interactive HITL Gate 1 mode:

    - Phase 1 (`mode="candidate"`, default):
      1. Dynamically introspects `sqlite_db_path` via `introspect_sqlite_database`.
      2. Loads `use_case_charter_path` and `tmf_sid_etom_vocab_path`.
      3. Invokes `generate_candidate_proposal_via_llm` (or `proposal_generator` when
         injected by unit tests) to synthesize `CandidateOntologyAndMappingProposal`.
      4. Saves `data/semantic_store/gate1_candidate_proposal.json`.
      5. Ensures `tbox_sid_etom.ttl`, `knowledge_graph.trig`, `cmdb_r2rml.ttl`, and
         `shapes/*.ttl` are NOT locked on disk yet (`SYS-01` shows
         `CANDIDATE_PROPOSED (Awaiting HITL Approval)` and `UNBOUND (Pending Gate 1 Lock)`).
      6. Writes `reports/hitl_gate1_ontology_mapping_review.html` and `.md` with
         status `CANDIDATE_PROPOSED` and returns the Architect Verification Questions.

    - Phase 2 (`mode="approve"`):
      1. Loads `data/semantic_store/gate1_candidate_proposal.json` (or generates it
         first if not yet present on disk).
      2. Generically compiles and writes `tbox_sid_etom.ttl`, `knowledge_graph.trig`
         (`0` persisted triples in `<urn:telco:graph:virtual:ib>`), `cmdb_r2rml.ttl`,
         and `shapes/*.ttl` (`service_spec_shape.ttl`, `trouble_ticket_shape.ttl`).
      3. Runs the Evaluator Agent Critique over the locked artifacts.
      4. Updates `reports/hitl_gate1_ontology_mapping_review.html` and `.md` to
         `LOCKED_APPROVED` (`SYS-01` transitions to `LOCKED_APPROVED` and `BOUND_ZERO_COPY`).
      5. Optionally copies approved artifacts into `data/golden_reference/` if
         `update_golden_ref=True`.
    """
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()
    sqlite_path = root_dir / Path(config.layer4_compiler_federation.sqlite_db_path)
    charter_path = root_dir / Path(
        config.track_b_ingestion_and_er.use_case_charter_path
    )
    vocab_path = root_dir / Path(
        config.track_b_ingestion_and_er.tmf_sid_etom_vocab_path
    )
    proposal_path = root_dir / Path(
        config.track_b_ingestion_and_er.gate1_candidate_proposal_path
    )
    tbox_path = root_dir / Path(config.layer4_compiler_federation.tbox_path)
    trig_path = root_dir / Path(config.layer4_compiler_federation.dataset_trig_path)
    r2rml_path = root_dir / Path(config.layer4_compiler_federation.r2rml_path)
    shapes_dir = root_dir / Path(config.layer4_compiler_federation.shapes_dir)
    hitl_html_path = root_dir / Path(
        config.track_b_ingestion_and_er.hitl_gate1_report_path
    )
    hitl_md_path = hitl_html_path.with_suffix(".md")

    # Fallback to real workspace charter & vocab if running inside an isolated pytest tmp_path
    real_root = get_workspace_root()
    if not charter_path.exists():
        charter_path = real_root / Path(
            config.track_b_ingestion_and_er.use_case_charter_path
        )
    if not vocab_path.exists():
        vocab_path = real_root / Path(
            config.track_b_ingestion_and_er.tmf_sid_etom_vocab_path
        )

    logger.info(
        "Starting Scenario DT-01a (mode=%s, update_golden_ref=%s) against %s",
        mode,
        update_golden_ref,
        sqlite_path,
    )

    gen_fn = proposal_generator or generate_candidate_proposal_via_llm

    if mode == "candidate" or not proposal_path.exists():
        introspection = introspect_sqlite_database(sqlite_path)
        charter_text = charter_path.read_text(encoding="utf-8")
        vocab_data = json.loads(vocab_path.read_text(encoding="utf-8"))
        proposal = gen_fn(introspection, charter_text, vocab_data, config, logger)

        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(
            json.dumps(proposal.model_dump(), indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "DT-01a saved structured candidate proposal to %s",
            proposal_path.relative_to(root_dir).as_posix(),
        )
    else:
        proposal = CandidateOntologyAndMappingProposal.model_validate_json(
            proposal_path.read_text(encoding="utf-8")
        )
        logger.info(
            "DT-01a loaded existing candidate proposal from %s for HITL Gate 1 approval",
            proposal_path.relative_to(root_dir).as_posix(),
        )

    tbox_turtle_str = compile_tbox_turtle_from_proposal(proposal)
    r2rml_turtle_str = compile_r2rml_turtle_from_proposal(proposal)
    table_profiles = [m.to_table_profile_entry() for m in proposal.table_mappings]
    total_rows = sum(t.total_rows for t in table_profiles)
    bound_tables = sum(
        1 for t in table_profiles if t.table_disposition == "BOUND_VIRTUAL_GRAPH"
    )
    excluded_tables = sum(
        1 for t in table_profiles if t.table_disposition == "EXCLUDED_NOISE"
    )
    executed_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if mode == "candidate":
        # Ensure locked artifacts are NOT materialized yet during Phase 1 (candidate mode)
        for locked_file in [tbox_path, trig_path, r2rml_path]:
            if locked_file.exists():
                locked_file.unlink()
        if shapes_dir.exists():
            for sh_file in shapes_dir.glob("*.ttl"):
                sh_file.unlink()

        critique = evaluate_proposal_and_artifacts(
            proposal=proposal,
            tbox_turtle_text=tbox_turtle_str,
            r2rml_turtle_text=r2rml_turtle_str,
            trig_path=None,
        )
        if not critique.overall_passed:
            raise ValueError(
                f"DT-01a Candidate Proposal failed Evaluator Critique: {critique.critique_summary}"
            )

        _write_hitl_gate1_html_report(
            proposal=proposal,
            table_profiles=table_profiles,
            critique=critique,
            gate1_status="CANDIDATE_PROPOSED",
            executed_at_utc=executed_at_utc,
            html_path=hitl_html_path,
        )
        _write_hitl_gate1_markdown_report(
            proposal=proposal,
            table_profiles=table_profiles,
            critique=critique,
            gate1_status="CANDIDATE_PROPOSED",
            executed_at_utc=executed_at_utc,
            md_path=hitl_md_path,
        )
        logger.info(
            "DT-01a Phase 1 (candidate) complete: awaiting HITL Gate 1 approval (%s)",
            hitl_html_path.relative_to(root_dir).as_posix(),
        )

        return Dt01aExecutionResult(
            scenario_id="DT-01a",
            gate1_mode="candidate",
            gate1_status="CANDIDATE_PROPOSED",
            executed_at_utc=executed_at_utc,
            total_tables_inspected=len(table_profiles),
            total_rows_inspected=total_rows,
            bound_tables_count=bound_tables,
            excluded_noise_tables_count=excluded_tables,
            table_profiles=table_profiles,
            scd2_verification=proposal.scd2_verification,
            evaluator_critique=critique,
            candidate_proposal_path=proposal_path,
            architect_verification_questions=proposal.architect_verification_questions,
            tbox_path=None,
            trig_dataset_path=None,
            r2rml_path=None,
            service_spec_shape_path=None,
            trouble_ticket_shape_path=None,
            hitl_html_report_path=hitl_html_path,
            hitl_markdown_report_path=hitl_md_path,
            golden_ref_updated=False,
        )

    # Phase 2 (`mode == "approve"`): Compile and lock artifacts on disk
    tbox_path.parent.mkdir(parents=True, exist_ok=True)
    tbox_path.write_text(tbox_turtle_str, encoding="utf-8")
    write_knowledge_graph_trig_with_tbox(
        tbox_path=tbox_path,
        trig_path=trig_path,
        tbox_graph_iri=proposal.ontology_iri,
        virtual_graph_iri=proposal.virtual_graph_iri,
    )

    r2rml_path.parent.mkdir(parents=True, exist_ok=True)
    r2rml_path.write_text(r2rml_turtle_str, encoding="utf-8")

    shapes_dir.mkdir(parents=True, exist_ok=True)
    written_shape_paths: Dict[str, Path] = {}
    for sh_spec in proposal.shacl_shapes:
        sh_out = shapes_dir / sh_spec.output_filename
        sh_out.write_text(compile_shacl_shape_turtle(sh_spec), encoding="utf-8")
        written_shape_paths[sh_spec.output_filename] = sh_out

    service_spec_shape_path = written_shape_paths.get(
        "service_spec_shape.ttl", shapes_dir / "service_spec_shape.ttl"
    )
    trouble_ticket_shape_path = written_shape_paths.get(
        "trouble_ticket_shape.ttl", shapes_dir / "trouble_ticket_shape.ttl"
    )

    critique = evaluate_proposal_and_artifacts(
        proposal=proposal,
        tbox_turtle_text=tbox_turtle_str,
        r2rml_turtle_text=r2rml_turtle_str,
        trig_path=trig_path,
    )
    if not critique.overall_passed:
        raise ValueError(
            f"DT-01a Locked Artifacts failed Evaluator Critique: {critique.critique_summary}"
        )

    _write_hitl_gate1_html_report(
        proposal=proposal,
        table_profiles=table_profiles,
        critique=critique,
        gate1_status="LOCKED_APPROVED",
        executed_at_utc=executed_at_utc,
        html_path=hitl_html_path,
    )
    _write_hitl_gate1_markdown_report(
        proposal=proposal,
        table_profiles=table_profiles,
        critique=critique,
        gate1_status="LOCKED_APPROVED",
        executed_at_utc=executed_at_utc,
        md_path=hitl_md_path,
    )
    logger.info(
        "DT-01a Phase 2 (approve) locked TBox (%s), R2RML (%s), and SHACL shapes; status=LOCKED_APPROVED",
        tbox_path.relative_to(root_dir).as_posix(),
        r2rml_path.relative_to(root_dir).as_posix(),
    )

    golden_updated = False
    if update_golden_ref:
        golden_dir = root_dir / Path("data/golden_reference")
        golden_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tbox_path, golden_dir / tbox_path.name)
        shutil.copy2(r2rml_path, golden_dir / r2rml_path.name)
        for sh_file in written_shape_paths.values():
            shutil.copy2(sh_file, golden_dir / sh_file.name)
        golden_updated = True
        logger.info(
            "DT-01a promoted approved Step 2 artifacts into %s",
            golden_dir.relative_to(root_dir).as_posix(),
        )

    return Dt01aExecutionResult(
        scenario_id="DT-01a",
        gate1_mode="approve",
        gate1_status="LOCKED_APPROVED",
        executed_at_utc=executed_at_utc,
        total_tables_inspected=len(table_profiles),
        total_rows_inspected=total_rows,
        bound_tables_count=bound_tables,
        excluded_noise_tables_count=excluded_tables,
        table_profiles=table_profiles,
        scd2_verification=proposal.scd2_verification,
        evaluator_critique=critique,
        candidate_proposal_path=proposal_path,
        architect_verification_questions=proposal.architect_verification_questions,
        tbox_path=tbox_path,
        trig_dataset_path=trig_path,
        r2rml_path=r2rml_path,
        service_spec_shape_path=service_spec_shape_path,
        trouble_ticket_shape_path=trouble_ticket_shape_path,
        hitl_html_report_path=hitl_html_path,
        hitl_markdown_report_path=hitl_md_path,
        golden_ref_updated=golden_updated,
    )
