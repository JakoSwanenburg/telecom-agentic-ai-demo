"""
Layer 3: NL2Semantics Dual Shadow Comparison Engine (Step 6 / Scenario RT-05).

Supports three configurable execution modes:
- `voicebox_hybrid`: TBox pruning + Stored Verified SPARQL Template matching + AST Gatekeeper.
- `zero_shot_llm`: Unconstrained TBox-only zero-shot SPARQL generation + AST Gatekeeper.
- `dual_comparison` (default): Executes both paths side-by-side and generates an empirical
  comparison report (`reports/rt05_layer3_nl2semantics_comparison.html` & `.md`).
"""

from __future__ import annotations

import html
import logging
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

import yaml
from google.genai import types
from pydantic import BaseModel
from rdflib import Dataset, Graph, RDF, RDFS, OWL

from src.layer3.ast_gatekeeper import validate_sparql_ast
from src.layer4.federated_executor import (
    build_five_challenge_proof_table,
    execute_readonly_sparql,
)
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
    FederatedCircuitContext,
    FiveChallengeProofTable,
    Layer3DualComparisonResult,
    VoiceboxExecutionResult,
    VoiceboxHybridSelectionProposal,
    ZeroShotExecutionResult,
    ZeroShotSparqlProposal,
)

TModel = TypeVar("TModel", bound=BaseModel)

_ALLOWED_MODES = frozenset({"dual_comparison", "voicebox_hybrid", "zero_shot_llm"})

_EXPECTED_CONTEXT_SPARQL_VARS = (
    "circuitId",
    "customerId",
    "customerName",
    "skuCode",
    "operStatus",
    "bandwidthGbps",
    "rfsId",
    "cpeModelSku",
    "maxPacketLossPct",
    "autoRemediationAllowed",
    "rxOpticalPowerMinDbm",
    "rxLosCutThresholdDbm",
    "slaPolicyLabel",
)

_LIFECYCLE_SPARQL = """
PREFIX telco: <http://telco.enterprise.org/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?docLabel ?lifecycleStatus
WHERE {
  GRAPH <urn:telco:graph:meta:doc-lifecycle> {
    ?doc telco:lifecycleStatus ?lifecycleStatus .
    OPTIONAL { ?doc rdfs:label ?docLabel . }
  }
}
"""

_ER_NAME_SPARQL = """
PREFIX telco: <http://telco.enterprise.org/ontology/>
SELECT ?mentionLabel
WHERE {
  GRAPH <urn:telco:graph:bridge:er> {
    ?erMention telco:resolvedToCanonicalCustomer <__CUSTOMER_IRI__> .
    OPTIONAL { ?erMention telco:rawMentionString ?mentionLabel . }
  }
}
"""


def _count_disk_virtual_ib_triples(trig_path: Path) -> int:
    """Count triples persisted on disk in <urn:telco:graph:virtual:ib>."""
    ds_check = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds_check.parse(str(trig_path), format="trig")
    return len(ds_check.graph(GRAPH_VIRTUAL_IB))


def _extract_iri_tail(iri_value: Any) -> str:
    """Extract final colon-delimited segment from a canonical URN IRI."""
    text = str(iri_value or "")
    return text.rsplit(":", 1)[-1] if ":" in text else text


def _load_templates_catalog(templates_path: Path) -> List[Dict[str, Any]]:
    """Load and validate stored SPARQL templates from YAML (fail fast if missing)."""
    if not templates_path.exists():
        raise RuntimeError(
            f"Stored SPARQL templates catalog not found: {templates_path}. "
            "Run 'scripts/run_dt01c_pdf_bites_gate2.py --mode approve' or pass "
            "'--compile-templates' to 'scripts/run_rt05_layer3_modes.py' first."
        )
    raw = yaml.safe_load(templates_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("templates"), list):
        raise ValueError(
            f"Invalid stored SPARQL templates YAML structure in {templates_path}"
        )
    return list(raw["templates"])


