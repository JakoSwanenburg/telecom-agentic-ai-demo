"""
Dynamic Stored SPARQL Template Compiler (IMP-008-R1).

Generates `data/semantic_store/stored_sparql_templates.yaml` dynamically from:
1. `uc001_use_case_charter.md`
2. `data/semantic_store/tbox_sid_etom.ttl`
3. `data/semantic_store/knowledge_graph.trig` (promoted Named Graphs)
4. Configured R2RML mapping + Layer 4 in-memory `<urn:telco:graph:virtual:ib>` projection

Validates every compiled template with `validate_sparql_ast()` and verifies that
`tpl_uc001_circuit_assurance_context` executes cleanly against Layer 4 before writing.
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from google.genai import types
from rdflib import Dataset, Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef

from src.config import get_workspace_root
from src.layer3.ast_gatekeeper import validate_sparql_ast
from src.layer4.federated_executor import execute_readonly_sparql
from src.layer4.r2rml_sqlite_compiler import (
    GRAPH_VIRTUAL_IB,
    compile_r2rml_to_virtual_graph,
    validate_layer4_prerequisites,
)
from src.llm_client import (
    create_genai_client,
    resolve_model_for_component,
    strip_unsupported_vertex_schema_keys,
)
from src.models import (
    AppConfig,
    StoredSparqlTemplateCatalog,
    TemplateCompileResult,
)

RR = Namespace("http://www.w3.org/ns/r2rml#")

_REQUIRED_PROMOTED_GRAPHS = (
    "urn:telco:graph:ref:catalog",
    "urn:telco:graph:bites:doc-hw-v4",
    "urn:telco:graph:bites:doc-msa-v1",
    "urn:telco:graph:meta:doc-lifecycle",
    "urn:telco:graph:bridge:er",
)

_REQUIRED_UC001_RESULT_KEYS = (
    "circuitId",
    "customerId",
    "skuCode",
    "maxPacketLossPct",
    "autoRemediationAllowed",
    "rxOpticalPowerMinDbm",
    "rxLosCutThresholdDbm",
)


def _summarize_tbox(tbox_path: Path) -> str:
    """Summarize classes and properties from tbox_sid_etom.ttl."""
    g = Graph()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        g.parse(str(tbox_path), format="turtle")

    classes = sorted(
        {str(s) for s in g.subjects(RDF.type, OWL.Class)}
        | {str(s) for s in g.subjects(RDF.type, RDFS.Class)}
    )
    props = sorted(
        {str(s) for s in g.subjects(RDF.type, OWL.DatatypeProperty)}
        | {str(s) for s in g.subjects(RDF.type, OWL.ObjectProperty)}
        | {str(s) for s in g.subjects(RDF.type, RDF.Property)}
    )
    return "\n".join(
        ["Classes:"] + [f"- {c}" for c in classes] + ["", "Properties:"] + [f"- {p}" for p in props]
    )


def _summarize_named_graphs(dataset: Dataset) -> str:
    """Introspect active Named Graphs in the combined Dataset (including virtual:ib)."""
    lines: List[str] = []
    for graph_ctx in sorted(dataset.graphs(), key=lambda g: str(g.identifier)):
        gid = str(graph_ctx.identifier)
        if gid == "urn:x-rdflib:default" or len(graph_ctx) == 0:
            continue
        classes = sorted({str(o) for _, _, o in graph_ctx.triples((None, RDF.type, None))})
        preds = sorted({str(p) for _, p, _ in graph_ctx})
        sample_iris: List[str] = []
        seen_prefixes: Set[str] = set()
        for s, _, o in graph_ctx:
            for term in (s, o):
                if isinstance(term, URIRef):
                    text = str(term)
                    prefix = text.rsplit(":", 1)[0] if ":" in text else text
                    if prefix not in seen_prefixes and len(sample_iris) < 6:
                        seen_prefixes.add(prefix)
                        sample_iris.append(text)
        lines.append(f"### Graph `<{gid}>` ({len(graph_ctx)} triples)")
        lines.append(f"- Classes: {classes}")
        lines.append(f"- Predicates: {preds}")
        lines.append(f"- Sample IRIs: {sample_iris}")
        lines.append("")
    return "\n".join(lines)


def _summarize_r2rml(r2rml_path: Path) -> str:
    """Extract TriplesMap subject templates and predicates from the configured R2RML mapping."""
    g = Graph()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        g.parse(str(r2rml_path), format="turtle")

    lines: List[str] = []
    for tm in sorted(set(g.subjects(RR.subjectMap, None)), key=str):
        sm = g.value(tm, RR.subjectMap)
        tmpl = g.value(sm, RR.template) if sm else None
        cls = g.value(sm, RR["class"]) if sm else None
        preds = sorted(
            {
                str(g.value(pom, RR.predicate))
                for pom in g.objects(tm, RR.predicateObjectMap)
                if g.value(pom, RR.predicate) is not None
            }
        )
        lines.append(
            f"- TriplesMap `<{tm}>`: class=`{cls}`, subject_template=`{tmpl}`, predicates={preds}"
        )
    return "\n".join(lines)


def _call_template_compiler_llm(
    config: AppConfig,
    logger: logging.Logger,
    model_name: str,
    prompt_text: str,
) -> StoredSparqlTemplateCatalog:
    """Invoke Gemini via shared src/llm_client.py to synthesize StoredSparqlTemplateCatalog."""
    client = create_genai_client(config, logger)
    clean_schema = strip_unsupported_vertex_schema_keys(
        StoredSparqlTemplateCatalog.model_json_schema()
    )
    gen_config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=clean_schema,
    )
    response = client.models.generate_content(
        model=model_name,
        contents=prompt_text,
        config=gen_config,
    )
    if not response or not getattr(response, "text", None):
        raise RuntimeError(
            f"Gemini model '{model_name}' returned empty response for StoredSparqlTemplateCatalog."
        )
    return StoredSparqlTemplateCatalog.model_validate_json(response.text)


def compile_stored_sparql_templates(
    config: AppConfig,
    logger: logging.Logger,
    root_dir: Optional[Path] = None,
    test_circuit_id: str = "CIR-994821",
) -> TemplateCompileResult:
    """
    Dynamically introspect Track B + Layer 4 schemas, synthesize verified SPARQL templates
    via Gemini, validate every template with AST Gatekeeper & Layer 4 execution, and write
    `data/semantic_store/stored_sparql_templates.yaml`.
    """
    workspace_root = root_dir if root_dir is not None else get_workspace_root()
    tbox_path, trig_path, r2rml_path, _ = validate_layer4_prerequisites(
        config, root_dir=workspace_root
    )

    charter_path = (
        workspace_root / Path(config.paths.raw_sources_dir) / "uc001_use_case_charter.md"
    )
    if not charter_path.exists():
        raise RuntimeError(f"Use Case Charter not found: {charter_path}")

    dataset, _ = compile_r2rml_to_virtual_graph(
        config=config, logger=logger, root_dir=workspace_root
    )

    # Verify required promoted Track B graphs are populated
    empty_graphs = [
        g for g in _REQUIRED_PROMOTED_GRAPHS if len(dataset.graph(g)) == 0
    ]
    if empty_graphs or len(dataset.graph(GRAPH_VIRTUAL_IB)) == 0:
        raise RuntimeError(
            "Cannot compile Layer 3 SPARQL templates: missing/empty promoted graphs "
            f"{empty_graphs}. Run DT-01a..c --mode approve first."
        )

    prompt_path = workspace_root / Path(
        config.layer3_nl2semantics.template_compiler_prompt_path
    )
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Layer 3 template compiler prompt not found: {prompt_path}"
        )

    prompt_text = (
        prompt_path.read_text(encoding="utf-8")
        .replace("{use_case_charter}", charter_path.read_text(encoding="utf-8"))
        .replace("{tbox_summary}", _summarize_tbox(tbox_path))
        .replace("{named_graphs_schema_summary}", _summarize_named_graphs(dataset))
        .replace("{r2rml_templates_summary}", _summarize_r2rml(r2rml_path))
    )

    model_name = resolve_model_for_component(config, "layer3_nl2semantics")
    logger.info("Compiling Layer 3 Stored SPARQL Templates via model=%s", model_name)
    catalog = _call_template_compiler_llm(
        config=config, logger=logger, model_name=model_name, prompt_text=prompt_text
    )

    # Validate every compiled template with static AST Gatekeeper
    sample_params = {"circuit_id": test_circuit_id, "sku_code": "ETH-10G-GOLD"}
    templates_by_id: Dict[str, Any] = {}
    for tmpl in catalog.templates:
        rendered = tmpl.sparql
        for key, val in sample_params.items():
            rendered = rendered.replace(f"{{{key}}}", val)
        ast_audit = validate_sparql_ast(rendered, tbox_path=tbox_path, trig_path=trig_path)
        if not ast_audit.passed:
            raise ValueError(
                f"Compiled template '{tmpl.template_id}' failed AST Gatekeeper: "
                f"{ast_audit.model_dump()}"
            )
        templates_by_id[tmpl.template_id] = tmpl

    if "tpl_uc001_circuit_assurance_context" not in templates_by_id:
        raise RuntimeError(
            "Compiled template catalog missing mandatory 'tpl_uc001_circuit_assurance_context'."
        )

    # Verify tpl_uc001_circuit_assurance_context executes against Layer 4
    uc001_query = templates_by_id["tpl_uc001_circuit_assurance_context"].sparql.replace(
        "{circuit_id}", test_circuit_id
    )
    rows = execute_readonly_sparql(dataset, uc001_query)
    if not rows:
        raise RuntimeError(
            f"Compiled 'tpl_uc001_circuit_assurance_context' returned 0 rows for {test_circuit_id}."
        )
    missing_keys = [
        k for k in _REQUIRED_UC001_RESULT_KEYS if rows[0].get(k) is None
    ]
    if missing_keys:
        raise RuntimeError(
            f"Compiled 'tpl_uc001_circuit_assurance_context' missing required output fields: {missing_keys}"
        )

    output_path = workspace_root / Path(
        config.layer3_nl2semantics.stored_sparql_templates_path
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"templates": [t.model_dump() for t in catalog.templates]}
    output_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    logger.info(
        "Wrote %d verified SPARQL templates to %s",
        len(catalog.templates),
        output_path,
    )

    return TemplateCompileResult(
        compiled_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        model_used=model_name,
        output_path=output_path,
        template_ids=[t.template_id for t in catalog.templates],
        ast_passed_count=len(catalog.templates),
        layer4_verified_circuit_id=test_circuit_id,
        layer4_verified_rows=len(rows),
    )
