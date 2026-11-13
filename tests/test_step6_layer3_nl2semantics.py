"""
Unit Tests for Step 6 (Layer 3): NL2Semantics Dual Shadow Comparison,
Static rdflib AST Gatekeeper, and Southbound `semantic-read-mcp` Server.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest

from src.config import load_config
from src.layer3.ast_gatekeeper import validate_sparql_ast
from src.layer3.nl2semantics_engine import run_layer3_nl2semantics
from src.layer3.template_compiler import compile_stored_sparql_templates
from src.mcp_servers.semantic_read_mcp import execute_query_knowledge_fabric
from src.models import (
    AppConfig,
    Layer3Nl2SemanticsSettings,
    StoredSparqlTemplate,
    StoredSparqlTemplateCatalog,
    VoiceboxHybridSelectionProposal,
    ZeroShotSparqlProposal,
)
from src.state_manager import reset_to_clean_slate

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def _sample_catalog() -> StoredSparqlTemplateCatalog:
    """Return a minimal verified StoredSparqlTemplateCatalog fixture."""
    return StoredSparqlTemplateCatalog(
        templates=[
            StoredSparqlTemplate(
                template_id="tpl_uc001_circuit_assurance_context",
                description="6-graph federated circuit assurance context lookup.",
                required_parameters=["circuit_id"],
                tbox_classes=["tmf:CustomerFacingService", "tmf:ResourceFacingService"],
                sparql="""
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX tmf: <http://tmforum.org/sid/>
PREFIX telco: <http://telco.enterprise.org/ontology/>
SELECT ?circuitId ?customerId ?customerName ?customerIri ?erScore ?erStatus
       ?skuCode ?operStatus ?bandwidthGbps ?rfsId ?peRouterIri ?oltPortIri
       ?cpeAssetIri ?cpeModelSku ?maxPacketLossPct ?autoRemediationAllowed
       ?eligibleUpgradeSpec ?catalogLifecycleStatus ?rxOpticalPowerMinDbm
       ?rxLosCutThresholdDbm ?slaPolicyLabel
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
  }
  GRAPH <urn:telco:graph:bites:doc-msa-v1> {
    ?specIri telco:hasSlaClause ?slaClause .
    OPTIONAL { ?slaClause rdfs:label ?slaPolicyLabel . }
  }
  OPTIONAL {
    GRAPH <urn:telco:graph:bridge:er> {
      ?erMention telco:resolvedToCanonicalCustomer ?customerIri ;
                 telco:erConfidenceScore ?erScore ;
                 telco:erCurationStatus ?erStatus .
    }
  }
  FILTER(STR(?circuitId) = "{circuit_id}")
}
""".strip(),
            ),
            StoredSparqlTemplate(
                template_id="tpl_uc002_catalog_sku_lookup",
                description="Lookup B2B catalog SKU specification.",
                required_parameters=["sku_code"],
                tbox_classes=["tmf:ServiceSpecification"],
                sparql="""
PREFIX tmf: <http://tmforum.org/sid/>
PREFIX telco: <http://telco.enterprise.org/ontology/>
SELECT ?catalogSpec ?skuCode ?maxPacketLossPct ?autoRemediationAllowed
WHERE {
  GRAPH <urn:telco:graph:ref:catalog> {
    ?catalogSpec a tmf:ServiceSpecification ;
                 tmf:skuCode ?skuCode ;
                 telco:maxPacketLossPct ?maxPacketLossPct ;
                 telco:autoRemediationAllowed ?autoRemediationAllowed .
    FILTER(STR(?skuCode) = "{sku_code}")
  }
}
""".strip(),
            ),
            StoredSparqlTemplate(
                template_id="tpl_uc003_doc_lifecycle_audit",
                description="Audit document lifecycle status.",
                required_parameters=[],
                tbox_classes=[],
                sparql="""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX telco: <http://telco.enterprise.org/ontology/>