def _summarize_tbox(tbox_path: Path) -> str:
    """Extract a concise class and property summary from the SID/eTOM TBox."""
    g = Graph()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        g.parse(str(tbox_path), format="turtle")

    classes = sorted(
        {
            str(s)
            for s in g.subjects(RDF.type, OWL.Class)
        }
        | {str(s) for s in g.subjects(RDF.type, RDFS.Class)}
    )
    props = sorted(
        {str(s) for s in g.subjects(RDF.type, OWL.DatatypeProperty)}
        | {str(s) for s in g.subjects(RDF.type, OWL.ObjectProperty)}
        | {str(s) for s in g.subjects(RDF.type, RDF.Property)}
    )
    lines = ["Classes:"] + [f"- {c}" for c in classes] + ["", "Properties:"] + [
        f"- {p}" for p in props
    ]
    return "\n".join(lines)


def _call_gemini_structured(
    config: AppConfig,
    logger: logging.Logger,
    model_name: str,
    prompt_text: str,
    schema_cls: Type[TModel],
) -> TModel:
    """Invoke Gemini via shared src/llm_client.py with strict Pydantic v2 JSON schema."""
    client = create_genai_client(config, logger)
    raw_schema = schema_cls.model_json_schema()
    clean_schema = strip_unsupported_vertex_schema_keys(raw_schema)
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
            f"Gemini model '{model_name}' returned an empty response for {schema_cls.__name__}."
        )
    return schema_cls.model_validate_json(response.text)


def _build_federated_context_from_row(
    dataset: Dataset,
    row: Dict[str, Any],
) -> FederatedCircuitContext:
    """Build a strict FederatedCircuitContext from a Layer 4 SPARQL result row."""
    lifecycle_rows = execute_readonly_sparql(dataset, _LIFECYCLE_SPARQL)
    doc_lifecycles = [
        f"{r.get('docLabel') or 'doc'}:{r.get('lifecycleStatus')}"
        for r in lifecycle_rows
    ]

    customer_iri = str(row["customerIri"])
    er_rows = execute_readonly_sparql(
        dataset, _ER_NAME_SPARQL.replace("__CUSTOMER_IRI__", customer_iri)
    )
    bridged_legal_name = (
        str(er_rows[0]["mentionLabel"])
        if er_rows and er_rows[0].get("mentionLabel")
        else None
    )

    upgrade_spec = row.get("eligibleUpgradeSpec")
    upgrade_sku = _extract_iri_tail(upgrade_spec) if upgrade_spec else None

    return FederatedCircuitContext(
        circuit_id=str(row["circuitId"]),
        customer_id=str(row["customerId"]),
        customer_name=str(row["customerName"]),
        customer_subject_iri=customer_iri,
        bridged_legal_name=bridged_legal_name,
        bridged_er_confidence=(
            float(row["erScore"]) if row.get("erScore") is not None else None
        ),
        bridged_er_status=str(row["erStatus"]) if row.get("erStatus") else None,
        product_sku=str(row["skuCode"]),
        operational_status=str(row["operStatus"]),
        bandwidth_gbps=float(row["bandwidthGbps"]),
        rfs_id=str(row["rfsId"]),
        pe_router_hostname=_extract_iri_tail(row["peRouterIri"]),
        olt_port_id=_extract_iri_tail(row["oltPortIri"]),
        cpe_asset_id=_extract_iri_tail(row["cpeAssetIri"]),
        cpe_model_sku=str(row["cpeModelSku"]),
        max_packet_loss_pct=float(row["maxPacketLossPct"]),
        auto_remediation_allowed=bool(row["autoRemediationAllowed"]),
        eligible_upgrade_sku=upgrade_sku,
        catalog_lifecycle_status=(
            str(row["catalogLifecycleStatus"])
            if row.get("catalogLifecycleStatus")
            else None
        ),
        rx_optical_power_min_dbm=float(row["rxOpticalPowerMinDbm"]),
        rx_los_cut_threshold_dbm=float(row["rxLosCutThresholdDbm"]),
        nominal_tx_dbm=(
            float(row["nominalTxDbm"]) if row.get("nominalTxDbm") is not None else None
        ),
        normal_rx_window=(
            str(row["normalRxWindow"]) if row.get("normalRxWindow") else None
        ),
        sla_policy_label=(
            str(row["slaPolicyLabel"]) if row.get("slaPolicyLabel") else None
        ),
        sla_credit_pct=(
            float(row["slaCreditPct"]) if row.get("slaCreditPct") is not None else None
        ),
        breach_duration_mins=(
            int(row["breachDurationMins"])
            if row.get("breachDurationMins") is not None
            else None
        ),
        doc_lifecycle_statuses=doc_lifecycles,
    )


