"""
Unit Tests for Step 4 (`DT-01c`): Prong 3 PDF BITES Extractor, Fuzzy Entity
Resolution (`rapidfuzz`) & Two-Phase Mandatory HITL Gate 2 Lock.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import warnings

import pytest
from rdflib import Dataset, URIRef

from src.config_loader import get_workspace_root, load_config
from src.models import (
    CanonicalCustomerRecord,
    CustomerMentionCandidate,
    ExtractedBitesTriple,
    PdfBitesLlmProposal,
    PdfDocumentExtractionProposal,
    PdfPageRelevanceDecision,
)
from src.state_inspector import inspect_system_state
from src.state_manager import reset_to_clean_slate
from src.track_b.s3_pdf_bites_er_ingestor import (
    GRAPH_BRIDGE_ER,
    GRAPH_META_DOC_LIFECYCLE,
    GRAPH_REF_CATALOG,
    GRAPH_TBOX_URI,
    GRAPH_VIRTUAL_IB,
    introspect_pdf_corpus,
    resolve_customer_mentions_fuzzy,
    run_dt01c_pdf_bites_gate2,
)


def _setup_isolated_workspace(tmp_path: Path, include_dt01b: bool = True) -> Path:
    """Copy required Stage 0/2/3 inputs into an isolated temporary workspace."""
    repo_root = get_workspace_root()
    files_to_copy = [
        "config.yaml",
        "config/mcp_primitives_catalog.json",
        "data/raw_sources/uc001_use_case_charter.md",
        "data/raw_sources/sql/cmdb_installed_base.db",
        "data/raw_sources/pdf/Vendor_Optical_Hardware_Manual_v4.pdf",
        "data/raw_sources/pdf/MSA_Contract_A_Corporate_Enterprise_2026.pdf",
        "data/semantic_store/tbox_sid_etom.ttl",
        "data/semantic_store/knowledge_graph.trig",
        "mappings/cmdb_r2rml.ttl",
        "prompts/s3_pdf_bites_extractor_prompt.md",
        "reports/hitl_gate1_ontology_mapping_review.html",
    ]
    if include_dt01b:
        files_to_copy.append("reports/shacl_quarantine_summary.json")

    for rel in files_to_copy:
        src = repo_root / rel
        if not src.exists():
            continue
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Ensure the isolated TriG starts in pre-Step-4 state (no promoted BITES/ER graphs)
    trig_path = tmp_path / "data/semantic_store/knowledge_graph.trig"
    if trig_path.exists():
        ds = Dataset()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
            ds.parse(str(trig_path), format="trig")
            for g_uri in [
                URIRef("urn:telco:graph:bites:doc-hw-v4"),
                URIRef("urn:telco:graph:bites:doc-msa-v1"),
                GRAPH_META_DOC_LIFECYCLE,
                GRAPH_BRIDGE_ER,
            ]:
                ds.remove((None, None, None, g_uri))
            ds.serialize(destination=str(trig_path), format="trig")
    return tmp_path


def _build_mock_llm_proposal(corpus_docs: dict) -> PdfBitesLlmProposal:
    """Build a realistic Gemini PdfBitesLlmProposal using live introspected SHA-256 hashes."""
    hw_doc = corpus_docs["Vendor_Optical_Hardware_Manual_v4.pdf"]
    msa_doc = corpus_docs["MSA_Contract_A_Corporate_Enterprise_2026.pdf"]

    return PdfBitesLlmProposal(
        document_extractions=[
            PdfDocumentExtractionProposal(
                pdf_filename=hw_doc.pdf_filename,
                sha256_hash=hw_doc.sha256_hash,
                assigned_scope="GLOBAL_SCOPE",
                target_named_graph_uri="urn:telco:graph:bites:doc-hw-v4",
                document_version="v4.0",
                document_summary="Vendor optical transceiver calibration thresholds.",
                page_decisions=[
                    PdfPageRelevanceDecision(
                        page_number=p.page_number,
                        classification=(
                            "RELEVANT_EXTRACTED" if p.page_number == 4 else "EXCLUDED_DISTRACTOR_PAGE"
                        ),
                        section_title=f"Page {p.page_number}",
                        rationale="Optical calibration chapter vs. non-optical hardware specs.",
                    )
                    for p in hw_doc.pages
                ],
                extracted_triples=[
                    ExtractedBitesTriple(
                        subject_iri="urn:telco:hw:profile:NOK-7210-SAS-Mxp",
                        predicate_qname="rdf:type",
                        object_value="telco:OpticalCalibrationProfile",
                        object_kind="IRI",
                        source_page_number=4,
                        evidence_snippet="SFP+ 10GBASE-LR optical calibration profile.",
                    ),
                    ExtractedBitesTriple(
                        subject_iri="urn:telco:hw:profile:NOK-7210-SAS-Mxp",
                        predicate_qname="telco:softDegradationMinRxDbm",
                        object_value="-27.5",
                        object_kind="LITERAL",
                        datatype_qname="xsd:double",
                        source_page_number=4,
                        evidence_snippet="DDM recalibration window [-25.0, -27.5 dBm].",
                    ),
                ],
                customer_mentions=[],
            ),
            PdfDocumentExtractionProposal(
                pdf_filename=msa_doc.pdf_filename,
                sha256_hash=msa_doc.sha256_hash,
                assigned_scope="DOCUMENT_SCOPE",
                target_named_graph_uri="urn:telco:graph:bites:doc-msa-v1",
                document_version="2026-v1",
                document_summary="Enterprise MSA SLA terms and DDM auto-remediation clause.",
                page_decisions=[
                    PdfPageRelevanceDecision(
                        page_number=p.page_number,
                        classification=(
                            "RELEVANT_EXTRACTED" if p.page_number >= 2 else "EXCLUDED_DISTRACTOR_PAGE"
                        ),
                        section_title=f"Page {p.page_number}",
                        rationale="SLA & auto-remediation annex vs. general legal boilerplate.",
                    )
                    for p in msa_doc.pages
                ],
                extracted_triples=[
                    ExtractedBitesTriple(
                        subject_iri="urn:telco:msa:clause:CIR-994821-ddm",
                        predicate_qname="rdf:type",
                        object_value="telco:SlaClause",
                        object_kind="IRI",
                        source_page_number=2,
                        evidence_snippet="Pre-authorized non-intrusive DDM recalibration.",
                    ),
                    ExtractedBitesTriple(
                        subject_iri="urn:telco:msa:clause:CIR-994821-ddm",
                        predicate_qname="telco:autoRemediationPreAuthorized",
                        object_value="true",
                        object_kind="LITERAL",
                        datatype_qname="xsd:boolean",
                        source_page_number=2,
                        evidence_snippet="Authorized when no maintenance lock is active.",
                    ),
                ],
                customer_mentions=[
                    CustomerMentionCandidate(
                        mention_text="A Corporate Enterprise B.V.",
                        registration_number="NL-8841209",
                        source_page_number=1,
                        context_snippet="MSA between Telco and A Corporate Enterprise B.V. (NL-8841209).",
                        mention_subject_iri="urn:telco:bites:mention:a-corporate-enterprise-bv",
                    )
                ],
            ),
        ],
        architect_verification_questions=[
            "Confirm KEEP_QUARANTINED disposition for the 2 pySHACL-quarantined Excel rows.",
            "Confirm GLOBAL_SCOPE vs. DOCUMENT_SCOPE partitioning for the 2 PDFs.",
            "Approve the fuzzy ER bridge between 'A Corporate Enterprise B.V.' and CUST-ENT-409.",
            "Authorize promotion of BITES, Lifecycle ACTIVE, and ER bridge triples into knowledge_graph.trig.",
        ],
    )


def test_zero_hardcoded_pdf_pages_skus_or_customers() -> None:
    """Verify s3_pdf_bites_er_ingestor.py contains zero hardcoded PDF/SKU/customer literals."""
    source_path = get_workspace_root() / "src" / "track_b" / "s3_pdf_bites_er_ingestor.py"
    source_text = source_path.read_text(encoding="utf-8")

    forbidden = [
        "NOK-7210-SAS-Mxp",
        "A Corporate Enterprise",
        "CUST-ENT-409",
        "NL-8841209",
        "Vendor_Optical_Hardware_Manual_v4.pdf",
        "MSA_Contract_A_Corporate_Enterprise_2026.pdf",
    ]
    for literal in forbidden:
        assert literal not in source_text, (
            f"Hardcoded literal '{literal}' found in s3_pdf_bites_er_ingestor.py"
        )


def test_dt01c_fails_fast_when_dt01a_missing_or_unapproved(tmp_path: Path) -> None:
    """Verify DT-01c fails fast if DT-01a is missing or not LOCKED_APPROVED."""
    config = load_config()
    logger = logging.getLogger("test_dt01c_prereq")

    with pytest.raises(RuntimeError, match="DT-01a"):
        run_dt01c_pdf_bites_gate2(
            config=config, logger=logger, mode="candidate", root_dir=tmp_path
        )

    ws = _setup_isolated_workspace(tmp_path, include_dt01b=False)
    gate1_path = ws / config.track_b_ingestion_and_er.hitl_gate1_report_path
    gate1_path.write_text("<html><body>CANDIDATE_PROPOSED</body></html>", encoding="utf-8")

    with pytest.raises(RuntimeError, match="LOCKED_APPROVED"):
        run_dt01c_pdf_bites_gate2(
            config=config, logger=logger, mode="candidate", root_dir=ws
        )


def test_rapidfuzz_composite_scoring_in_hitl_review_band() -> None:
    """Verify rapidfuzz composite scoring places legal-suffix variation in [0.85, 0.95]."""
    doc = PdfDocumentExtractionProposal(
        pdf_filename="contract.pdf",
        sha256_hash="a" * 64,
        assigned_scope="DOCUMENT_SCOPE",
        target_named_graph_uri="urn:telco:graph:bites:doc-msa-v1",
        document_version="v1",
        document_summary="Summary",
        page_decisions=[
            PdfPageRelevanceDecision(
                page_number=1,
                classification="RELEVANT_EXTRACTED",
                section_title="Parties",
                rationale="Party identification",
            )
        ],
        extracted_triples=[
            ExtractedBitesTriple(
                subject_iri="urn:telco:msa:clause:1",
                predicate_qname="rdf:type",
                object_value="telco:SlaClause",
                object_kind="IRI",
                source_page_number=1,
                evidence_snippet="Clause 1",
            )
        ],
        customer_mentions=[
            CustomerMentionCandidate(
                mention_text="A Corporate Enterprise B.V.",
                registration_number="NL-8841209",
                source_page_number=1,
                context_snippet="Customer legal name",
                mention_subject_iri="urn:telco:bites:mention:cust",
            )
        ],
    )
    canon = [
        CanonicalCustomerRecord(
            customer_id="CUST-ENT-409",
            customer_name="A Corporate Enterprise",
            subject_iri="urn:telco:cmdb:customer:CUST-ENT-409",
            registration_number="NL-8841209",
        )
    ]

    matches = resolve_customer_mentions_fuzzy([doc], canon, 0.85, 0.95)
    assert len(matches) == 1
    assert 0.85 <= matches[0].composite_confidence <= 0.95
    assert matches[0].curation_status == "CURATION_PENDING"
    assert matches[0].canonical_customer_id == "CUST-ENT-409"


def test_dt01c_two_phase_candidate_then_approve_and_sys01_transitions(
    tmp_path: Path,
) -> None:
    """
    Verify Two-Phase HITL Gate 2:
      - Phase 1 (--mode candidate): Writes gate2_candidate_proposal.json + HTML/MD
        reports, keeps BITES/ER graphs unpromoted, SYS-01 Element 4 = CURATION_PENDING.
      - Phase 2 (--mode approve): Populates BITES, doc-lifecycle, and ER bridge graphs
        in knowledge_graph.trig, keeps <urn:telco:graph:virtual:ib> = 0, SYS-01 Element 4 = PROMOTED.
      - DT-00 reset: Removes Gate 2 artifacts and resets Element 4 to EMPTY.
    """
    ws = _setup_isolated_workspace(tmp_path, include_dt01b=True)
    config = load_config()
    logger = logging.getLogger("test_dt01c_e2e")

    pdf_dir = ws / config.paths.raw_sources_dir / config.paths.pdf_subdir
    corpus = introspect_pdf_corpus(pdf_dir, ws)
    corpus_docs = {doc.pdf_filename: doc for doc in corpus.documents}

    mock_proposal = _build_mock_llm_proposal(corpus_docs)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = SimpleNamespace(
        text=mock_proposal.model_dump_json()
    )

    with patch(
        "src.track_b.s3_pdf_bites_er_ingestor.create_genai_client",
        return_value=mock_client,
    ):
        cand_res = run_dt01c_pdf_bites_gate2(
            config=config, logger=logger, mode="candidate", root_dir=ws
        )

    assert cand_res.gate2_status == "CURATION_PENDING"
    assert cand_res.active_pdfs_count == 2
    assert cand_res.er_links_count == 1
    assert len(cand_res.architect_verification_questions) == 4
    assert cand_res.candidate_proposal_path.exists()
    assert cand_res.gate2_html_report_path.exists()
    assert cand_res.gate2_markdown_report_path.exists()

    # Verify TriG store has NOT promoted BITES or ER graphs yet
    ds_cand = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds_cand.parse(str(cand_res.trig_dataset_path), format="trig")
    assert len(ds_cand.graph(URIRef("urn:telco:graph:bites:doc-hw-v4"))) == 0
    assert len(ds_cand.graph(URIRef("urn:telco:graph:bites:doc-msa-v1"))) == 0
    assert len(ds_cand.graph(GRAPH_BRIDGE_ER)) == 0
    assert len(ds_cand.graph(GRAPH_VIRTUAL_IB)) == 0

    sys_cand = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    elem4_cand = next(e for e in sys_cand.elements if e.element_number == 4)
    assert elem4_cand.state == "CURATION_PENDING (Awaiting HITL Gate 2)"

    # Phase 2: --mode approve
    app_res = run_dt01c_pdf_bites_gate2(
        config=config, logger=logger, mode="approve", root_dir=ws
    )
    assert app_res.gate2_status == "PROMOTED"
    assert app_res.global_scope_triples_count == 2
    assert app_res.document_scope_triples_count == 2
    assert app_res.doc_lifecycle_triples_count > 0
    assert app_res.er_bridge_triples_count == 5
    assert app_res.virtual_ib_triples_count == 0

    ds_app = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds_app.parse(str(app_res.trig_dataset_path), format="trig")
    assert len(ds_app.graph(GRAPH_TBOX_URI)) > 0
    assert len(ds_app.graph(GRAPH_REF_CATALOG)) > 0
    assert len(ds_app.graph(GRAPH_VIRTUAL_IB)) == 0
    assert len(ds_app.graph(URIRef("urn:telco:graph:bites:doc-hw-v4"))) == 2
    assert len(ds_app.graph(URIRef("urn:telco:graph:bites:doc-msa-v1"))) == 2
    assert len(ds_app.graph(GRAPH_META_DOC_LIFECYCLE)) > 0
    assert len(ds_app.graph(GRAPH_BRIDGE_ER)) == 5

    sys_app = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    elem4_app = next(e for e in sys_app.elements if e.element_number == 4)
    assert elem4_app.state == "PROMOTED"
    assert "HITL Gate 2: APPROVED" in elem4_app.metrics_summary

    # Verify DT-00 reset cleans Gate 2 artifacts and resets Element 4 to EMPTY
    reset_to_clean_slate(config=config, logger=logger, workspace_root=ws)
    assert not app_res.candidate_proposal_path.exists()
    assert not app_res.gate2_html_report_path.exists()
    sys_reset = inspect_system_state(
        config=config, logger=logger, workspace_root=ws, render_console=False
    )
    elem4_reset = next(e for e in sys_reset.elements if e.element_number == 4)
    assert elem4_reset.state == "EMPTY"

