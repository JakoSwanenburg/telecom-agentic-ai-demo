"""
Federated Multi-Named-Graph Executor & 5-Challenge Resolution Proof
(`src/layer4/federated_executor.py`).

Executes read-only SPARQL queries across the 6 federated Named Graphs:
  1. `<urn:telco:graph:virtual:ib>` (ephemeral in-memory R2RML-to-SQLite projection)
  2. `<urn:telco:graph:ref:catalog>` (pySHACL-validated Excel ServiceSpecifications)
  3. `<urn:telco:graph:bites:doc-hw-v4>` (GLOBAL_SCOPE hardware optical profiles)
  4. `<urn:telco:graph:bites:doc-msa-v1>` (DOCUMENT_SCOPE MSA SLA & policy clauses)
  5. `<urn:telco:graph:meta:doc-lifecycle>` (ACTIVE document lifecycle governance)
  6. `<urn:telco:graph:bridge:er>` (HITL Gate 2 approved fuzzy ER bridge)
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import warnings

from rdflib import Dataset, URIRef

from src.config_loader import get_workspace_root
from src.layer4.r2rml_sqlite_compiler import (
    GRAPH_VIRTUAL_IB,
    compile_r2rml_to_virtual_graph,
)
from src.models import (
    AppConfig,
    BitAndErGate2CandidateProposal,
    ChallengeResolutionProofEntry,
    FederatedCircuitContext,
    FiveChallengeProofTable,
    Layer4FederationExecutionResult,
)

_SPARQL_MUTATION_RE = re.compile(
    r"\b(INSERT|DELETE|DROP|CLEAR|LOAD|CREATE|MOVE|COPY|ADD)\b",
    re.IGNORECASE,
)

_FEDERATED_CIRCUIT_SPARQL = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX tmf: <http://tmforum.org/sid/>
PREFIX telco: <http://telco.enterprise.org/ontology/>

SELECT
  ?circuitId ?customerId ?customerName ?customerIri
  ?erScore ?erStatus
  ?skuCode ?operStatus ?bandwidthGbps
  ?rfsId ?peRouterIri ?oltPortIri ?cpeAssetIri ?cpeModelSku
  ?maxPacketLossPct ?autoRemediationAllowed ?eligibleUpgradeSpec ?catalogLifecycleStatus
  ?rxOpticalPowerMinDbm ?rxLosCutThresholdDbm ?nominalTxDbm ?normalRxWindow
  ?slaPolicyLabel ?slaCreditPct ?breachDurationMins
WHERE {
  GRAPH <urn:telco:graph:virtual:ib> {
    ?cfs a tmf:CustomerFacingService ;
         tmf:serviceId ?circuitId ;
         tmf:hasCustomer ?customerIri ;
         tmf:isDescribedBy ?specIri ;
         tmf:operationalStatus ?operStatus ;
         telco:bandwidthGbps ?bandwidthGbps .
    ?customerIri a tmf:Customer ;
                 tmf:customerId ?customerId ;
                 tmf:partyLegalName ?customerName .
    ?rfs a tmf:ResourceFacingService ;
         tmf:supportsService ?cfs ;
         tmf:rfsId ?rfsId ;
         telco:terminatesOnRouter ?peRouterIri ;
         telco:usesOltPort ?oltPortIri ;
         telco:demarcatesAtCpe ?cpeAssetIri ;
         telco:cpeModelSku ?cpeModelSku .
  }
  BIND(STRAFTER(STR(?specIri), "urn:telco:spec:service:") AS ?skuCode)
  BIND(IRI(CONCAT("urn:telco:spec:resource:", STR(?cpeModelSku))) AS ?hwSpecIri)

  GRAPH <urn:telco:graph:ref:catalog> {
    ?catalogSpec a tmf:ServiceSpecification ;
                 tmf:skuCode ?skuCode ;
                 telco:maxPacketLossPct ?maxPacketLossPct ;
                 telco:autoRemediationAllowed ?autoRemediationAllowed .
    OPTIONAL { ?catalogSpec telco:eligibleUpgradeSpec ?eligibleUpgradeSpec . }
    OPTIONAL { ?catalogSpec telco:lifecycleStatus ?catalogLifecycleStatus . }
  }

  GRAPH <urn:telco:graph:bites:doc-hw-v4> {
    ?hwSpecIri telco:hasOpticalCalibrationProfile ?optProfile .
    ?optProfile telco:rxOpticalPowerMinDbm ?rxOpticalPowerMinDbm ;
                telco:rxLosCutThresholdDbm ?rxLosCutThresholdDbm .
    OPTIONAL { ?optProfile telco:nominalTxDbm ?nominalTxDbm . }
    OPTIONAL { ?optProfile telco:normalRxWindow ?normalRxWindow . }
  }

  GRAPH <urn:telco:graph:bites:doc-msa-v1> {
    ?specIri telco:hasSlaClause ?slaClause .
    OPTIONAL { ?slaClause rdfs:label ?slaPolicyLabel . }
    OPTIONAL { ?slaClause telco:slaCreditPct ?slaCreditPct . }
    OPTIONAL { ?slaClause telco:breachDurationMins ?breachDurationMins . }
  }

  OPTIONAL {
    GRAPH <urn:telco:graph:bridge:er> {
      ?erMention telco:resolvedToCanonicalCustomer ?customerIri ;
                 telco:erConfidenceScore ?erScore ;
                 telco:erCurationStatus ?erStatus .
    }
  }
  FILTER(STR(?circuitId) = "__CIRCUIT_ID__")
}
"""

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