def _run_voicebox_hybrid_path(
    natural_language_intent: str,
    target_circuit_id: Optional[str],
    config: AppConfig,
    logger: logging.Logger,
    model_name: str,
    workspace_root: Path,
    tbox_path: Path,
    trig_path: Path,
    dataset: Dataset,
    compile_result: Any,
    disk_virtual_after: int,
) -> VoiceboxExecutionResult:
    """Execute the deterministic Voicebox Hybrid path (TBox pruning + template + AST gate)."""
    templates_path = workspace_root / config.layer3_nl2semantics.stored_sparql_templates_path
    templates = _load_templates_catalog(templates_path)
    templates_by_id = {t["template_id"]: t for t in templates}

    catalog_summary = "\n".join(
        f"- `{t['template_id']}`: {t['description']} | required_parameters={t.get('required_parameters', [])}"
        for t in templates
    )

    prompt_path = workspace_root / config.layer3_nl2semantics.voicebox_prompt_template_path
    if not prompt_path.exists():
        raise FileNotFoundError(f"Voicebox prompt template not found: {prompt_path}")

    prompt_text = (
        prompt_path.read_text(encoding="utf-8")
        .replace("{natural_language_intent}", natural_language_intent)
        .replace("{target_circuit_id}", target_circuit_id or "None")
        .replace("{tbox_summary}", _summarize_tbox(tbox_path))
        .replace("{templates_catalog_summary}", catalog_summary)
    )

    t0 = time.perf_counter()
    proposal = _call_gemini_structured(
        config=config,
        logger=logger,
        model_name=model_name,
        prompt_text=prompt_text,
        schema_cls=VoiceboxHybridSelectionProposal,
    )

    if proposal.template_id not in templates_by_id:
        raise ValueError(
            f"Voicebox Hybrid selected unknown template_id '{proposal.template_id}'."
        )

    tmpl = templates_by_id[proposal.template_id]
    params = dict(proposal.parameters)
    if "circuit_id" in tmpl.get("required_parameters", []) and "circuit_id" not in params:
        if target_circuit_id:
            params["circuit_id"] = target_circuit_id

    for req_param in tmpl.get("required_parameters", []):
        if req_param not in params or not str(params[req_param]).strip():
            raise ValueError(
                f"Voicebox Hybrid missing required parameter '{req_param}' for template '{proposal.template_id}'."
            )

    compiled_sparql = str(tmpl["sparql"])
    for key, val in params.items():
        compiled_sparql = compiled_sparql.replace(f"{{{key}}}", str(val))

    ast_audit = validate_sparql_ast(
        compiled_sparql, tbox_path=tbox_path, trig_path=trig_path
    )
    if not ast_audit.passed:
        raise ValueError(
            f"Voicebox Hybrid compiled SPARQL failed AST Gatekeeper: {ast_audit.model_dump()}"
        )

    rows = execute_readonly_sparql(dataset, compiled_sparql)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    federated_context: Optional[FederatedCircuitContext] = None
    proof_table: Optional[FiveChallengeProofTable] = None
    if proposal.template_id == "tpl_uc001_circuit_assurance_context" and rows:
        federated_context = _build_federated_context_from_row(dataset, rows[0])
        proof_table = build_five_challenge_proof_table(
            ctx=federated_context,
            compile_result=compile_result,
            disk_virtual_after=disk_virtual_after,
        )

    return VoiceboxExecutionResult(
        template_id=proposal.template_id,
        compiled_sparql=compiled_sparql,
        pruned_tbox_classes=proposal.pruned_tbox_classes,
        pruned_tbox_properties=proposal.pruned_tbox_properties,
        parameters=params,
        ast_audit=ast_audit,
        latency_ms=latency_ms,
        row_count=len(rows),
        federated_context=federated_context,
        five_challenge_proof=proof_table,
        sql_pushdown_queries=compile_result.query_records,
    )