SELECT ?doc ?docLabel ?lifecycleStatus
WHERE {
  GRAPH <urn:telco:graph:meta:doc-lifecycle> {
    ?doc telco:lifecycleStatus ?lifecycleStatus .
    OPTIONAL { ?doc rdfs:label ?docLabel . }
  }
}
""".strip(),
            ),
        ]
    )


def _copy_promoted_workspace(tmp_path: Path) -> Path:
    """Create an isolated workspace copy with Track B + config/prompts/templates."""
    for rel_dir in (
        "data/semantic_store",
        "data/raw_sources/sql",
        "mappings",
        "prompts",
        "config",
        "reports",
        "logs",
        "shapes",
        "skills",
        "data/cqrs_state",
        "data/golden_reference",
        "data/raw_sources",
    ):
        (tmp_path / rel_dir).mkdir(parents=True, exist_ok=True)

    shutil.copy2(WORKSPACE_ROOT / "config.yaml", tmp_path / "config.yaml")
    shutil.copy2(
        WORKSPACE_ROOT / "data/semantic_store/tbox_sid_etom.ttl",
        tmp_path / "data/semantic_store/tbox_sid_etom.ttl",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "data/semantic_store/knowledge_graph.trig",
        tmp_path / "data/semantic_store/knowledge_graph.trig",
    )
    src_tmpl = WORKSPACE_ROOT / "data/semantic_store/stored_sparql_templates.yaml"
    if src_tmpl.exists():
        shutil.copy2(
            src_tmpl,
            tmp_path / "data/semantic_store/stored_sparql_templates.yaml",
        )
    else:
        import yaml

        (tmp_path / "data/semantic_store/stored_sparql_templates.yaml").write_text(
            yaml.safe_dump(
                {"templates": [t.model_dump() for t in _sample_catalog().templates]},
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    shutil.copy2(
        WORKSPACE_ROOT / "mappings/cmdb_r2rml.ttl",
        tmp_path / "mappings/cmdb_r2rml.ttl",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "data/raw_sources/sql/cmdb_installed_base.db",
        tmp_path / "data/raw_sources/sql/cmdb_installed_base.db",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "prompts/layer3_voicebox_hybrid_prompt.md",
        tmp_path / "prompts/layer3_voicebox_hybrid_prompt.md",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "prompts/layer3_template_compiler_prompt.md",
        tmp_path / "prompts/layer3_template_compiler_prompt.md",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "prompts/layer3_zero_shot_sparql_prompt.md",
        tmp_path / "prompts/layer3_zero_shot_sparql_prompt.md",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "data/raw_sources/uc001_use_case_charter.md",
        tmp_path / "data/raw_sources/uc001_use_case_charter.md",
    )
    shutil.copy2(
        WORKSPACE_ROOT / "config/mcp_primitives_catalog.json",
        tmp_path / "config/mcp_primitives_catalog.json",
    )
    return tmp_path


def test_ast_gatekeeper_valid_and_blocked_queries() -> None:
    tbox_path = WORKSPACE_ROOT / "data/semantic_store/tbox_sid_etom.ttl"
    trig_path = WORKSPACE_ROOT / "data/semantic_store/knowledge_graph.trig"

    valid_sparql = """
    PREFIX tmf: <http://tmforum.org/sid/>
    PREFIX telco: <http://telco.enterprise.org/ontology/>
    SELECT ?cfs ?circuitId ?cpeModelSku WHERE {
      GRAPH <urn:telco:graph:virtual:ib> {
        ?cfs a tmf:CustomerFacingService ;
             tmf:serviceId ?circuitId .
        ?rfs telco:cpeModelSku ?cpeModelSku .
      }
    }
    """
    res_ok = validate_sparql_ast(valid_sparql, tbox_path=tbox_path, trig_path=trig_path)
    assert res_ok.passed is True
    assert res_ok.query_type == "SelectQuery"
    assert res_ok.blocked_mutations == []
    assert res_ok.sql_leakage_matches == []
    assert res_ok.unknown_uris == []

    # Mutation blocked
    mutation_sparql = "DELETE WHERE { ?s ?p ?o }"
    res_mut = validate_sparql_ast(mutation_sparql, tbox_path=tbox_path)
    assert res_mut.passed is False
    assert "DELETE" in res_mut.blocked_mutations

    # SQL leakage blocked
    sql_leak_sparql = """
    PREFIX tmf: <http://tmforum.org/sid/>
    SELECT ?s WHERE { ?s tmf:serviceId "T_CMDB_CFS" . }
    """
    res_sql = validate_sparql_ast(sql_leak_sparql, tbox_path=tbox_path)
    assert res_sql.passed is False
    assert "T_CMDB_CFS" in res_sql.sql_leakage_matches

    # Hallucinated ontology URI blocked
    unknown_uri_sparql = """
    PREFIX telco: <http://telco.enterprise.org/ontology/>
    SELECT ?s WHERE { ?s telco:hallucinatedProperty ?o . }
    """
    res_unk = validate_sparql_ast(unknown_uri_sparql, tbox_path=tbox_path)
    assert res_unk.passed is False
    assert "http://telco.enterprise.org/ontology/hallucinatedProperty" in res_unk.unknown_uris

    # Syntax error blocked
    res_syn = validate_sparql_ast("SELECT * WHERE { ?s ?p", tbox_path=tbox_path)
    assert res_syn.passed is False
    assert res_syn.syntax_error is not None


def test_layer3_contains_zero_physical_sql_references() -> None:
    layer3_dir = WORKSPACE_ROOT / "src/layer3"
    forbidden = ("T_CMDB_", "T_OSS_", "cmdb_r2rml.ttl", "CFS_ROW_ID")
    for py_file in layer3_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in content, f"Forbidden SQL/R2RML token '{token}' in {py_file}"


def test_layer3_dual_comparison_and_modes(tmp_path: Path) -> None:
    ws = _copy_promoted_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = logging.getLogger("test_layer3")

    def fake_gemini(
        config: AppConfig,
        logger: logging.Logger,
        model_name: str,
        prompt_text: str,
        schema_cls: type,
    ):
        if schema_cls is VoiceboxHybridSelectionProposal:
            return VoiceboxHybridSelectionProposal(
                template_id="tpl_uc001_circuit_assurance_context",
                pruned_tbox_classes=["tmf:CustomerFacingService", "tmf:ResourceFacingService"],
                pruned_tbox_properties=["tmf:serviceId", "telco:maxPacketLossPct"],
                parameters={"circuit_id": "CIR-994821"},
                reasoning="Matched 6-graph circuit assurance template.",
            )
        return ZeroShotSparqlProposal(
            sparql_query=(
                "PREFIX telco: <http://telco.enterprise.org/ontology/>\n"
                "SELECT ?s WHERE { ?s telco:hallucinatedMetric ?v . }"
            ),
            reasoning="Zero-shot attempt without templates.",
        )

    with patch("src.layer3.nl2semantics_engine._call_gemini_structured", side_effect=fake_gemini):
        dual_res = run_layer3_nl2semantics(
            natural_language_intent="Get assurance context for CIR-994821",
            config=config,
            logger=logger,
            target_circuit_id="CIR-994821",
            execution_mode="dual_comparison",
            root_dir=ws,
        )
        assert dual_res.voicebox_result is not None
        assert dual_res.zero_shot_result is not None
        assert dual_res.voicebox_result.ast_audit.passed is True
        assert dual_res.voicebox_result.row_count == 1
        assert dual_res.authoritative_context is not None
        assert dual_res.authoritative_context.circuit_id == "CIR-994821"
        assert dual_res.authoritative_context.product_sku == "ETH-10G-GOLD"
        assert dual_res.authoritative_context.rx_los_cut_threshold_dbm == -27.5
        assert dual_res.zero_shot_result.ast_audit.passed is False
        assert dual_res.zero_shot_result.row_count == 0
        assert dual_res.disk_virtual_ib_triples_after == 0
        assert dual_res.report_html_path.exists()
        assert dual_res.report_markdown_path.exists()

        vb_only = run_layer3_nl2semantics(
            natural_language_intent="Get assurance context for CIR-994821",
            config=config,
            logger=logger,
            target_circuit_id="CIR-994821",
            execution_mode="voicebox_hybrid",
            root_dir=ws,
        )
        assert vb_only.voicebox_result is not None
        assert vb_only.zero_shot_result is None

        zs_only = run_layer3_nl2semantics(
            natural_language_intent="Get assurance context for CIR-994821",
            config=config,
            logger=logger,
            target_circuit_id="CIR-994821",
            execution_mode="zero_shot_llm",
            root_dir=ws,
        )
        assert zs_only.voicebox_result is None
        assert zs_only.zero_shot_result is not None
        assert zs_only.zero_shot_result.ast_audit.passed is False

    # Verify DT-00 cleans RT-05 reports
    reset_to_clean_slate(config, logger, workspace_root=ws)
    assert not dual_res.report_html_path.exists()
    assert not dual_res.report_markdown_path.exists()


def test_semantic_read_mcp_obo_jwt_validation(tmp_path: Path) -> None:
    ws = _copy_promoted_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = logging.getLogger("test_mcp")

    def fake_vb_only(
        config: AppConfig,
        logger: logging.Logger,
        model_name: str,
        prompt_text: str,
        schema_cls: type,
    ):
        return VoiceboxHybridSelectionProposal(
            template_id="tpl_uc001_circuit_assurance_context",
            pruned_tbox_classes=["tmf:CustomerFacingService"],
            pruned_tbox_properties=["tmf:serviceId"],
            parameters={"circuit_id": "CIR-994821"},
            reasoning="Matched template.",
        )

    with patch("src.layer3.nl2semantics_engine._call_gemini_structured", side_effect=fake_vb_only):
        # 1. Standalone bypass when require_obo_jwt=False and obo_jwt=None
        out_bypass = execute_query_knowledge_fabric(
            natural_language_intent="Get CIR-994821",
            target_circuit_id="CIR-994821",
            execution_mode="voicebox_hybrid",
            obo_jwt=None,
            config=config,
            logger=logger,
            root_dir=ws,
        )
        assert out_bypass["auth_metadata"]["auth_mode"] == "STANDALONE_RT05_BYPASS"
        assert out_bypass["auth_metadata"]["obo_jwt_present"] is False

        # 2. Valid OBO JWT
        valid_token = jwt.encode(
            {"sub": "worker-agent-01", "scp": ["semantic:read"], "exp": int(time.time()) + 300},
            "test-secret-key-at-least-32-bytes!",
            algorithm="HS256",
        )
        out_jwt = execute_query_knowledge_fabric(
            natural_language_intent="Get CIR-994821",
            target_circuit_id="CIR-994821",
            execution_mode="voicebox_hybrid",
            obo_jwt=valid_token,
            config=config,
            logger=logger,
            root_dir=ws,
        )
        assert out_jwt["auth_metadata"]["obo_jwt_verified"] is True
        assert out_jwt["auth_metadata"]["obo_subject"] == "worker-agent-01"

        # 3. Wrong scope OBO JWT -> PermissionError
        bad_scope_token = jwt.encode(
            {"sub": "worker-agent-01", "scp": ["action:write"], "exp": int(time.time()) + 300},
            "test-secret-key-at-least-32-bytes!",
            algorithm="HS256",
        )
        with pytest.raises(PermissionError, match="lacks required scope"):
            execute_query_knowledge_fabric(
                natural_language_intent="Get CIR-994821",
                target_circuit_id="CIR-994821",
                execution_mode="voicebox_hybrid",
                obo_jwt=bad_scope_token,
                config=config,
                logger=logger,
                root_dir=ws,
            )

        # 4. Expired OBO JWT -> PermissionError
        expired_token = jwt.encode(
            {"sub": "worker-agent-01", "scp": ["semantic:read"], "exp": int(time.time()) - 60},
            "test-secret-key-at-least-32-bytes!",
            algorithm="HS256",
        )
        with pytest.raises(PermissionError, match="Invalid or expired"):
            execute_query_knowledge_fabric(
                natural_language_intent="Get CIR-994821",
                target_circuit_id="CIR-994821",
                execution_mode="voicebox_hybrid",
                obo_jwt=expired_token,
                config=config,
                logger=logger,
                root_dir=ws,
            )

        # 5. Missing OBO JWT when require_obo_jwt=True -> PermissionError
        strict_l3 = Layer3Nl2SemanticsSettings(
            **{**config.layer3_nl2semantics.model_dump(), "require_obo_jwt": True}
        )
        strict_cfg = config.model_copy(update={"layer3_nl2semantics": strict_l3})
        with pytest.raises(PermissionError, match="Missing mandatory OBO JWT"):
            execute_query_knowledge_fabric(
                natural_language_intent="Get CIR-994821",
                target_circuit_id="CIR-994821",
                execution_mode="voicebox_hybrid",
                obo_jwt=None,
                config=strict_cfg,
                logger=logger,
                root_dir=ws,
            )


def test_template_compiler_and_fail_fast_missing_templates(tmp_path: Path) -> None:
    ws = _copy_promoted_workspace(tmp_path)
    config = load_config(ws / "config.yaml")
    logger = logging.getLogger("test_template_compiler")

    tmpl_path = ws / config.layer3_nl2semantics.stored_sparql_templates_path
    if tmpl_path.exists():
        tmpl_path.unlink()

    # Fail fast with RuntimeError when templates are missing
    with pytest.raises(RuntimeError, match="Stored SPARQL templates catalog not found"):
        run_layer3_nl2semantics(
            natural_language_intent="Get assurance context for CIR-994821",
            config=config,
            logger=logger,
            target_circuit_id="CIR-994821",
            execution_mode="voicebox_hybrid",
            root_dir=ws,
        )

    sample_catalog = _sample_catalog()

    with patch(
        "src.layer3.template_compiler._call_template_compiler_llm",
        return_value=sample_catalog,
    ):
        comp_res = compile_stored_sparql_templates(
            config=config, logger=logger, root_dir=ws
        )
        assert comp_res.ast_passed_count == 3
        assert comp_res.layer4_verified_rows == 1
        assert tmpl_path.exists()

    # Verify DT-00 deletes stored_sparql_templates.yaml
    reset_to_clean_slate(config, logger, workspace_root=ws)
    assert not tmpl_path.exists()
