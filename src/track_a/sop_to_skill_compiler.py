"""
Scenario DT-02a & Gate 3: 100% Document-Independent Track A SOP-to-Skill Compiler.

Dynamically introspects:
- Master NOC Assurance Runbook markdown (`config.stage0.sop_runbook_md_filename`)
- Use Case Charter (`config.track_b_ingestion_and_er.use_case_charter_path`)
- Locked SID/eTOM TBox (`config.layer4_compiler_federation.tbox_path`)
- Southbound MCP Primitives Catalog (`config.layer2_worker_and_sop.mcp_catalog_path`)

Enforces:
- Fail-fast on missing `DT-01a` TBox or `PARTIAL_GAP` MCP catalog (writing full
  functional tool specs to `reports/missing_primitive_spec.json`).
- True Two-Phase HITL Gate 3 (`--mode candidate` -> `--mode approve`).
"""

from __future__ import annotations

import html
import json
import logging
import re
import shutil
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from google.genai import types
from rdflib import Graph, OWL, RDF, RDFS

from src.catalog_manager import load_catalog
from src.config import get_workspace_root
from src.llm_client import (
    create_genai_client,
    resolve_model_for_component,
    strip_unsupported_vertex_schema_keys,
)
from src.models import (
    AdverseTestSuiteResult,
    AppConfig,
    CompiledSopSkillProposal,
    Dt02ExecutionResult,
    Gate3CandidateBundle,
    McpPrimitivesCatalog,
    MissingPrimitivesGapReport,
    MissingPrimitiveToolSpec,
)
from src.track_a.adverse_test_harness import run_dt02b_adverse_guardrail_tests

_REQUIRED_PROTOCOLS: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    (
        "SPARQL_1_1_FEDERATED_READ",
        {
            "required_mcp_primitive_uri": "mcp://semantic-read/query_knowledge_fabric",
            "tool_name": "query_knowledge_fabric",
            "functional_description": "Executes read-only federated SPARQL queries across Layer 3/4.",
            "sop_step_requiring_it": "STEP_1_SEMANTIC_CONTEXT",
            "required_obo_jwt_scope": "semantic:read",
            "idempotency_and_rollback_requirements": "Strictly read-only; no mutation or rollback required.",
        },
    ),
    (
        "gNMI_OPTICAL_TELEMETRY",
        {
            "required_mcp_primitive_uri": "cqrs://singleton-check/probe_resource_state",
            "tool_name": "probe_optical_ddm_telemetry",
            "functional_description": "Executes non-cached singleton gNMI optical DDM telemetry probe and acquires port mutex lock.",
            "sop_step_requiring_it": "STEP_2_SINGLETON_OPTICAL_PROBE",
            "required_obo_jwt_scope": "telemetry:read",
            "idempotency_and_rollback_requirements": "Read-only probe; mutex lock expires automatically via Redis TTL.",
        },
    ),
    (
        "TMF640_SERVICE_ACTIVATION",
        {
            "required_mcp_primitive_uri": "cqrs://transactional-write/execute_governed_mutation",
            "tool_name": "recalibrate_optical_ddm_bias",
            "functional_description": "Executes OBO-authenticated, mutex-locked optical transceiver DDM AGC/bias recalibration.",
            "sop_step_requiring_it": "STEP_3_BRANCH_A_REMEDIATION",
            "required_obo_jwt_scope": "activation:write",
            "idempotency_and_rollback_requirements": "Requires singleton_lock_token + pre/post gNMI verification; restores prior bias setpoint on failure.",
        },
    ),
    (
        "TMF621_TROUBLE_TICKET",
        {
            "required_mcp_primitive_uri": "cqrs://transactional-write/execute_governed_mutation",
            "tool_name": "create_or_update_trouble_ticket",
            "functional_description": "Creates or updates TMF621 trouble tickets for field fiber dispatch or resolved auto-remediation audit.",
            "sop_step_requiring_it": "STEP_4_BRANCH_B_DISPATCH_AND_AUDIT",
            "required_obo_jwt_scope": "ticket:write",
            "idempotency_and_rollback_requirements": "Idempotent via correlation_id; appends immutable audit entries in data/cqrs_state/tmf621_ticket_journal.json.",
        },
    ),
)