def _run_zero_shot_llm_path(
    natural_language_intent: str,
    target_circuit_id: Optional[str],
    config: AppConfig,
    logger: logging.Logger,
    model_name: str,
    workspace_root: Path,
    tbox_path: Path,
    trig_path: Path,
    dataset: Dataset,
) -> ZeroShotExecutionResult:
    """
    Execute the Zero-Shot LLM shadow path.
    Never aborts on AST failure, SPARQL syntax error, or empty/partial results;
    captures all diagnostics cleanly for empirical comparison.
    """
    prompt_path = workspace_root / config.layer3_nl2semantics.zero_shot_prompt_template_path
    if not prompt_path.exists():
        raise FileNotFoundError(f"Zero-Shot prompt template not found: {prompt_path}")

    tbox_turtle = tbox_path.read_text(encoding="utf-8")
    prompt_text = (
        prompt_path.read_text(encoding="utf-8")
        .replace("{natural_language_intent}", natural_language_intent)
        .replace("{target_circuit_id}", target_circuit_id or "None")
        .replace("{tbox_turtle}", tbox_turtle)
    )

    t0 = time.perf_counter()
    proposal = _call_gemini_structured(
        config=config,
        logger=logger,
        model_name=model_name,
        prompt_text=prompt_text,
        schema_cls=ZeroShotSparqlProposal,
    )

    ast_audit = validate_sparql_ast(
        proposal.sparql_query, tbox_path=tbox_path, trig_path=trig_path
    )

    rows: List[Dict[str, Any]] = []
    execution_error: Optional[str] = None
    if not ast_audit.passed:
        execution_error = (
            ast_audit.syntax_error
            or f"AST Gatekeeper blocked zero-shot query (unknown_uris={ast_audit.unknown_uris}, "
            f"sql_leakage={ast_audit.sql_leakage_matches}, mutations={ast_audit.blocked_mutations})"
        )
    else:
        try:
            rows = execute_readonly_sparql(dataset, proposal.sparql_query)
        except Exception as exc:
            execution_error = f"SPARQL execution error: {exc}"

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    if not rows:
        missing_fields = list(_EXPECTED_CONTEXT_SPARQL_VARS)
    else:
        present_keys = {k for k, v in rows[0].items() if v is not None}
        missing_fields = [
            f for f in _EXPECTED_CONTEXT_SPARQL_VARS if f not in present_keys
        ]

    return ZeroShotExecutionResult(
        generated_sparql=proposal.sparql_query,
        ast_audit=ast_audit,
        latency_ms=latency_ms,
        row_count=len(rows),
        execution_error=execution_error,
        missing_fields=missing_fields,
        raw_rows=rows,
    )


