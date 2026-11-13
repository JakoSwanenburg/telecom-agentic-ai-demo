"""
100% Generic R2RML-to-SQLite Pushdown Compiler (`src/layer4/r2rml_sqlite_compiler.py`).

Architectural Invariants (`IMP-007`):
  1. Zero hardcoded SQL table names, column names, or domain SQL query strings
     exist anywhere in this module.
  2. Fails fast if Track B artifacts (`tbox_sid_etom.ttl`, `knowledge_graph.trig`,
     `cmdb_r2rml.ttl`, `cmdb_installed_base.db`) are missing or if
     `<urn:telco:graph:virtual:ib>` has >0 persisted triples on disk.
  3. Dynamically parses `mappings/cmdb_r2rml.ttl` via `rdflib`, executes the
     discovered SQL pushdown queries against SQLite, and projects RDF triples
     strictly in memory into `<urn:telco:graph:virtual:ib>` on a runtime
     `rdflib.Dataset` clone (never modifying `knowledge_graph.trig` on disk).
  4. Generically projects any SQL `SELECT` column returned by an `rr:TriplesMap`
     query that is not explicitly bound by an `rr:predicateObjectMap` using a
     deterministic `telco:<camelCaseColumn>` datatype property.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import warnings

from rdflib import Dataset, Graph, Literal, Namespace, RDF, URIRef, XSD

from src.config_loader import get_workspace_root
from src.models import (
    AppConfig,
    CompiledR2rmlQueryRecord,
    Scd2AuditSummary,
    VirtualGraphCompileResult,
)

GRAPH_VIRTUAL_IB = URIRef("urn:telco:graph:virtual:ib")
RR_NS = Namespace("http://www.w3.org/ns/r2rml#")
TELCO_NS = Namespace("http://telco.enterprise.org/ontology/")

_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")
_FROM_TABLE_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _column_to_camel_case(column_name: str) -> str:
    """Convert an uppercase/snake_case SQL column name to lowerCamelCase."""
    parts = [p.lower() for p in re.split(r"[_\s]+", column_name.strip()) if p]
    if not parts:
        return "attribute"
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _render_template(template: str, row_dict: Dict[str, Any]) -> str:
    """Substitute `{COL}` placeholders in an R2RML template with SQLite row values."""
    rendered = template
    for col in _TEMPLATE_PLACEHOLDER_RE.findall(template):
        val = row_dict.get(col)
        rendered = rendered.replace(f"{{{col}}}", "" if val is None else str(val).strip())
    return rendered


def _coerce_r2rml_literal(value: Any, datatype_uri: Optional[URIRef]) -> Literal:
    """Coerce a SQLite column value into an RDF Literal matching optional rr:datatype."""
    if datatype_uri is None:
        if isinstance(value, bool):
            return Literal(value, datatype=XSD.boolean)
        if isinstance(value, int):
            return Literal(value, datatype=XSD.integer)
        if isinstance(value, float):
            return Literal(value, datatype=XSD.double)
        return Literal(str(value).strip())

    dt_str = str(datatype_uri)
    if dt_str == str(XSD.double) or dt_str == str(XSD.decimal) or dt_str == str(XSD.float):
        return Literal(float(value), datatype=datatype_uri)
    if dt_str == str(XSD.integer) or dt_str == str(XSD.int):
        return Literal(int(float(value)), datatype=datatype_uri)
    if dt_str == str(XSD.boolean):
        if isinstance(value, bool):
            return Literal(value, datatype=XSD.boolean)
        return Literal(str(value).strip().lower() in {"true", "1", "yes"}, datatype=XSD.boolean)
    if dt_str == str(XSD.date):
        return Literal(str(value).strip(), datatype=XSD.date)
    return Literal(str(value).strip())


def validate_layer4_prerequisites(
    config: AppConfig,
    root_dir: Optional[Path] = None,
) -> Tuple[Path, Path, Path, Path]:
    """
    Fail fast if required Track B artifacts are missing or if `<urn:telco:graph:virtual:ib>`
    on disk has >0 persisted triples.
    """
    resolved_root = root_dir if root_dir is not None else get_workspace_root()
    tbox_path = resolved_root / Path(config.layer4_compiler_federation.tbox_path)
    trig_path = resolved_root / Path(config.layer4_compiler_federation.dataset_trig_path)
    r2rml_path = resolved_root / Path(config.layer4_compiler_federation.r2rml_path)
    sqlite_path = resolved_root / Path(config.layer4_compiler_federation.sqlite_db_path)

    missing = [
        str(p)
        for p in (tbox_path, trig_path, r2rml_path, sqlite_path)
        if not p.exists()
    ]
    if missing:
        raise RuntimeError(
            "Layer 4 prerequisite check failed: missing Track B / CMDB artifacts: "
            f"{missing}. Run DT-01a..c before executing Layer 4 queries."
        )

    ds_check = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds_check.parse(str(trig_path), format="trig")

    disk_virtual_count = len(ds_check.graph(GRAPH_VIRTUAL_IB))
    if disk_virtual_count != 0:
        raise RuntimeError(
            f"Zero-Copy Invariant Violation: <{GRAPH_VIRTUAL_IB}> on disk contains "
            f"{disk_virtual_count} persisted triples (expected 0)."
        )

    return tbox_path, trig_path, r2rml_path, sqlite_path


def compile_r2rml_to_virtual_graph(
    config: AppConfig,
    logger: logging.Logger,
    root_dir: Optional[Path] = None,
) -> Tuple[Dataset, VirtualGraphCompileResult]:
    """
    Load `knowledge_graph.trig` into an in-memory `rdflib.Dataset`, parse
    `mappings/cmdb_r2rml.ttl`, execute all discovered SQL pushdown queries against
    SQLite, and project triples ephemerally into `<urn:telco:graph:virtual:ib>`.
    """
    _, trig_path, r2rml_path, sqlite_path = validate_layer4_prerequisites(
        config, root_dir
    )

    runtime_ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        runtime_ds.parse(str(trig_path), format="trig")

    r2rml_graph = Graph()
    r2rml_graph.parse(str(r2rml_path), format="turtle")

    for prefix, uri in r2rml_graph.namespace_manager.namespaces():
        if prefix:
            runtime_ds.bind(str(prefix), Namespace(str(uri)))

    query_records: List[CompiledR2rmlQueryRecord] = []
    mapped_tables: List[str] = []
    scd2_filtered_tables: List[str] = []
    total_rows_in_mapped = 0
    active_rows_retained = 0

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        sqlite_tables_discovered = sorted(str(r["name"]) for r in table_rows)

        for tm in sorted(r2rml_graph.subjects(RDF.type, RR_NS.TriplesMap), key=str):
            logical_table = r2rml_graph.value(tm, RR_NS.logicalTable)
            subject_map = r2rml_graph.value(tm, RR_NS.subjectMap)
            if logical_table is None or subject_map is None:
                continue

            sql_query_lit = r2rml_graph.value(logical_table, RR_NS.sqlQuery)
            table_name_lit = r2rml_graph.value(logical_table, RR_NS.tableName)
            if sql_query_lit is not None:
                compiled_sql = str(sql_query_lit).strip()
            elif table_name_lit is not None:
                compiled_sql = f'SELECT * FROM "{str(table_name_lit).strip()}"'
            else:
                continue

            subj_template_lit = r2rml_graph.value(subject_map, RR_NS.template)
            subj_class_uri = r2rml_graph.value(subject_map, RR_NS["class"])
            subj_graph_uri = r2rml_graph.value(subject_map, RR_NS.graph) or GRAPH_VIRTUAL_IB
            if subj_template_lit is None or subj_class_uri is None:
                continue

            subj_template = str(subj_template_lit).strip()
            target_graph_ref = URIRef(str(subj_graph_uri))
            target_ctx = runtime_ds.graph(target_graph_ref)

            # Parse predicateObjectMap specs
            pom_specs: List[
                Tuple[URIRef, Optional[str], Optional[str], Optional[URIRef], bool]
            ] = []
            explicitly_bound_cols: Set[str] = set()
            for pom in r2rml_graph.objects(tm, RR_NS.predicateObjectMap):
                pred_uri = r2rml_graph.value(pom, RR_NS.predicate)
                obj_map = r2rml_graph.value(pom, RR_NS.objectMap)
                if pred_uri is None or obj_map is None:
                    continue
                col_lit = r2rml_graph.value(obj_map, RR_NS.column)
                tmpl_lit = r2rml_graph.value(obj_map, RR_NS.template)
                dt_uri = r2rml_graph.value(obj_map, RR_NS.datatype)
                term_type = r2rml_graph.value(obj_map, RR_NS.termType)
                is_iri = term_type == RR_NS.IRI or tmpl_lit is not None

                col_name = str(col_lit).strip() if col_lit is not None else None
                tmpl_str = str(tmpl_lit).strip() if tmpl_lit is not None else None
                if col_name:
                    explicitly_bound_cols.add(col_name)
                if tmpl_str:
                    explicitly_bound_cols.update(_TEMPLATE_PLACEHOLDER_RE.findall(tmpl_str))

                pom_specs.append(
                    (
                        URIRef(str(pred_uri)),
                        col_name,
                        tmpl_str,
                        URIRef(str(dt_uri)) if dt_uri is not None else None,
                        is_iri,
                    )
                )

            t_start = time.perf_counter()
            cursor = conn.execute(compiled_sql)
            rows = cursor.fetchall()
            latency_ms = round((time.perf_counter() - t_start) * 1000.0, 3)

            returned_cols = [desc[0] for desc in (cursor.description or [])]
            unbound_cols = [c for c in returned_cols if c not in explicitly_bound_cols]

            triples_before = len(target_ctx)
            for row in rows:
                row_dict = dict(row)
                subj_uri = URIRef(_render_template(subj_template, row_dict))
                target_ctx.add((subj_uri, RDF.type, URIRef(str(subj_class_uri))))

                for pred_uri, col_name, tmpl_str, dt_uri, is_iri in pom_specs:
                    if tmpl_str is not None:
                        rendered = _render_template(tmpl_str, row_dict)
                        if not rendered:
                            continue
                        obj_term: Any = URIRef(rendered) if is_iri else Literal(rendered)
                        target_ctx.add((subj_uri, pred_uri, obj_term))
                    elif col_name is not None:
                        raw_val = row_dict.get(col_name)
                        if raw_val is None or str(raw_val).strip() == "":
                            continue
                        if is_iri:
                            target_ctx.add((subj_uri, pred_uri, URIRef(str(raw_val).strip())))
                        else:
                            target_ctx.add(
                                (subj_uri, pred_uri, _coerce_r2rml_literal(raw_val, dt_uri))
                            )

                for unbound_col in unbound_cols:
                    raw_val = row_dict.get(unbound_col)
                    if raw_val is None or str(raw_val).strip() == "":
                        continue
                    generic_pred = TELCO_NS[_column_to_camel_case(unbound_col)]
                    target_ctx.add(
                        (subj_uri, generic_pred, _coerce_r2rml_literal(raw_val, None))
                    )

            triples_projected = len(target_ctx) - triples_before

            # Dynamic SCD2 & table audit
            from_tables = _FROM_TABLE_RE.findall(compiled_sql)
            if table_name_lit is not None and not from_tables:
                from_tables = [str(table_name_lit).strip()]
            for tbl in from_tables:
                if tbl not in mapped_tables:
                    mapped_tables.append(tbl)
                if tbl in sqlite_tables_discovered:
                    tbl_total = int(
                        conn.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()[0]
                    )
                    total_rows_in_mapped += tbl_total
                    active_rows_retained += len(rows)
                    if tbl_total > len(rows) and tbl not in scd2_filtered_tables:
                        scd2_filtered_tables.append(tbl)

            logger.info(
                "Layer 4 R2RML pushdown %s -> %d rows, %d triples (%.3f ms)",
                tm,
                len(rows),
                triples_projected,
                latency_ms,
            )
            query_records.append(
                CompiledR2rmlQueryRecord(
                    triples_map_iri=str(tm),
                    target_class_iri=str(subj_class_uri),
                    target_graph_iri=str(target_graph_ref),
                    compiled_sql=compiled_sql,
                    rows_returned=len(rows),
                    triples_projected=triples_projected,
                    execution_latency_ms=latency_ms,
                    unbound_columns_projected=unbound_cols,
                )
            )
    finally:
        conn.close()

    excluded_unmapped = sorted(set(sqlite_tables_discovered) - set(mapped_tables))
    scd2_audit = Scd2AuditSummary(
        sqlite_tables_discovered=sqlite_tables_discovered,
        mapped_tables=mapped_tables,
        excluded_unmapped_tables=excluded_unmapped,
        scd2_filtered_tables=scd2_filtered_tables,
        total_rows_in_mapped_tables=total_rows_in_mapped,
        active_rows_retained=active_rows_retained,
        historical_rows_suppressed=max(0, total_rows_in_mapped - active_rows_retained),
    )

    in_memory_virtual_count = len(runtime_ds.graph(GRAPH_VIRTUAL_IB))
    compile_result = VirtualGraphCompileResult(
        compiled_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        virtual_graph_iri=str(GRAPH_VIRTUAL_IB),
        disk_virtual_ib_triples_before=0,
        in_memory_virtual_ib_triples=in_memory_virtual_count,
        query_records=query_records,
        scd2_audit=scd2_audit,
    )
    return runtime_ds, compile_result