def _split_sop_markdown_sections(sop_text: str) -> str:
    """Dynamically split a markdown SOP runbook by `## ` headings for LLM scoring."""
    parts = re.split(r"(?m)^(?=##\s+)", sop_text.strip())
    sections = [p.strip() for p in parts if p.strip().startswith("## ")]
    if not sections:
        return sop_text.strip()
    formatted: List[str] = []
    for idx, sec in enumerate(sections, start=1):
        formatted.append(f"### Discovered Section {idx}\n{sec}")
    return "\n\n".join(formatted)


def _summarize_tbox(tbox_path: Path) -> str:
    """Extract classes and properties from tbox_sid_etom.ttl."""
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


def _detect_catalog_gaps(catalog: McpPrimitivesCatalog) -> List[MissingPrimitiveToolSpec]:
    """Check whether all required southbound protocols are enabled in the MCP catalog."""
    enabled_protocols: Set[str] = set()
    for prim in catalog.primitives:
        if prim.enabled:
            for proto in prim.supported_protocols:
                enabled_protocols.add(proto)

    if not catalog.enable_tmf621_dispatch_primitive:
        enabled_protocols.discard("TMF621_TROUBLE_TICKET")

    missing: List[MissingPrimitiveToolSpec] = []
    for proto, meta in _REQUIRED_PROTOCOLS:
        if proto not in enabled_protocols:
            missing.append(
                MissingPrimitiveToolSpec(
                    required_mcp_primitive_uri=meta["required_mcp_primitive_uri"],
                    tool_name=meta["tool_name"],
                    required_protocol=proto,
                    functional_description=meta["functional_description"],
                    sop_step_requiring_it=meta["sop_step_requiring_it"],
                    input_parameter_schema={
                        "type": "object",
                        "properties": {
                            "circuit_id": {"type": "string"},
                            "resource_iri": {"type": "string"},
                            "singleton_lock_token": {"type": "string"},
                            "obo_jwt": {"type": "string"},
                        },
                        "required": ["circuit_id", "obo_jwt"],
                    },
                    expected_output_schema={
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                            "audit_id": {"type": "string"},
                        },
                        "required": ["status"],
                    },
                    required_obo_jwt_scope=meta["required_obo_jwt_scope"],
                    idempotency_and_rollback_requirements=meta[
                        "idempotency_and_rollback_requirements"
                    ],
                )
            )
    return missing