def _strip_sparql_strings_and_comments(query_text: str) -> str:
    """Remove SPARQL comments and quoted literals before mutation keyword checks."""
    no_comments = re.sub(r"#[^\n]*", " ", query_text)
    no_strings = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"]*"|\'[^\']*\'', " ", no_comments)
    return no_strings


def execute_readonly_sparql(
    dataset: Dataset,
    query_text: str,
) -> List[Dict[str, Any]]:
    """
    Execute a read-only SPARQL query (`SELECT` / `ASK` / `CONSTRUCT` / `DESCRIBE`)
    against an `rdflib.Dataset`, deterministically rejecting any SPARQL UPDATE
    mutation keywords.
    """
    sanitized = _strip_sparql_strings_and_comments(query_text)
    match = _SPARQL_MUTATION_RE.search(sanitized)
    if match:
        raise ValueError(
            f"Read-only SPARQL guard rejected mutation keyword '{match.group(1).upper()}'."
        )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        result = dataset.query(query_text)

    if getattr(result, "type", None) == "ASK":
        return [{"ask_result": bool(result.askAnswer)}]

    rows: List[Dict[str, Any]] = []
    var_names = [str(v) for v in (result.vars or [])]
    for row in result:
        row_dict: Dict[str, Any] = {}
        for idx, var_name in enumerate(var_names):
            val = row[idx]
            row_dict[var_name] = val.toPython() if hasattr(val, "toPython") else (
                str(val) if val is not None else None
            )
        rows.append(row_dict)
    return rows


def _extract_iri_tail(iri_value: Any) -> str:
    """Extract final colon-delimited segment from a canonical URN IRI."""
    text = str(iri_value or "")
    return text.rsplit(":", 1)[-1] if ":" in text else text