def _write_rt05_comparison_reports(
    result: Layer3DualComparisonResult,
    html_path: Path,
    md_path: Path,
) -> None:
    """Write Scenario RT-05 Dual Shadow Comparison HTML and Markdown reports."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    vb = result.voicebox_result
    zs = result.zero_shot_result

    md_lines = [
        "# Scenario RT-05 — Layer 3 `NL2Semantics` Dual Shadow Comparison Report",
        "",
        f"- **Execution Mode:** `{result.execution_mode}`",
        f"- **Model Used:** `{result.model_used}`",
        f"- **Target Circuit ID:** `{result.target_circuit_id or '-'}`",
        f"- **Natural Language Intent:** {result.natural_language_intent}",
        f"- **On-Disk `<urn:telco:graph:virtual:ib>` Triples After Query:** `{result.disk_virtual_ib_triples_after}`",
        "",
        "## Side-by-Side Comparison",
        "",
        "| Dimension | Voicebox Hybrid (`Option 3C`) | Zero-Shot LLM (Shadow) |",
        "|---|---|---|",
        f"| **AST Gatekeeper Passed** | `{vb.ast_audit.passed if vb else 'N/A'}` | `{zs.ast_audit.passed if zs else 'N/A'}` |",
        f"| **Latency (ms)** | `{vb.latency_ms if vb else 'N/A'}` | `{zs.latency_ms if zs else 'N/A'}` |",
        f"| **Rows Returned** | `{vb.row_count if vb else 'N/A'}` | `{zs.row_count if zs else 'N/A'}` |",
        f"| **Unknown Vocabulary URIs** | `{vb.ast_audit.unknown_uris if vb else 'N/A'}` | `{zs.ast_audit.unknown_uris if zs else 'N/A'}` |",
        f"| **Missing Context Fields** | `[]` | `{zs.missing_fields if zs else 'N/A'}` |",
        f"| **Execution Error** | `None` | `{zs.execution_error if zs else 'N/A'}` |",
        "",
    ]
    if vb:
        md_lines.extend(
            [
                f"## Voicebox Hybrid Selected Template: `{vb.template_id}`",
                "",
                f"- **Parameters:** `{vb.parameters}`",
                f"- **Pruned TBox Classes:** `{vb.pruned_tbox_classes}`",
                "",
                "```sparql",
                vb.compiled_sparql.strip(),
                "```",
                "",
            ]
        )
    if zs:
        md_lines.extend(
            [
                "## Zero-Shot LLM Generated SPARQL (Shadow)",
                "",
                "```sparql",
                zs.generated_sparql.strip(),
                "```",
                "",
            ]
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Scenario RT-05: Layer 3 NL2Semantics Dual Shadow Comparison</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    .card {{ background: #f8fafc; border: 1px solid #cbd5e1; padding: 14px; border-radius: 6px; margin-bottom: 18px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e2e8f0; }}
    pre {{ background: #f1f5f9; padding: 10px; border-radius: 4px; white-space: pre-wrap; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Scenario RT-05: Layer 3 NL2Semantics Dual Shadow Comparison</h1>
  <div class="card">
    <p><strong>Execution Mode:</strong> {html.escape(result.execution_mode)} |
       <strong>Model:</strong> {html.escape(result.model_used)} |
       <strong>Circuit:</strong> {html.escape(result.target_circuit_id or '-')}</p>
    <p><strong>Intent:</strong> {html.escape(result.natural_language_intent)}</p>
    <p><strong>On-Disk virtual:ib Triples After:</strong> {result.disk_virtual_ib_triples_after}</p>
  </div>
  <table>
    <thead>
      <tr><th>Dimension</th><th>Voicebox Hybrid (Option 3C)</th><th>Zero-Shot LLM (Shadow)</th></tr>
    </thead>
    <tbody>
      <tr><td>AST Gatekeeper Passed</td><td>{vb.ast_audit.passed if vb else 'N/A'}</td><td>{zs.ast_audit.passed if zs else 'N/A'}</td></tr>
      <tr><td>Latency (ms)</td><td>{vb.latency_ms if vb else 'N/A'}</td><td>{zs.latency_ms if zs else 'N/A'}</td></tr>
      <tr><td>Rows Returned</td><td>{vb.row_count if vb else 'N/A'}</td><td>{zs.row_count if zs else 'N/A'}</td></tr>
      <tr><td>Unknown Vocabulary URIs</td><td>{html.escape(str(vb.ast_audit.unknown_uris)) if vb else 'N/A'}</td><td>{html.escape(str(zs.ast_audit.unknown_uris)) if zs else 'N/A'}</td></tr>
      <tr><td>Missing Context Fields</td><td>[]</td><td>{html.escape(str(zs.missing_fields)) if zs else 'N/A'}</td></tr>
      <tr><td>Execution Error</td><td>None</td><td>{html.escape(str(zs.execution_error)) if zs else 'N/A'}</td></tr>
    </tbody>
  </table>
  <h2>Voicebox Hybrid Compiled SPARQL</h2>
  <pre>{html.escape(vb.compiled_sparql.strip()) if vb else 'Not executed'}</pre>
  <h2>Zero-Shot LLM Generated SPARQL</h2>
  <pre>{html.escape(zs.generated_sparql.strip()) if zs else 'Not executed'}</pre>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")


def run_layer3_nl2semantics(
    natural_language_intent: str,
    config: AppConfig,
    logger: logging.Logger,
    target_circuit_id: Optional[str] = None,
    execution_mode: Optional[str] = None,
    root_dir: Optional[Path] = None,
) -> Layer3DualComparisonResult:
    """
    Execute Layer 3 NL2Semantics translation + AST Gatekeeper + Layer 4 federated execution.
    """
    workspace_root = root_dir or Path.cwd()
    tbox_path, trig_path, _, _ = validate_layer4_prerequisites(
        config, root_dir=workspace_root
    )

    mode = execution_mode or config.layer3_nl2semantics.execution_mode
    if mode not in _ALLOWED_MODES:
        raise ValueError(
            f"Invalid Layer 3 execution_mode '{mode}'. Expected one of {sorted(_ALLOWED_MODES)}."
        )

    model_name = resolve_model_for_component(config, "layer3_nl2semantics")
    dataset, compile_result = compile_r2rml_to_virtual_graph(
        config=config, logger=logger, root_dir=workspace_root
    )
    disk_virtual_after = _count_disk_virtual_ib_triples(trig_path)

    voicebox_res: Optional[VoiceboxExecutionResult] = None
    zero_shot_res: Optional[ZeroShotExecutionResult] = None

    if mode in {"dual_comparison", "voicebox_hybrid"}:
        logger.info("Executing Layer 3 Voicebox Hybrid path (model=%s)", model_name)
        voicebox_res = _run_voicebox_hybrid_path(
            natural_language_intent=natural_language_intent,
            target_circuit_id=target_circuit_id,
            config=config,
            logger=logger,
            model_name=model_name,
            workspace_root=workspace_root,
            tbox_path=tbox_path,
            trig_path=trig_path,
            dataset=dataset,
            compile_result=compile_result,
            disk_virtual_after=disk_virtual_after,
        )

    if mode in {"dual_comparison", "zero_shot_llm"}:
        logger.info("Executing Layer 3 Zero-Shot LLM shadow path (model=%s)", model_name)
        zero_shot_res = _run_zero_shot_llm_path(
            natural_language_intent=natural_language_intent,
            target_circuit_id=target_circuit_id,
            config=config,
            logger=logger,
            model_name=model_name,
            workspace_root=workspace_root,
            tbox_path=tbox_path,
            trig_path=trig_path,
            dataset=dataset,
        )

    html_path = workspace_root / config.layer3_nl2semantics.rt05_comparison_report_path
    md_path = html_path.with_suffix(".md")

    result = Layer3DualComparisonResult(
        execution_mode=mode,  # type: ignore[arg-type]
        natural_language_intent=natural_language_intent,
        target_circuit_id=target_circuit_id,
        model_used=model_name,
        voicebox_result=voicebox_res,
        zero_shot_result=zero_shot_res,
        authoritative_context=(
            voicebox_res.federated_context if voicebox_res else None
        ),
        five_challenge_proof=(
            voicebox_res.five_challenge_proof if voicebox_res else None
        ),
        disk_virtual_ib_triples_after=disk_virtual_after,
        report_html_path=html_path,
        report_markdown_path=md_path,
    )
    _write_rt05_comparison_reports(result, html_path=html_path, md_path=md_path)
    return result