def _write_gap_reports(
    gap_report: MissingPrimitivesGapReport,
    missing_spec_path: Path,
    html_path: Path,
    md_path: Path,
) -> None:
    """Write PARTIAL_GAP functional tool specification JSON and HITL gap diagnostic reports."""
    missing_spec_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    missing_spec_path.write_text(
        json.dumps(gap_report.model_dump(), indent=2) + "\n", encoding="utf-8"
    )

    md_lines = [
        "# HITL Gate 3 — SOP-to-Skill Compilation BLOCKED (`PARTIAL_GAP`)",
        "",
        f"- **Generated At (UTC):** `{gap_report.generated_at_utc}`",
        f"- **Catalog State:** `{gap_report.catalog_state}`",
        f"- **Blocking Reason:** {gap_report.blocking_reason}",
        f"- **Functional Tool Spec:** `{missing_spec_path.as_posix()}`",
        "",
        "| Missing Protocol | Tool Name | Required MCP URI | Required OBO Scope | SOP Step |",
        "|---|---|---|---|---|",
    ]
    for m in gap_report.missing_tools:
        md_lines.append(
            f"| `{m.required_protocol}` | `{m.tool_name}` | `{m.required_mcp_primitive_uri}` | "
            f"`{m.required_obo_jwt_scope}` | `{m.sop_step_requiring_it}` |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    rows_html = "\n".join(
        f"<tr><td><code>{html.escape(m.required_protocol)}</code></td>"
        f"<td><code>{html.escape(m.tool_name)}</code></td>"
        f"<td><code>{html.escape(m.required_mcp_primitive_uri)}</code></td>"
        f"<td><code>{html.escape(m.required_obo_jwt_scope)}</code></td>"
        f"<td>{html.escape(m.functional_description)}</td></tr>"
        for m in gap_report.missing_tools
    )
    html_path.write_text(
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" /><title>HITL Gate 3 Blocked: PARTIAL_GAP</title></head>
<body style="font-family: Arial, sans-serif; margin: 24px;">
  <h1 style="color: #b91c1c;">HITL Gate 3 Compilation Blocked (MCP Catalog PARTIAL_GAP)</h1>
  <p>{html.escape(gap_report.blocking_reason)}</p>
  <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
    <thead><tr><th>Missing Protocol</th><th>Tool Name</th><th>Required MCP URI</th><th>OBO Scope</th><th>Description</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</body></html>
""",
        encoding="utf-8",
    )


def _write_gate3_review_reports(
    bundle: Gate3CandidateBundle,
    html_path: Path,
    md_path: Path,
) -> None:
    """Write HITL Gate 3 SOP-to-Skill & DT-02b Adverse Verification HTML/MD reports."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    prop = bundle.proposal
    adv = bundle.adverse_suite

    md_lines = [
        f"# HITL Gate 3 — SOP-to-Skill & Adverse Guardrail Review (`{bundle.status}`)",
        "",
        f"- **Generated At (UTC):** `{bundle.generated_at_utc}`",
        f"- **Model Used:** `{bundle.model_used}`",
        f"- **Status:** `{bundle.status}`",
        f"- **Target Skill:** `{prop.skill_spec.skill_id}` (`{prop.skill_spec.sop_id}`, eTOM `{', '.join(prop.skill_spec.etom_process_ids)}`)",
        f"- **DT-02b Adverse Guardrail Tests:** `{adv.passed_tests}/{adv.total_tests}` passed",
        "",
        "## 1. Procedure Scope & Distractor Pruning",
        "",
        "| Section | Procedure ID | Score | Disposition | Rationale |",
        "|---|---|---:|---|---|",
    ]
    for a in prop.procedure_assessments:
        md_lines.append(
            f"| {a.section_heading} | `{a.procedure_id}` | {a.relevance_score:.2f} | `{a.disposition}` | {a.rationale} |"
        )

    md_lines.extend(
        [
            "",
            "## 2. Machine-Enforceable Guardrails (`guardrails_sop_402.json`)",
            "",
            "| Guardrail ID | Phase | Parameter | Operator | Threshold | Target Tool |",
            "|---|---|---|---|---|---|",
        ]
    )
    for r in prop.guardrails_spec.rules:
        md_lines.append(
            f"| `{r.guardrail_id}` | `{r.phase}` | `{r.parameter}` | `{r.operator}` | `{r.threshold_value}` | `{r.target_tool}` |"
        )

    md_lines.extend(
        [
            "",
            "## 3. DT-02b Adverse Guardrail Rejection Proof",
            "",
            "| Test ID | Scenario | Expected Guardrail | Actual Blocked | Actual Guardrail | Passed |",
            "|---|---|---|---|---|---|",
        ]
    )
    for c in adv.cases:
        md_lines.append(
            f"| `{c.test_id}` | {c.test_name} | `{c.expected_blocking_guardrail_id}` | "
            f"`{c.actual_blocked}` | `{c.actual_blocking_guardrail_id}` | `{c.passed}` |"
        )

    md_lines.extend(["", "## 4. HITL Gate 3 NOC Architect Verification Questions", ""])
    for idx, q in enumerate(prop.architect_verification_questions, start=1):
        md_lines.append(f"{idx}. {q}")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    proc_rows_html = "\n".join(
        f"<tr><td>{html.escape(a.section_heading)}</td><td><code>{html.escape(a.procedure_id)}</code></td>"
        f"<td>{a.relevance_score:.2f}</td><td><strong>{html.escape(a.disposition)}</strong></td>"
        f"<td>{html.escape(a.rationale)}</td></tr>"
        for a in prop.procedure_assessments
    )
    guardrail_rows_html = "\n".join(
        f"<tr><td><code>{html.escape(r.guardrail_id)}</code></td>"
        f"<td><code>{html.escape(r.phase)}</code></td>"
        f"<td><code>{html.escape(r.parameter)}</code></td>"
        f"<td><code>{html.escape(r.operator)}</code></td>"
        f"<td><code>{html.escape(str(r.threshold_value))}</code></td>"
        f"<td><code>{html.escape(r.target_tool)}</code></td></tr>"
        for r in prop.guardrails_spec.rules
    )
    adv_rows_html = "\n".join(
        f"<tr><td><code>{html.escape(c.test_id)}</code></td><td>{html.escape(c.test_name)}</td>"
        f"<td><code>{html.escape(c.expected_blocking_guardrail_id)}</code></td>"
        f"<td><code>{c.actual_blocked}</code></td>"
        f"<td><code>{html.escape(str(c.actual_blocking_guardrail_id))}</code></td>"
        f"<td><strong>{c.passed}</strong></td></tr>"
        for c in adv.cases
    )
    questions_html = "\n".join(
        f"<li>{html.escape(q)}</li>" for q in prop.architect_verification_questions
    )
    html_path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>HITL Gate 3: SOP-to-Skill &amp; Adverse Guardrail Review</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; }}
    .card {{ background: #f8fafc; border: 1px solid #cbd5e1; padding: 14px; border-radius: 6px; margin-bottom: 18px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 13px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e2e8f0; }}
    ol {{ background: #fffbeb; border: 1px solid #fde68a; padding: 16px 32px; border-radius: 6px; }}
    li {{ margin-bottom: 8px; }}
  </style>
</head>
<body>
  <h1>HITL Gate 3: SOP-to-Skill &amp; Adverse Guardrail Review ({html.escape(bundle.status)})</h1>
  <div class="card">
    <p><strong>Generated At (UTC):</strong> {html.escape(bundle.generated_at_utc)} |
       <strong>Model:</strong> {html.escape(bundle.model_used)} |
       <strong>Status:</strong> {html.escape(bundle.status)}</p>
    <p><strong>Target Skill:</strong> {html.escape(prop.skill_spec.skill_id)} ({html.escape(prop.skill_spec.sop_id)}, eTOM {html.escape(', '.join(prop.skill_spec.etom_process_ids))}) |
       <strong>DT-02b Adverse Guardrail Tests:</strong> {adv.passed_tests}/{adv.total_tests} passed</p>
  </div>
  <h2>1. Procedure Scope &amp; Distractor Pruning</h2>
  <table><thead><tr><th>Section</th><th>Procedure ID</th><th>Score</th><th>Disposition</th><th>Rationale</th></tr></thead><tbody>{proc_rows_html}</tbody></table>
  <h2>2. Machine-Enforceable Guardrails (<code>guardrails_sop_402.json</code>)</h2>
  <table><thead><tr><th>Guardrail ID</th><th>Phase</th><th>Parameter</th><th>Operator</th><th>Threshold</th><th>Target Tool</th></tr></thead><tbody>{guardrail_rows_html}</tbody></table>
  <h2>3. DT-02b Adverse Guardrail Rejection Proof</h2>
  <table><thead><tr><th>Test ID</th><th>Scenario</th><th>Expected Guardrail</th><th>Actual Blocked</th><th>Actual Guardrail</th><th>Passed</th></tr></thead><tbody>{adv_rows_html}</tbody></table>
  <h2>4. HITL Gate 3 NOC Architect Verification Questions</h2>
  <ol>{questions_html}</ol>
</body>
</html>
""",
        encoding="utf-8",
    )


def _call_sop_compiler_llm(
    config: AppConfig,
    logger: logging.Logger,
    model_name: str,
    prompt_text: str,
) -> CompiledSopSkillProposal:
    """Invoke Gemini via shared src/llm_client.py with strict Pydantic v2 JSON schema."""
    client = create_genai_client(config, logger)
    clean_schema = strip_unsupported_vertex_schema_keys(
        CompiledSopSkillProposal.model_json_schema()
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
            f"Gemini model '{model_name}' returned empty response for CompiledSopSkillProposal."
        )
    return CompiledSopSkillProposal.model_validate_json(response.text)


def run_dt02_sop_skill_compiler(
    config: AppConfig,
    logger: logging.Logger,
    mode: str = "candidate",
    update_golden_ref: bool = False,
    root_dir: Optional[Path] = None,
) -> Dt02ExecutionResult:
    """
    Execute Track A Scenario DT-02a & DT-02b with Two-Phase HITL Gate 3:
    - `candidate`: Introspect SOP/Charter/TBox/Catalog, compile skill & guardrails, run DT-02b,
      stage in `skills/gate3_candidate_sop_402.json`, pause at `CANDIDATE_COMPILED`.
    - `approve`: Verify 3/3 DT-02b pass, materialize `skills/skill_sop_402.yaml` &
      `skills/guardrails_sop_402.json`, transition to `VERIFIED_LOCKED`.
    """
    if mode not in {"candidate", "approve"}:
        raise ValueError(f"Invalid DT-02 mode '{mode}'. Expected 'candidate' or 'approve'.")

    workspace_root = root_dir if root_dir is not None else get_workspace_root()
    tbox_path = workspace_root / Path(config.layer4_compiler_federation.tbox_path)
    if not tbox_path.exists():
        raise RuntimeError(
            f"Track A DT-02a prerequisite failed: TBox not found at {tbox_path}. "
            "Run DT-01a --mode approve first."
        )

    candidate_path = workspace_root / Path(
        config.layer2_worker_and_sop.gate3_candidate_proposal_path
    )
    active_skill_path = workspace_root / Path(
        config.layer2_worker_and_sop.active_skill_path
    )
    active_guardrails_path = workspace_root / Path(
        config.layer2_worker_and_sop.active_guardrails_path
    )
    missing_spec_path = workspace_root / Path(
        config.layer2_worker_and_sop.missing_primitive_spec_path
    )
    html_path = workspace_root / Path(
        config.layer2_worker_and_sop.hitl_sop_review_report_path
    )
    md_path = html_path.with_suffix(".md")

    catalog = load_catalog(config, workspace_root)
    missing_tools = _detect_catalog_gaps(catalog)
    if missing_tools:
        gap_report = MissingPrimitivesGapReport(
            generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            catalog_state="PARTIAL_GAP",
            blocking_reason=(
                "Southbound MCP Catalog is in PARTIAL_GAP state; missing required protocol(s): "
                f"{[m.required_protocol for m in missing_tools]}."
            ),
            missing_tools=missing_tools,
        )
        _write_gap_reports(
            gap_report=gap_report,
            missing_spec_path=missing_spec_path,
            html_path=html_path,
            md_path=md_path,
        )
        raise RuntimeError(
            f"DT-02a blocked by MCP Catalog PARTIAL_GAP ({[m.required_protocol for m in missing_tools]}). "
            f"Functional tool spec written to {missing_spec_path}."
        )

    if mode == "candidate":
        sop_path = (
            workspace_root
            / Path(config.paths.raw_sources_dir)
            / Path(config.paths.sop_subdir)
            / Path(config.stage0.sop_runbook_md_filename)
        )
        charter_path = workspace_root / Path(
            config.track_b_ingestion_and_er.use_case_charter_path
        )
        prompt_path = workspace_root / Path(
            config.layer2_worker_and_sop.sop_compiler_prompt_template_path
        )
        for req_p in (sop_path, charter_path, prompt_path):
            if not req_p.exists():
                raise RuntimeError(f"Required DT-02a input file not found: {req_p}")

        prompt_text = (
            prompt_path.read_text(encoding="utf-8")
            .replace("{use_case_charter}", charter_path.read_text(encoding="utf-8"))
            .replace("{tbox_summary}", _summarize_tbox(tbox_path))
            .replace("{mcp_catalog_json}", json.dumps(catalog.model_dump(), indent=2))
            .replace(
                "{sop_sections_summary}",
                _split_sop_markdown_sections(sop_path.read_text(encoding="utf-8")),
            )
        )

        model_name = resolve_model_for_component(config, "track_a_sop_compiler")
        logger.info("Executing DT-02a SOP-to-Skill compilation via model=%s", model_name)
        proposal = _call_sop_compiler_llm(
            config=config, logger=logger, model_name=model_name, prompt_text=prompt_text
        )
        adverse_suite: AdverseTestSuiteResult = run_dt02b_adverse_guardrail_tests(
            proposal.guardrails_spec
        )

        bundle = Gate3CandidateBundle(
            generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            model_used=model_name,
            status="CANDIDATE_COMPILED",
            proposal=proposal,
            adverse_suite=adverse_suite,
        )
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text(
            json.dumps(bundle.model_dump(), indent=2) + "\n", encoding="utf-8"
        )
        _write_gate3_review_reports(bundle=bundle, html_path=html_path, md_path=md_path)

        return Dt02ExecutionResult(
            mode="candidate",
            sys01_element6_state="CANDIDATE_COMPILED (Awaiting HITL Gate 3)",
            model_used=model_name,
            catalog_state="COMPLETE",
            candidate_proposal_path=candidate_path,
            active_skill_path=active_skill_path,
            active_guardrails_path=active_guardrails_path,
            hitl_report_html_path=html_path,
            hitl_report_markdown_path=md_path,
            adverse_tests_passed=adverse_suite.passed_tests,
            adverse_tests_total=adverse_suite.total_tests,
            architect_verification_questions=proposal.architect_verification_questions,
        )

    # Phase 2: --mode approve
    if not candidate_path.exists():
        raise RuntimeError(
            f"Cannot approve HITL Gate 3: candidate proposal not found at {candidate_path}. "
            "Run DT-02 --mode candidate first."
        )

    bundle = Gate3CandidateBundle.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    adverse_suite = run_dt02b_adverse_guardrail_tests(bundle.proposal.guardrails_spec)
    if not adverse_suite.all_passed:
        raise RuntimeError(
            f"HITL Gate 3 approval blocked: DT-02b adverse guardrail tests passed "
            f"{adverse_suite.passed_tests}/{adverse_suite.total_tests} (expected 100%)."
        )

    active_skill_path.parent.mkdir(parents=True, exist_ok=True)
    active_skill_path.write_text(
        yaml.safe_dump(
            bundle.proposal.skill_spec.model_dump(),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    active_guardrails_path.write_text(
        json.dumps(bundle.proposal.guardrails_spec.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )

    locked_bundle = bundle.model_copy(
        update={"status": "VERIFIED_LOCKED", "adverse_suite": adverse_suite}
    )
    candidate_path.write_text(
        json.dumps(locked_bundle.model_dump(), indent=2) + "\n", encoding="utf-8"
    )
    _write_gate3_review_reports(
        bundle=locked_bundle, html_path=html_path, md_path=md_path
    )

    if update_golden_ref:
        golden_dir = workspace_root / "data" / "golden_reference"
        golden_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(active_skill_path, golden_dir / active_skill_path.name)
        shutil.copy2(active_guardrails_path, golden_dir / active_guardrails_path.name)

    return Dt02ExecutionResult(
        mode="approve",
        sys01_element6_state="VERIFIED_LOCKED",
        model_used=bundle.model_used,
        catalog_state="COMPLETE",
        candidate_proposal_path=candidate_path,
        active_skill_path=active_skill_path,
        active_guardrails_path=active_guardrails_path,
        hitl_report_html_path=html_path,
        hitl_report_markdown_path=md_path,
        adverse_tests_passed=adverse_suite.passed_tests,
        adverse_tests_total=adverse_suite.total_tests,
        architect_verification_questions=bundle.proposal.architect_verification_questions,
    )