def build_five_challenge_proof_table(
    ctx: FederatedCircuitContext,
    compile_result: Any,
    disk_virtual_after: int,
) -> FiveChallengeProofTable:
    """Construct the structured 5-Challenge Resolution Proof Table."""
    scd2 = compile_result.scd2_audit
    entries = [
        ChallengeResolutionProofEntry(
            challenge_number=1,
            challenge_name="Zero-Copy Semantic Virtualization",
            problem_statement=(
                "Live CMDB operational topology must remain authoritative in SQLite without "
                "duplicating installed-base rows onto RDF disk storage."
            ),
            layer4_resolution_mechanism=(
                "R2RML pushdown compiler executes SQL queries on demand and projects "
                "<urn:telco:graph:virtual:ib> strictly in memory."
            ),
            live_verification_evidence=(
                f"In-memory virtual:ib triples={compile_result.in_memory_virtual_ib_triples} | "
                f"Disk virtual:ib triples before={compile_result.disk_virtual_ib_triples_before}, "
                f"after={disk_virtual_after}."
            ),
        ),
        ChallengeResolutionProofEntry(
            challenge_number=2,
            challenge_name="Unstable Universal Keys across Silos",
            problem_statement=(
                "CMDB customer names, MSA legal names, product SKU IRIs, and hardware model "
                "SKUs use heterogeneous identifiers across SQL, Excel, and PDFs."
            ),
            layer4_resolution_mechanism=(
                "Approved ER bridge (<urn:telco:graph:bridge:er>) plus canonical SKU & hardware "
                "key alignment inside Layer 4 federated SPARQL."
            ),
            live_verification_evidence=(
                f"Bridged {ctx.customer_id} ('{ctx.customer_name}') <-> "
                f"'{ctx.bridged_legal_name or 'N/A'}' (ER={ctx.bridged_er_confidence}); "
                f"joined SKU '{ctx.product_sku}' & CPE '{ctx.cpe_model_sku}'."
            ),
        ),
        ChallengeResolutionProofEntry(
            challenge_number=3,
            challenge_name="SCD Type 2 Historical Contamination & Exclusion",
            problem_statement=(
                "CMDB contains superseded SCD2 circuit rows and unmapped billing noise tables "
                "that would corrupt active SLA/remediation decisions."
            ),
            layer4_resolution_mechanism=(
                "R2RML SQL pushdown enforces active-row filtering (VALID_TO_TS IS NULL) and "
                "omits unmapped noise tables."
            ),
            live_verification_evidence=(
                f"Suppressed {scd2.historical_rows_suppressed} historical row(s) across "
                f"{scd2.scd2_filtered_tables}; excluded {scd2.excluded_unmapped_tables}; "
                f"retained {ctx.circuit_id} -> {ctx.product_sku} ({ctx.operational_status}, "
                f"{ctx.bandwidth_gbps} Gbps)."
            ),
        ),
        ChallengeResolutionProofEntry(
            challenge_number=4,
            challenge_name="Unstructured Dark Data Scope & Lifecycle",
            problem_statement=(
                "Hardware optical cutoffs and customer MSA SLA clauses live in unstructured PDFs "
                "requiring scope separation and active lifecycle governance."
            ),
            layer4_resolution_mechanism=(
                "Scoped BITES graphs separate GLOBAL_SCOPE hardware profiles (<urn:telco:graph:bites:doc-hw-v4>) "
                "from DOCUMENT_SCOPE MSAs (<urn:telco:graph:bites:doc-msa-v1>) and lifecycle metadata."
            ),
            live_verification_evidence=(
                f"Optical Rx window min={ctx.rx_optical_power_min_dbm} dBm, "
                f"LOS cutoff={ctx.rx_los_cut_threshold_dbm} dBm; "
                f"Lifecycles={ctx.doc_lifecycle_statuses}."
            ),
        ),
        ChallengeResolutionProofEntry(
            challenge_number=5,
            challenge_name="Deterministic Read-Only SPARQL & Zero-Hallucination Guardrails",
            problem_statement=(
                "Layer 4 must prevent mutation side effects and never fabricate missing "
                "contract/optical values."
            ),
            layer4_resolution_mechanism=(
                "SPARQL guard rejects INSERT/DELETE/DROP/CLEAR/LOAD; Pydantic v2 validates "
                "required vs. Optional graph-backed fields."
            ),
            live_verification_evidence=(
                f"Read-only 6-graph SPARQL join succeeded for {ctx.circuit_id}: "
                f"maxPacketLossPct={ctx.max_packet_loss_pct}%, "
                f"autoRemediationAllowed={ctx.auto_remediation_allowed}."
            ),
        ),
    ]
    return FiveChallengeProofTable(circuit_id=ctx.circuit_id, entries=entries)


def write_layer4_proof_reports(
    result: Layer4FederationExecutionResult,
    html_path: Path,
    md_path: Path,
) -> None:
    """Write HTML and Markdown audit reports for Layer 4 Federation & 5-Challenge Proof."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    ctx = result.circuit_context
    comp = result.compile_result

    md_lines: List[str] = [
        f"# Step 5 — Layer 4 R2RML Pushdown & Federated Proof Report (`{ctx.circuit_id}`)",
        "",
        f"- **Executed At (UTC):** `{result.executed_at_utc}`",
        f"- **In-Memory `<urn:telco:graph:virtual:ib>` Triples:** `{comp.in_memory_virtual_ib_triples}`",
        f"- **On-Disk `<urn:telco:graph:virtual:ib>` Triples (Before / After):** `{comp.disk_virtual_ib_triples_before}` / `{result.disk_virtual_ib_triples_after}`",
        f"- **SCD2 Historical Rows Suppressed:** `{comp.scd2_audit.historical_rows_suppressed}` (`{', '.join(comp.scd2_audit.scd2_filtered_tables)}`)",
        f"- **Excluded Unmapped Tables:** `{', '.join(comp.scd2_audit.excluded_unmapped_tables)}`",
        "",
        "## 1. Compiled R2RML-to-SQLite Pushdown Queries",
        "",
        "| TriplesMap | Rows | Triples | Latency (ms) | Unbound Cols Projected |",
        "|---|---:|---:|---:|---|",
    ]
    for rec in comp.query_records:
        md_lines.append(
            f"| `{rec.triples_map_iri}` | {rec.rows_returned} | {rec.triples_projected} | "
            f"{rec.execution_latency_ms:.3f} | `{', '.join(rec.unbound_columns_projected) or '-'}` |"
        )

    md_lines.extend([
        "",
        f"## 2. Unified Federated Circuit Context (`{ctx.circuit_id}`)",
        "",
        f"- **Customer:** `{ctx.customer_id}` (`{ctx.customer_name}`) <-> Bridged Legal Entity: `{ctx.bridged_legal_name or '-'}` (ER Confidence: `{ctx.bridged_er_confidence}`)",
        f"- **Active CFS:** `{ctx.product_sku}` | Status: `{ctx.operational_status}` | Bandwidth: `{ctx.bandwidth_gbps} Gbps`",
        f"- **Topology:** RFS `{ctx.rfs_id}` | Router `{ctx.pe_router_hostname}` | Port `{ctx.olt_port_id}` | CPE `{ctx.cpe_asset_id}` (`{ctx.cpe_model_sku}`)",
        f"- **Excel Catalog SLA:** `maxPacketLossPct = {ctx.max_packet_loss_pct}%` | `autoRemediationAllowed = {ctx.auto_remediation_allowed}` | Upgrade: `{ctx.eligible_upgrade_sku or '-'}`",
        f"- **Hardware Optical Thresholds:** `rxOpticalPowerMinDbm = {ctx.rx_optical_power_min_dbm} dBm` | `rxLosCutThresholdDbm = {ctx.rx_los_cut_threshold_dbm} dBm`",
        f"- **MSA Policy:** `{ctx.sla_policy_label or '-'}` | Document Lifecycles: `{', '.join(ctx.doc_lifecycle_statuses)}`",
        "",
        "## 3. 5-Challenge Resolution Proof Table",
        "",
        "| # | Challenge | Layer 4 Resolution Mechanism | Live Verification Evidence | Status |",
        "|---:|---|---|---|---|",
    ])
    for e in result.proof_table.entries:
        md_lines.append(
            f"| {e.challenge_number} | **{e.challenge_name}** | {e.layer4_resolution_mechanism} | "
            f"{e.live_verification_evidence} | `{e.status}` |"
        )

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    query_rows_html = "\n".join(
        f"<tr><td><code>{html.escape(r.triples_map_iri)}</code></td>"
        f"<td>{r.rows_returned}</td><td>{r.triples_projected}</td>"
        f"<td>{r.execution_latency_ms:.3f}</td>"
        f"<td><code>{html.escape(', '.join(r.unbound_columns_projected) or '-')}</code></td>"
        f"<td><pre>{html.escape(r.compiled_sql)}</pre></td></tr>"
        for r in comp.query_records
    )
    proof_rows_html = "\n".join(
        f"<tr><td>{e.challenge_number}</td><td><strong>{html.escape(e.challenge_name)}</strong></td>"
        f"<td>{html.escape(e.problem_statement)}</td>"
        f"<td>{html.escape(e.layer4_resolution_mechanism)}</td>"
        f"<td>{html.escape(e.live_verification_evidence)}</td>"
        f"<td><strong>{html.escape(e.status)}</strong></td></tr>"
        for e in result.proof_table.entries
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Step 5 Layer 4 Federation Proof ({html.escape(ctx.circuit_id)})</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    .card {{ background: #f8fafc; border: 1px solid #cbd5e1; padding: 14px; border-radius: 6px; margin-bottom: 18px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e2e8f0; }}
    pre {{ margin: 0; white-space: pre-wrap; font-size: 11px; }}
  </style>
</head>
<body>
  <h1>Step 5: Layer 4 R2RML Pushdown &amp; Federated Resolution Proof ({html.escape(ctx.circuit_id)})</h1>
  <div class="card">
    <p><strong>In-Memory virtual:ib Triples:</strong> {comp.in_memory_virtual_ib_triples} |
       <strong>On-Disk virtual:ib Triples (Before / After):</strong> {comp.disk_virtual_ib_triples_before} / {result.disk_virtual_ib_triples_after}</p>
    <p><strong>Customer:</strong> {html.escape(ctx.customer_id)} ({html.escape(ctx.customer_name)}) &harr;
       {html.escape(ctx.bridged_legal_name or '-')} (ER: {ctx.bridged_er_confidence})</p>
    <p><strong>Active Circuit:</strong> {html.escape(ctx.product_sku)} | {html.escape(ctx.operational_status)} | {ctx.bandwidth_gbps} Gbps |
       <strong>CPE:</strong> {html.escape(ctx.cpe_asset_id)} ({html.escape(ctx.cpe_model_sku)})</p>
    <p><strong>Catalog SLA &amp; Optical Cutoffs:</strong> maxPacketLossPct={ctx.max_packet_loss_pct}% |
       autoRemediationAllowed={ctx.auto_remediation_allowed} |
       rxOpticalPowerMinDbm={ctx.rx_optical_power_min_dbm} dBm | rxLosCutThresholdDbm={ctx.rx_los_cut_threshold_dbm} dBm</p>
  </div>

  <h2>1. Compiled R2RML-to-SQLite Pushdown Queries</h2>
  <table>
    <thead><tr><th>TriplesMap</th><th>Rows</th><th>Triples</th><th>Latency (ms)</th><th>Unbound Cols</th><th>Compiled SQL</th></tr></thead>
    <tbody>{query_rows_html}</tbody>
  </table>

  <h2>2. 5-Challenge Resolution Proof Table</h2>
  <table>
    <thead><tr><th>#</th><th>Challenge</th><th>Problem</th><th>Layer 4 Resolution</th><th>Live Verification Evidence</th><th>Status</th></tr></thead>
    <tbody>{proof_rows_html}</tbody>
  </table>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")


def query_federated_circuit_context(
    circuit_id: str,
    config: AppConfig,
    logger: logging.Logger,
    root_dir: Optional[Path] = None,
) -> Layer4FederationExecutionResult:
    """
    Compile `<urn:telco:graph:virtual:ib>` ephemerally in memory via R2RML pushdown,
    execute the 6-graph federated SPARQL query for `circuit_id`, construct the
    5-Challenge Resolution Proof Table, and write audit reports.
    """
    resolved_root = root_dir if root_dir is not None else get_workspace_root()
    runtime_ds, compile_result = compile_r2rml_to_virtual_graph(
        config=config, logger=logger, root_dir=resolved_root
    )

    sparql_query = _FEDERATED_CIRCUIT_SPARQL.replace("__CIRCUIT_ID__", circuit_id.strip())
    rows = execute_readonly_sparql(runtime_ds, sparql_query)
    if not rows:
        raise RuntimeError(
            f"Layer 4 federated SPARQL query returned 0 rows for circuit_id='{circuit_id}'."
        )
    row = rows[0]

    lifecycle_rows = execute_readonly_sparql(runtime_ds, _LIFECYCLE_SPARQL)
    lifecycle_statuses = sorted(
        {str(r["lifecycleStatus"]) for r in lifecycle_rows if r.get("lifecycleStatus")}
    )

    bridged_legal_name: Optional[str] = None
    gate2_path = resolved_root / Path(
        config.track_b_ingestion_and_er.gate2_candidate_proposal_path
    )
    if gate2_path.exists():
        gate2_prop = BitAndErGate2CandidateProposal.model_validate_json(
            gate2_path.read_text(encoding="utf-8")
        )
        cust_iri = str(row["customerIri"])
        for match in gate2_prop.fuzzy_er_matches:
            if match.canonical_subject_iri == cust_iri and match.curation_status != "REJECTED":
                bridged_legal_name = match.mention_text
                break

    circuit_ctx = FederatedCircuitContext(
        circuit_id=str(row["circuitId"]),
        customer_id=str(row["customerId"]),
        customer_name=str(row["customerName"]),
        customer_subject_iri=str(row["customerIri"]),
        bridged_legal_name=bridged_legal_name,
        bridged_er_confidence=(
            float(row["erScore"]) if row.get("erScore") is not None else None
        ),
        bridged_er_status=(
            str(row["erStatus"]) if row.get("erStatus") is not None else None
        ),
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
        eligible_upgrade_sku=(
            _extract_iri_tail(row["eligibleUpgradeSpec"])
            if row.get("eligibleUpgradeSpec") is not None
            else None
        ),
        catalog_lifecycle_status=(
            str(row["catalogLifecycleStatus"])
            if row.get("catalogLifecycleStatus") is not None
            else None
        ),
        rx_optical_power_min_dbm=float(row["rxOpticalPowerMinDbm"]),
        rx_los_cut_threshold_dbm=float(row["rxLosCutThresholdDbm"]),
        nominal_tx_dbm=(
            float(row["nominalTxDbm"]) if row.get("nominalTxDbm") is not None else None
        ),
        normal_rx_window=(
            str(row["normalRxWindow"]) if row.get("normalRxWindow") is not None else None
        ),
        sla_policy_label=(
            str(row["slaPolicyLabel"]) if row.get("slaPolicyLabel") is not None else None
        ),
        sla_credit_pct=(
            float(row["slaCreditPct"]) if row.get("slaCreditPct") is not None else None
        ),
        breach_duration_mins=(
            int(row["breachDurationMins"])
            if row.get("breachDurationMins") is not None
            else None
        ),
        doc_lifecycle_statuses=lifecycle_statuses,
    )

    # Confirm disk virtual:ib remains 0 after execution
    trig_path = resolved_root / Path(config.layer4_compiler_federation.dataset_trig_path)
    ds_after = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds_after.parse(str(trig_path), format="trig")
    disk_virtual_after = len(ds_after.graph(GRAPH_VIRTUAL_IB))

    proof_table = build_five_challenge_proof_table(
        ctx=circuit_ctx,
        compile_result=compile_result,
        disk_virtual_after=disk_virtual_after,
    )

    html_path = resolved_root / Path(
        config.layer4_compiler_federation.layer4_federation_proof_report_path
    )
    md_path = html_path.with_suffix(".md")
    executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = Layer4FederationExecutionResult(
        executed_at_utc=executed_at,
        circuit_id=circuit_ctx.circuit_id,
        compile_result=compile_result,
        circuit_context=circuit_ctx,
        proof_table=proof_table,
        disk_virtual_ib_triples_after=disk_virtual_after,
        federated_graphs_queried=[
            "urn:telco:graph:virtual:ib",
            "urn:telco:graph:ref:catalog",
            "urn:telco:graph:bites:doc-hw-v4",
            "urn:telco:graph:bites:doc-msa-v1",
            "urn:telco:graph:meta:doc-lifecycle",
            "urn:telco:graph:bridge:er",
        ],
        report_html_path=html_path,
        report_markdown_path=md_path,
    )

    write_layer4_proof_reports(result, html_path=html_path, md_path=md_path)
    logger.info(
        "Layer 4 federation complete for %s: disk virtual:ib=%d, in-memory=%d",
        circuit_ctx.circuit_id,
        disk_virtual_after,
        compile_result.in_memory_virtual_ib_triples,
    )
    return result

