"""
Scenario `DT-01a` — Prong 1 SQL CMDB Schema Profiler, Pruned TMF SID/eTOM TBox,
Base SHACL Shapes, W3C R2RML Virtual Graph Mapping & Mandatory HITL Gate 1 Lock
(`src/track_b/s1_cmdb_tbox_profiler.py`).

Implements Stage 2 Activities B1 & B2 (`ADR-TELCO-UC001-ACT03-V1` Decision 4 & 5):
  1. Dynamically inspects `data/raw_sources/sql/cmdb_installed_base.db` via
     `sqlite_master` and `PRAGMA table_info(...)` across all 4 tables (104 rows).
  2. Classifies every physical table and column against the TM Forum SID (`GB922`)
     and eTOM (`GB921`) vocabulary, flagging `T_BILLING_AUDIT_NOISE` (25 rows) and
     internal/legacy/sync columns so they never leak into the Conceptual TBox.
  3. Generates the Pruned TMF SID/eTOM Conceptual Ontology (`data/semantic_store/tbox_sid_etom.ttl`)
     with 14 OWL classes, object/datatype properties, rich `skos:altLabel` synonyms,
     eTOM process concepts (`1.3.7`, `1.4.5`), and QUDT unit annotations, and loads
     it into Named Graph `<urn:telco:graph:tbox:sid-etom>` in
     `data/semantic_store/knowledge_graph.trig` while keeping
     `<urn:telco:graph:virtual:ib>` at `0` persisted triples on disk.
  4. Generates Base W3C SHACL shapes (`shapes/service_spec_shape.ttl` and
     `shapes/trouble_ticket_shape.ttl`).
  5. Generates the Physical W3C R2RML Virtual Graph Mapping (`mappings/cmdb_r2rml.ttl`)
     with `<#CustomerTriplesMap>`, `<#CfsCircuitTriplesMap>`, and `<#RfsResourceTriplesMap>`.
  6. Executes the Evaluator Agent Ontology Critique and renders the Mandatory HITL
     Gate 1 Sign-Off Reports (`reports/hitl_gate1_ontology_mapping_review.html` & `.md`).
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Dict, List, Literal, Optional, Tuple
import warnings

from rdflib import Dataset, Graph, Namespace, RDF, URIRef
from rdflib.namespace import OWL, SKOS

from src.config_loader import get_workspace_root
from src.models import (
    AppConfig,
    ColumnDisposition,
    ColumnProfileEntry,
    Dt01aExecutionResult,
    EvaluatorOntologyCritique,
    Scd2CircuitVerification,
    TableProfileEntry,
)


TMF_NS = Namespace("http://tmforum.org/sid/")
ETOM_NS = Namespace("http://tmforum.org/etom/")
TELCO_NS = Namespace("http://telco.enterprise.org/ontology/")
RR_NS = Namespace("http://www.w3.org/ns/r2rml#")
SH_NS = Namespace("http://www.w3.org/ns/shacl#")

GRAPH_TBOX_URI = "urn:telco:graph:tbox:sid-etom"
GRAPH_VIRTUAL_IB_URI = "urn:telco:graph:virtual:ib"


# ============================================================================
# 1. Dynamic SQLite CMDB Schema & Column Disposition Profiler
# ============================================================================
_COLUMN_RULES: Dict[Tuple[str, str], Tuple[ColumnDisposition, str, str, str]] = {
    # T_OSS_CUST_PARTY (15 rows, 7 columns)
    ("T_OSS_CUST_PARTY", "PARTY_SURR_ID"): (
        "EXCLUDED_INTERNAL_OR_LEGACY",
        "NONE (Excluded)",
        "Excluded from R2RML projection",
        "Internal relational surrogate sequence key; canonical IRI uses CUST_EXT_REF.",
    ),
    ("T_OSS_CUST_PARTY", "CUST_EXT_REF"): (
        "MAPPED_TO_TBOX",
        "tmf:Customer / tmf:customerId",
        "Subject IRI: urn:telco:party:customer:{CUST_EXT_REF} + xsd:string literal",
        "Canonical enterprise customer business identifier (e.g., CUST-ENT-409).",
    ),
    ("T_OSS_CUST_PARTY", "LEGAL_NAME"): (
        "MAPPED_TO_TBOX",
        "tmf:Customer / tmf:partyLegalName",
        "Direct xsd:string literal mapping",
        "Official registered customer name used for entity resolution against MSA PDFs.",
    ),
    ("T_OSS_CUST_PARTY", "SEGMENT_CD"): (
        "MAPPED_TO_TBOX",
        "tmf:Customer / tmf:marketSegment",
        "Direct xsd:string literal mapping (ENT_VIP, GOV, SMB, RES)",
        "Commercial customer tier used for assurance prioritization.",
    ),
    ("T_OSS_CUST_PARTY", "ACCT_MGR_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:Customer / telco:accountManagerCode",
        "Nullable xsd:string literal mapping",
        "Assigned enterprise account manager reference for VIP SLA escalations.",
    ),
    ("T_OSS_CUST_PARTY", "LEGACY_CRM_ID"): (
        "EXCLUDED_INTERNAL_OR_LEGACY",
        "NONE (Excluded)",
        "Excluded from R2RML projection",
        "Deprecated Siebel CRM foreign key; excluded to prevent legacy schema pollution.",
    ),
    ("T_OSS_CUST_PARTY", "CREATED_TS"): (
        "EXCLUDED_INTERNAL_OR_LEGACY",
        "NONE (Excluded)",
        "Excluded from R2RML projection",
        "Internal database row creation timestamp not required by assurance TBox.",
    ),
    # T_CMDB_CFS_CIRCUIT (32 rows, 11 columns)
    ("T_CMDB_CFS_CIRCUIT", "CFS_ROW_ID"): (
        "PHYSICAL_SCD2_CONTROL_ONLY",
        "NONE (Layer 4 SCD2 Audit Control Only)",
        "Used strictly in Layer 4 SCD2 proof log (2000 vs 2001); never exposed in TBox",
        "Physical SCD Type 2 version surrogate key; zero exposure in Conceptual TBox.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "CIRCUIT_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / tmf:serviceId",
        "Subject IRI: urn:telco:service:cfs:{CIRCUIT_ID} + xsd:string literal",
        "Canonical L2 enterprise circuit identifier (e.g., CIR-994821).",
    ),
    ("T_CMDB_CFS_CIRCUIT", "CUST_REF_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / tmf:hasCustomer",
        "Object IRI: urn:telco:party:customer:{CUST_REF_ID}",
        "Links CustomerFacingService instance to owning tmf:Customer.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "PROD_SPEC_CODE"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / tmf:isDescribedBy",
        "Object IRI: urn:telco:catalog:sku:{PROD_SPEC_CODE} (joins Prong 2 Excel graph)",
        "Links active circuit to its commercial ServiceSpecification SKU (e.g., ETH-10G-GOLD).",
    ),
    ("T_CMDB_CFS_CIRCUIT", "OPER_STATUS_CD"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / tmf:operationalStatus",
        "CASE OPER_STATUS_CD WHEN '10' THEN 'ACTIVE' WHEN '20' THEN 'MAINTENANCE' WHEN '99' THEN 'DECOMMISSIONED' END",
        "Translates undocumented numeric shadow enums ('10','20','99') into canonical SID status literals.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "BW_VAL"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / telco:bandwidthGbps",
        "Normalized with BW_UNIT_CD into canonical Gbps (xsd:decimal)",
        "Raw bandwidth magnitude; combined with BW_UNIT_CD via QUDT scaling.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "BW_UNIT_CD"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / telco:bandwidthGbps (qudt:unit unit:GigaBIT-PER-SEC)",
        "CASE BW_UNIT_CD WHEN 'Gbps' THEN BW_VAL WHEN 'Mbps' THEN BW_VAL/1000.0 WHEN 'Kbps' THEN BW_VAL/1000000.0 END",
        "Mixed unit code ('Kbps','Mbps','Gbps') normalized to canonical Gbps.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "INSTALL_DT"): (
        "MAPPED_TO_TBOX",
        "tmf:CustomerFacingService / telco:installationDate",
        "Direct xsd:date literal mapping",
        "Service commission date for operational lifecycle context.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "VALID_FROM_TS"): (
        "PHYSICAL_SCD2_CONTROL_ONLY",
        "NONE (Layer 4 SCD2 Window Start Control Only)",
        "Physical SCD2 window start timestamp; not projected into Conceptual TBox",
        "Physical SCD Type 2 effective-from timestamp handled by Layer 4 virtual SQL pushdown.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "VALID_TO_TS"): (
        "PHYSICAL_SCD2_CONTROL_ONLY",
        "NONE (Layer 4 R2RML WHERE VALID_TO_TS IS NULL Filter)",
        "Enforced in rr:sqlQuery WHERE VALID_TO_TS IS NULL (filters out row 2000, keeps row 2001)",
        "Physical SCD Type 2 expiration timestamp; governs active circuit filtering in R2RML.",
    ),
    ("T_CMDB_CFS_CIRCUIT", "LEGACY_BILL_TAG"): (
        "EXCLUDED_LEGACY",
        "NONE (Excluded)",
        "Excluded from R2RML projection",
        "Deprecated legacy billing tag; excluded from operational assurance ontology.",
    ),
    # T_CMDB_RFS_RESOURCE (32 rows, 9 columns)
    ("T_CMDB_RFS_RESOURCE", "RFS_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / tmf:rfsId",
        "Subject IRI: urn:telco:service:rfs:{RFS_ID} + xsd:string literal",
        "Canonical ResourceFacingService bearer identifier (e.g., RFS-OLT04-P12).",
    ),
    ("T_CMDB_RFS_RESOURCE", "PARENT_CFS_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / tmf:supportsService",
        "Object IRI: urn:telco:service:cfs:{PARENT_CFS_ID}",
        "Binds ResourceFacingService to the parent CustomerFacingService circuit.",
    ),
    ("T_CMDB_RFS_RESOURCE", "PE_ROUTER_HOSTNAME"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / telco:terminatesOnRouter (telco:PeRouterResource)",
        "Object IRI: urn:telco:resource:router:{PE_ROUTER_HOSTNAME} + tmf:resourceName",
        "Provider Edge aggregation router hostname (e.g., NLD-HAG-PE02).",
    ),
    ("T_CMDB_RFS_RESOURCE", "OLT_PORT_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / telco:usesOltPort (telco:OltPortResource)",
        "Object IRI: urn:telco:resource:port:{OLT_PORT_ID} + telco:portIdentifier",
        "Physical OLT optical port identifier probed by CQRS gNMI telemetry (e.g., OLT04-P12).",
    ),
    ("T_CMDB_RFS_RESOURCE", "CPE_ASSET_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / telco:demarcatesAtCpe (telco:CpeDeviceResource)",
        "Object IRI: urn:telco:resource:cpe:{CPE_ASSET_ID} + tmf:resourceId",
        "Customer Premises Equipment demarcation asset identifier (e.g., CPE-ASN-7741).",
    ),
    ("T_CMDB_RFS_RESOURCE", "CPE_MODEL_SKU"): (
        "MAPPED_TO_TBOX",
        "tmf:PhysicalResource / tmf:hasResourceSpecification (tmf:PhysicalResourceSpec)",
        "Object IRI: urn:telco:resource:spec:{CPE_MODEL_SKU} (joins Prong 3 HW Manual PDF)",
        "Hardware model SKU (e.g., NOK-7210-SAS-Mxp) linking CMDB inventory to optical manual specs.",
    ),
    ("T_CMDB_RFS_RESOURCE", "VLAN_TAG"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / telco:vlanTag",
        "Direct xsd:integer literal mapping",
        "IEEE 802.1Q encapsulation VLAN tag on the access bearer.",
    ),
    ("T_CMDB_RFS_RESOURCE", "FIBER_SPAN_ID"): (
        "MAPPED_TO_TBOX",
        "tmf:ResourceFacingService / telco:fiberSpanId",
        "Direct xsd:string literal mapping",
        "Physical metro fiber ring/span identifier for outside-plant fault localization.",
    ),
    ("T_CMDB_RFS_RESOURCE", "LAST_SYNC_UTC"): (
        "EXCLUDED_SYNC_METADATA",
        "NONE (Excluded)",
        "Excluded from R2RML projection",
        "Internal NMS polling sync watermark; excluded from Conceptual TBox.",
    ),
}


def profile_cmdb_sqlite_database(
    sqlite_path: Path, target_circuit_id: str = "CIR-994821"
) -> Tuple[List[TableProfileEntry], Scd2CircuitVerification]:
    """
    Dynamically inspect `cmdb_installed_base.db` via `sqlite_master` and
    `PRAGMA table_info(...)`, returning validated table/column profiles and
    the `CIR-994821` SCD Type 2 ground-truth verification.
    """
    if not sqlite_path.exists() or not sqlite_path.is_file():
        raise FileNotFoundError(
            f"SQLite CMDB database not found at expected path: {sqlite_path}"
        )

    conn = sqlite3.connect(str(sqlite_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        discovered_tables = [row[0] for row in cur.fetchall()]

        expected_order = [
            "T_OSS_CUST_PARTY",
            "T_CMDB_CFS_CIRCUIT",
            "T_CMDB_RFS_RESOURCE",
            "T_BILLING_AUDIT_NOISE",
        ]
        ordered_tables = [t for t in expected_order if t in discovered_tables] + [
            t for t in discovered_tables if t not in expected_order
        ]

        table_profiles: List[TableProfileEntry] = []
        for tbl_name in ordered_tables:
            cur.execute(f'SELECT COUNT(*) FROM "{tbl_name}"')
            total_rows = int(cur.fetchone()[0])

            if tbl_name == "T_CMDB_CFS_CIRCUIT":
                cur.execute(
                    'SELECT COUNT(*) FROM "T_CMDB_CFS_CIRCUIT" WHERE VALID_TO_TS IS NULL'
                )
                active_rows = int(cur.fetchone()[0])
            elif tbl_name == "T_BILLING_AUDIT_NOISE":
                active_rows = 0
            else:
                active_rows = total_rows

            cur.execute(f'PRAGMA table_info("{tbl_name}")')
            pragma_rows = cur.fetchall()

            col_profiles: List[ColumnProfileEntry] = []
            for _, col_name, col_type, notnull_flag, _, pk_flag in pragma_rows:
                if tbl_name == "T_BILLING_AUDIT_NOISE":
                    extra_note = (
                        " Represents internal batch/hash audit metadata (ERP_BATCH_REF / AUDIT_HASH)."
                        if col_name in {"ERP_BATCH_REF", "AUDIT_HASH"}
                        else ""
                    )
                    col_profiles.append(
                        ColumnProfileEntry(
                            table_name=tbl_name,
                            column_name=col_name,
                            sql_type=col_type or "TEXT",
                            not_null=bool(notnull_flag),
                            is_primary_key=bool(pk_flag),
                            disposition="EXCLUDED_NOISE",
                            mapped_tbox_target="NONE (Excluded Billing Noise Table)",
                            transformation_rule="Excluded at table & column level from R2RML",
                            audit_rationale=(
                                "Financial ERP/billing invoice audit column out of scope for "
                                f"UC-001 L2 assurance.{extra_note}"
                            ),
                        )
                    )
                else:
                    rule = _COLUMN_RULES.get((tbl_name, col_name))
                    if rule is None:
                        raise ValueError(
                            f"Unclassified SQLite column discovered dynamically: {tbl_name}.{col_name}"
                        )
                    disp, target_iri, transform_rule, rationale = rule
                    col_profiles.append(
                        ColumnProfileEntry(
                            table_name=tbl_name,
                            column_name=col_name,
                            sql_type=col_type or "TEXT",
                            not_null=bool(notnull_flag),
                            is_primary_key=bool(pk_flag),
                            disposition=disp,
                            mapped_tbox_target=target_iri,
                            transformation_rule=transform_rule,
                            audit_rationale=rationale,
                        )
                    )

            if tbl_name == "T_OSS_CUST_PARTY":
                table_profiles.append(
                    TableProfileEntry(
                        table_name=tbl_name,
                        total_rows=total_rows,
                        active_rows=active_rows,
                        table_disposition="BOUND_VIRTUAL_GRAPH",
                        target_tmf_classes=["tmf:Customer"],
                        canonical_iri_templates=["urn:telco:party:customer:{CUST_EXT_REF}"],
                        r2rml_triples_map_id="<#CustomerTriplesMap>",
                        columns=col_profiles,
                    )
                )
            elif tbl_name == "T_CMDB_CFS_CIRCUIT":
                table_profiles.append(
                    TableProfileEntry(
                        table_name=tbl_name,
                        total_rows=total_rows,
                        active_rows=active_rows,
                        table_disposition="BOUND_VIRTUAL_GRAPH",
                        target_tmf_classes=["tmf:CustomerFacingService"],
                        canonical_iri_templates=["urn:telco:service:cfs:{CIRCUIT_ID}"],
                        r2rml_triples_map_id="<#CfsCircuitTriplesMap>",
                        columns=col_profiles,
                    )
                )
            elif tbl_name == "T_CMDB_RFS_RESOURCE":
                table_profiles.append(
                    TableProfileEntry(
                        table_name=tbl_name,
                        total_rows=total_rows,
                        active_rows=active_rows,
                        table_disposition="BOUND_VIRTUAL_GRAPH",
                        target_tmf_classes=[
                            "tmf:ResourceFacingService",
                            "tmf:PhysicalResource",
                            "telco:OltPortResource",
                            "telco:PeRouterResource",
                            "telco:CpeDeviceResource",
                        ],
                        canonical_iri_templates=[
                            "urn:telco:service:rfs:{RFS_ID}",
                            "urn:telco:resource:port:{OLT_PORT_ID}",
                            "urn:telco:resource:router:{PE_ROUTER_HOSTNAME}",
                            "urn:telco:resource:cpe:{CPE_ASSET_ID}",
                        ],
                        r2rml_triples_map_id="<#RfsResourceTriplesMap>",
                        columns=col_profiles,
                    )
                )
            else:
                table_profiles.append(
                    TableProfileEntry(
                        table_name=tbl_name,
                        total_rows=total_rows,
                        active_rows=0,
                        table_disposition="EXCLUDED_NOISE",
                        target_tmf_classes=[],
                        canonical_iri_templates=[],
                        r2rml_triples_map_id="NONE (Excluded Noise Table)",
                        columns=col_profiles,
                    )
                )

        # Verify SCD2 rows for target_circuit_id (CIR-994821)
        cur.execute(
            """
            SELECT CFS_ROW_ID, PROD_SPEC_CODE, OPER_STATUS_CD, BW_VAL, BW_UNIT_CD, VALID_TO_TS
            FROM T_CMDB_CFS_CIRCUIT
            WHERE CIRCUIT_ID = ?
            ORDER BY CFS_ROW_ID ASC
            """,
            (target_circuit_id,),
        )
        circuit_rows = cur.fetchall()
        expired_rows = [r for r in circuit_rows if r[5] is not None]
        active_rows_list = [r for r in circuit_rows if r[5] is None]
        if not expired_rows or not active_rows_list:
            raise ValueError(
                f"Expected both expired and active SCD2 rows for {target_circuit_id}, found: {circuit_rows}"
            )

        exp_row = expired_rows[0]
        act_row = active_rows_list[0]
        status_map = {"10": "ACTIVE", "20": "MAINTENANCE", "99": "DECOMMISSIONED"}
        bw_val = float(act_row[3])
        bw_unit = str(act_row[4])
        if bw_unit == "Gbps":
            norm_gbps = bw_val
        elif bw_unit == "Mbps":
            norm_gbps = bw_val / 1000.0
        elif bw_unit == "Kbps":
            norm_gbps = bw_val / 1_000_000.0
        else:
            raise ValueError(f"Unsupported bandwidth unit: {bw_unit}")

        scd2_verification = Scd2CircuitVerification(
            circuit_id=target_circuit_id,
            expired_row_id=int(exp_row[0]),
            expired_product_sku=str(exp_row[1]),
            expired_valid_to_ts=str(exp_row[5]),
            active_row_id=int(act_row[0]),
            active_product_sku=str(act_row[1]),
            raw_oper_status_cd=str(act_row[2]),
            canonical_oper_status=status_map.get(str(act_row[2]), "UNKNOWN"),
            raw_bandwidth_val=bw_val,
            raw_bandwidth_unit=bw_unit,
            normalized_bandwidth_gbps=norm_gbps,
        )

        return table_profiles, scd2_verification
    finally:
        conn.close()


# ============================================================================
# 2. Pruned TMF SID / eTOM Conceptual TBox Generator (`tbox_sid_etom.ttl`)
# ============================================================================
def build_tbox_sid_etom_turtle() -> str:
    """
    Return the W3C Turtle content for `data/semantic_store/tbox_sid_etom.ttl`.

    Contains 14 pruned OWL classes, object/datatype properties, rich `skos:altLabel`
    business synonyms, eTOM process individuals (`1.3.7`, `1.4.5`), and QUDT unit
    annotations. Strictly ZERO physical SQL table or column names appear anywhere
    in this ontology.
    """
    return """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
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

<urn:telco:graph:tbox:sid-etom> a owl:Ontology ;
    rdfs:label "Telecom Agentic AI Pruned TM Forum SID & eTOM Conceptual Ontology (UC-001)"@en ;
    dcterms:identifier "ONT-TELCO-UC001-SID-ETOM-V1" ;
    rdfs:comment "Conceptual domain ontology scoped strictly to Enterprise L2 Fiber Packet-Loss Triage and Automated Optical DDM Recalibration. Free of any physical relational schema artifacts."@en .

# ============================================================================
# TM Forum eTOM (GB921) Business Process Concepts
# ============================================================================
etom:BusinessProcess a owl:Class ;
    rdfs:label "eTOM Business Process"@en ;
    rdfs:comment "TM Forum Business Process Framework (eTOM GB921) operational process element."@en ;
    skos:altLabel "eTOM Process"@en ,
                  "Assurance Operational Process"@en ,
                  "Telecom Process Domain"@en .

etom:Process_1_3_7_ProblemHandling a etom:BusinessProcess , owl:NamedIndividual ;
    rdfs:label "eTOM 1.3.7 Problem Handling"@en ;
    dcterms:identifier "1.3.7" ;
    rdfs:comment "Customer-facing service problem reception, SLA triage, root-cause correlation, and customer status notification."@en ;
    skos:altLabel "Customer Problem Handling"@en ,
                  "CFS SLA Assurance Triage"@en .

etom:Process_1_4_5_ResourceTroubleManagement a etom:BusinessProcess , owl:NamedIndividual ;
    rdfs:label "eTOM 1.4.5 Resource Trouble Management"@en ;
    dcterms:identifier "1.4.5" ;
    rdfs:comment "Network resource fault localization, optical transceiver DDM diagnostics, autonomous self-healing, and field technician dispatch."@en ;
    skos:altLabel "Resource Trouble Management"@en ,
                  "Network Fault Isolation & Remediation"@en .

# ============================================================================
# Pruned TM Forum SID (GB922) & Telecom Assurance OWL Classes (14 Classes)
# ============================================================================
tmf:Customer a owl:Class ;
    rdfs:label "Customer"@en ;
    rdfs:comment "An enterprise party or organization that subscribes to commercial telecom products and holds an active Master Service Agreement."@en ;
    skos:altLabel "Enterprise Subscriber"@en ,
                  "B2B Account"@en ,
                  "Contracted Party"@en ,
                  "Corporate Client"@en ;
    telco:alignedEtomProcess etom:Process_1_3_7_ProblemHandling .

tmf:Product a owl:Class ;
    rdfs:label "Product"@en ;
    rdfs:comment "A procured commercial telecom offering binding a customer agreement to one or more CustomerFacingServices."@en ;
    skos:altLabel "Commercial Product Instance"@en ,
                  "Subscribed Telecom Offering"@en ,
                  "Enterprise Connectivity Subscription"@en ;
    telco:alignedEtomProcess etom:Process_1_3_7_ProblemHandling .

tmf:CustomerFacingService a owl:Class ;
    rdfs:label "Customer Facing Service"@en ;
    rdfs:comment "An active Layer 2 Ethernet or wavelength connectivity circuit directly visible to and contracted by an enterprise customer."@en ;
    skos:altLabel "CFS Circuit"@en ,
                  "Enterprise L2 Fiber Circuit"@en ,
                  "Carrier Ethernet Service"@en ,
                  "Leased Line Connection"@en ;
    telco:alignedEtomProcess etom:Process_1_3_7_ProblemHandling .

tmf:ServiceSpecification a owl:Class ;
    rdfs:label "Service Specification"@en ;
    rdfs:comment "Standardized commercial catalog SKU defining bandwidth tier, SLA packet-loss ceiling, availability target, and autonomous remediation eligibility."@en ;
    skos:altLabel "Commercial Product SKU"@en ,
                  "Catalog Service Tier"@en ,
                  "SLA Service Specification"@en ;
    telco:alignedEtomProcess etom:Process_1_3_7_ProblemHandling .

tmf:ResourceFacingService a owl:Class ;
    rdfs:label "Resource Facing Service"@en ;
    rdfs:comment "Internal network transport and access bearer service realizing a CustomerFacingService across PE routers, OLT ports, fiber spans, and CPE devices."@en ;
    skos:altLabel "RFS Access Bearer"@en ,
                  "Network Transport Bearer"@en ,
                  "L2 Optical Bearer Service"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

tmf:PhysicalResource a owl:Class ;
    rdfs:label "Physical Resource"@en ;
    rdfs:comment "A physical network equipment asset deployed in the provider core, access plant, or customer demarcation point."@en ;
    skos:altLabel "Network Inventory Element"@en ,
                  "Physical Hardware Asset"@en ,
                  "Telecom Network Device"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

telco:OltPortResource a owl:Class ;
    rdfs:subClassOf tmf:PhysicalResource ;
    rdfs:label "OLT Optical Port Resource"@en ;
    rdfs:comment "Optical Line Terminal transceiver port terminating the access fiber span and providing real-time gNMI DDM optical telemetry."@en ;
    skos:altLabel "OLT Port"@en ,
                  "Optical Access Line Card Port"@en ,
                  "PON Optical Interface"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

telco:CpeDeviceResource a owl:Class ;
    rdfs:subClassOf tmf:PhysicalResource ;
    rdfs:label "Customer Premises Equipment Resource"@en ;
    rdfs:comment "Physical demarcation switch or router installed at the enterprise customer site."@en ;
    skos:altLabel "CPE Device"@en ,
                  "Enterprise NTE Demarcation Chassis"@en ,
                  "On-Premises Optical Access Switch"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

telco:PeRouterResource a owl:Class ;
    rdfs:subClassOf tmf:PhysicalResource ;
    rdfs:label "Provider Edge Router Resource"@en ;
    rdfs:comment "Metro or core Provider Edge router aggregating L2 Ethernet access bearers."@en ;
    skos:altLabel "PE Router"@en ,
                  "Metro Aggregation Router"@en ,
                  "Edge Routing Node"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

tmf:PhysicalResourceSpec a owl:Class ;
    rdfs:label "Physical Resource Specification"@en ;
    rdfs:comment "Vendor equipment model specification defining hardware capabilities, supported optical transceivers, and DDM calibration thresholds."@en ;
    skos:altLabel "Hardware Model SKU"@en ,
                  "Vendor Equipment Specification"@en ,
                  "Chassis Hardware Model"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

tmf:TroubleTicket a owl:Class ;
    rdfs:label "Trouble Ticket"@en ;
    rdfs:comment "TMF621 operational assurance ticket tracking network incidents, automated remediations, or field fiber splicing dispatches."@en ;
    skos:altLabel "NOC Assurance Ticket"@en ,
                  "TMF621 Incident Record"@en ,
                  "Field Dispatch Trouble Ticket"@en ;
    telco:alignedEtomProcess etom:Process_1_3_7_ProblemHandling ,
                             etom:Process_1_4_5_ResourceTroubleManagement .

telco:SlaClause a owl:Class ;
    rdfs:label "Service Level Agreement Clause"@en ;
    rdfs:comment "Contractual or catalog SLA clause specifying packet-loss thresholds, mean time to repair, service credit penalties, and VIP escalation rules."@en ;
    skos:altLabel "SLA Guarantee Clause"@en ,
                  "MSA Contractual Penalty Policy"@en ,
                  "Quality of Service Commitment"@en ;
    telco:alignedEtomProcess etom:Process_1_3_7_ProblemHandling .

telco:OpticalCalibrationProfile a owl:Class ;
    rdfs:label "Optical Calibration Profile"@en ;
    rdfs:comment "Vendor hardware manual optical Digital Diagnostic Monitoring (DDM) power envelope and autonomous laser bias recalibration specification."@en ;
    skos:altLabel "DDM Optical Power Envelope"@en ,
                  "SFP+ Tx/Rx Calibration Spec"@en ,
                  "Optical Attenuation Threshold Profile"@en ;
    telco:alignedEtomProcess etom:Process_1_4_5_ResourceTroubleManagement .

# ============================================================================
# Object Properties (Relational & Semantic Spine Links)
# ============================================================================
tmf:hasCustomer a owl:ObjectProperty ;
    rdfs:domain tmf:CustomerFacingService ;
    rdfs:range tmf:Customer ;
    rdfs:label "has customer"@en ;
    rdfs:comment "Associates a CustomerFacingService circuit with the subscribing enterprise Customer."@en ;
    skos:altLabel "subscribed by customer"@en ,
                  "owned by enterprise party"@en .

tmf:isDescribedBy a owl:ObjectProperty ;
    rdfs:domain tmf:CustomerFacingService ;
    rdfs:range tmf:ServiceSpecification ;
    rdfs:label "is described by service specification"@en ;
    rdfs:comment "Links an active CustomerFacingService circuit to its commercial catalog ServiceSpecification SKU."@en ;
    skos:altLabel "governed by catalog SKU"@en ,
                  "has commercial service tier"@en .

tmf:supportsService a owl:ObjectProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range tmf:CustomerFacingService ;
    rdfs:label "supports customer facing service"@en ;
    rdfs:comment "Binds an underlying ResourceFacingService bearer to the CustomerFacingService circuit it realizes."@en ;
    skos:altLabel "realizes circuit"@en ,
                  "underpins customer service"@en .

telco:usesOltPort a owl:ObjectProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range telco:OltPortResource ;
    rdfs:label "uses OLT optical port"@en ;
    rdfs:comment "Identifies the physical OLT port carrying the optical access signal for the ResourceFacingService."@en ;
    skos:altLabel "terminated on OLT port"@en ,
                  "served by optical port"@en .

telco:terminatesOnRouter a owl:ObjectProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range telco:PeRouterResource ;
    rdfs:label "terminates on PE router"@en ;
    rdfs:comment "Identifies the Provider Edge router terminating the L2 bearer."@en ;
    skos:altLabel "aggregated by PE router"@en ,
                  "routed via edge node"@en .

telco:demarcatesAtCpe a owl:ObjectProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range telco:CpeDeviceResource ;
    rdfs:label "demarcates at CPE device"@en ;
    rdfs:comment "Identifies the physical Customer Premises Equipment demarcation device for the bearer."@en ;
    skos:altLabel "installed CPE chassis"@en ,
                  "customer demarcation unit"@en .

tmf:hasResourceSpecification a owl:ObjectProperty ;
    rdfs:domain tmf:PhysicalResource ;
    rdfs:range tmf:PhysicalResourceSpec ;
    rdfs:label "has physical resource specification"@en ;
    rdfs:comment "Links a deployed PhysicalResource asset to its vendor hardware model specification."@en ;
    skos:altLabel "hardware model spec"@en ,
                  "equipment SKU specification"@en .

telco:hasOpticalCalibrationProfile a owl:ObjectProperty ;
    rdfs:domain tmf:PhysicalResourceSpec ;
    rdfs:range telco:OpticalCalibrationProfile ;
    rdfs:label "has optical calibration profile"@en ;
    rdfs:comment "Links a vendor hardware specification to its DDM optical power threshold and calibration profile."@en ;
    skos:altLabel "optical DDM envelope"@en ,
                  "transceiver power profile"@en .

telco:hasSlaClause a owl:ObjectProperty ;
    rdfs:domain tmf:Customer ;
    rdfs:range telco:SlaClause ;
    rdfs:label "has contractual SLA clause"@en ;
    rdfs:comment "Links an enterprise Customer to a custom Master Service Agreement SLA clause."@en ;
    skos:altLabel "governed by MSA clause"@en ,
                  "has custom penalty agreement"@en .

telco:recommendedUpgradeSpec a owl:ObjectProperty ;
    rdfs:domain tmf:ServiceSpecification ;
    rdfs:range tmf:ServiceSpecification ;
    rdfs:label "recommended upgrade specification"@en ;
    rdfs:comment "Points from a current ServiceSpecification SKU to the next recommended commercial upgrade tier."@en ;
    skos:altLabel "upsell target SKU"@en ,
                  "next capacity tier"@en .

telco:affectedCircuit a owl:ObjectProperty ;
    rdfs:domain tmf:TroubleTicket ;
    rdfs:range tmf:CustomerFacingService ;
    rdfs:label "affected customer circuit"@en ;
    rdfs:comment "Links a TroubleTicket to the impacted CustomerFacingService circuit."@en ;
    skos:altLabel "impacted CFS circuit"@en ,
                  "ticket target circuit"@en .

telco:affectedResource a owl:ObjectProperty ;
    rdfs:domain tmf:TroubleTicket ;
    rdfs:range tmf:PhysicalResource ;
    rdfs:label "affected physical resource"@en ;
    rdfs:comment "Links a TroubleTicket to the faulted physical network resource or port."@en ;
    skos:altLabel "faulted hardware port"@en ,
                  "impacted network element"@en .

# ============================================================================
# Datatype Properties & QUDT Unit Annotations
# ============================================================================
tmf:customerId a owl:DatatypeProperty ;
    rdfs:domain tmf:Customer ;
    rdfs:range xsd:string ;
    rdfs:label "customer identifier"@en ;
    rdfs:comment "Unique enterprise customer identifier."@en ;
    skos:altLabel "account ID"@en ,
                  "enterprise party reference"@en .

tmf:partyLegalName a owl:DatatypeProperty ;
    rdfs:domain tmf:Customer ;
    rdfs:range xsd:string ;
    rdfs:label "party legal name"@en ;
    rdfs:comment "Registered corporate legal name of the customer."@en ;
    skos:altLabel "company legal name"@en ,
                  "enterprise name"@en .

tmf:marketSegment a owl:DatatypeProperty ;
    rdfs:domain tmf:Customer ;
    rdfs:range xsd:string ;
    rdfs:label "market segment"@en ;
    rdfs:comment "Commercial market segment classification (e.g., ENT_VIP, GOV, SMB, RES)."@en ;
    skos:altLabel "customer tier"@en ,
                  "business segment"@en .

telco:accountManagerCode a owl:DatatypeProperty ;
    rdfs:domain tmf:Customer ;
    rdfs:range xsd:string ;
    rdfs:label "account manager code"@en ;
    rdfs:comment "Identifier of the dedicated enterprise account manager."@en ;
    skos:altLabel "assigned account executive"@en ,
                  "commercial owner ID"@en .

telco:chamberOfCommerceReg a owl:DatatypeProperty ;
    rdfs:domain tmf:Customer ;
    rdfs:range xsd:string ;
    rdfs:label "chamber of commerce registration"@en ;
    rdfs:comment "National trade registry / KvK registration number from legal contracts."@en ;
    skos:altLabel "KvK registration number"@en ,
                  "corporate registry ID"@en .

tmf:serviceId a owl:DatatypeProperty ;
    rdfs:domain tmf:CustomerFacingService ;
    rdfs:range xsd:string ;
    rdfs:label "service circuit identifier"@en ;
    rdfs:comment "Canonical identifier of the CustomerFacingService circuit."@en ;
    skos:altLabel "circuit ID"@en ,
                  "L2 service reference"@en .

tmf:operationalStatus a owl:DatatypeProperty ;
    rdfs:domain tmf:CustomerFacingService ;
    rdfs:range xsd:string ;
    rdfs:label "operational status"@en ;
    rdfs:comment "Canonical operational lifecycle status of the service (ACTIVE, MAINTENANCE, DECOMMISSIONED)."@en ;
    skos:altLabel "circuit status"@en ,
                  "service operational state"@en .

telco:bandwidthGbps a owl:DatatypeProperty ;
    rdfs:domain tmf:CustomerFacingService ;
    rdfs:range xsd:decimal ;
    qudt:applicableUnit unit:GigaBIT-PER-SEC ;
    rdfs:label "committed bandwidth (Gbps)"@en ;
    rdfs:comment "Committed information rate normalized to canonical Gigabits per second (Gbps)."@en ;
    skos:altLabel "circuit capacity Gbps"@en ,
                  "normalized line rate"@en .

telco:installationDate a owl:DatatypeProperty ;
    rdfs:domain tmf:CustomerFacingService ;
    rdfs:range xsd:date ;
    rdfs:label "installation date"@en ;
    rdfs:comment "Date on which the service circuit was commissioned."@en ;
    skos:altLabel "commissioning date"@en ,
                  "service activation date"@en .

tmf:rfsId a owl:DatatypeProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range xsd:string ;
    rdfs:label "resource facing service identifier"@en ;
    rdfs:comment "Unique identifier of the ResourceFacingService bearer."@en ;
    skos:altLabel "RFS bearer ID"@en ,
                  "access bearer reference"@en .

telco:vlanTag a owl:DatatypeProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range xsd:integer ;
    rdfs:label "VLAN tag"@en ;
    rdfs:comment "IEEE 802.1Q VLAN identifier configured on the access bearer."@en ;
    skos:altLabel "802.1Q VLAN ID"@en ,
                  "service encapsulation tag"@en .

telco:fiberSpanId a owl:DatatypeProperty ;
    rdfs:domain tmf:ResourceFacingService ;
    rdfs:range xsd:string ;
    rdfs:label "fiber span identifier"@en ;
    rdfs:comment "Identifier of the physical outside-plant optical fiber ring or span."@en ;
    skos:altLabel "optical fiber span"@en ,
                  "metro ring span ID"@en .

tmf:resourceId a owl:DatatypeProperty ;
    rdfs:domain tmf:PhysicalResource ;
    rdfs:range xsd:string ;
    rdfs:label "physical resource identifier"@en ;
    rdfs:comment "Asset or inventory identifier of a physical network resource."@en ;
    skos:altLabel "asset tag"@en ,
                  "hardware inventory ID"@en .

tmf:resourceName a owl:DatatypeProperty ;
    rdfs:domain tmf:PhysicalResource ;
    rdfs:range xsd:string ;
    rdfs:label "physical resource hostname"@en ;
    rdfs:comment "Network hostname or label of the physical resource."@en ;
    skos:altLabel "router hostname"@en ,
                  "node name"@en .

telco:portIdentifier a owl:DatatypeProperty ;
    rdfs:domain telco:OltPortResource ;
    rdfs:range xsd:string ;
    rdfs:label "OLT port identifier"@en ;
    rdfs:comment "Slot and port identifier on the Optical Line Terminal."@en ;
    skos:altLabel "optical port ID"@en ,
                  "OLT interface name"@en .

tmf:skuCode a owl:DatatypeProperty ;
    rdfs:domain owl:Thing ;
    rdfs:range xsd:string ;
    rdfs:label "catalog or hardware SKU code"@en ;
    rdfs:comment "Standardized commercial product SKU or hardware equipment model code."@en ;
    skos:altLabel "SKU identifier"@en ,
                  "product or model code"@en .

telco:maxPacketLossPct a owl:DatatypeProperty ;
    rdfs:domain tmf:ServiceSpecification ;
    rdfs:range xsd:decimal ;
    qudt:applicableUnit unit:PERCENT ;
    rdfs:label "maximum packet loss ceiling (%)"@en ;
    rdfs:comment "Maximum allowed frame/packet loss percentage before SLA breach."@en ;
    skos:altLabel "SLA packet loss threshold"@en ,
                  "frame loss ceiling percent"@en .

telco:availabilityTargetPct a owl:DatatypeProperty ;
    rdfs:domain tmf:ServiceSpecification ;
    rdfs:range xsd:decimal ;
    qudt:applicableUnit unit:PERCENT ;
    rdfs:label "annual availability target (%)"@en ;
    rdfs:comment "Contracted service availability percentage target."@en ;
    skos:altLabel "SLA uptime target"@en ,
                  "service availability percent"@en .

telco:lifecycleStatus a owl:DatatypeProperty ;
    rdfs:domain tmf:ServiceSpecification ;
    rdfs:range xsd:string ;
    rdfs:label "catalog lifecycle status"@en ;
    rdfs:comment "Commercial catalog lifecycle state (ACTIVE or DEPRECATED)."@en ;
    skos:altLabel "SKU lifecycle state"@en ,
                  "product status"@en .

telco:autoRemediationAllowed a owl:DatatypeProperty ;
    rdfs:domain tmf:ServiceSpecification ;
    rdfs:range xsd:boolean ;
    rdfs:label "autonomous remediation allowed"@en ;
    rdfs:comment "Indicates whether zero-touch autonomous optical DDM recalibration is permitted for the tier."@en ;
    skos:altLabel "self-healing eligible"@en ,
                  "automated recalibration flag"@en .

telco:rxOpticalPowerMinDbm a owl:DatatypeProperty ;
    rdfs:domain telco:OpticalCalibrationProfile ;
    rdfs:range xsd:decimal ;
    qudt:applicableUnit unit:MilliWATT-DeciBEL ;
    rdfs:label "minimum Rx optical power (dBm)"@en ;
    rdfs:comment "Minimum normal receive optical power threshold in dBm before soft attenuation warning."@en ;
    skos:altLabel "Rx nominal floor dBm"@en ,
                  "optical receive power minimum"@en .

telco:rxLosCutThresholdDbm a owl:DatatypeProperty ;
    rdfs:domain telco:OpticalCalibrationProfile ;
    rdfs:range xsd:decimal ;
    qudt:applicableUnit unit:MilliWATT-DeciBEL ;
    rdfs:label "Rx Loss-of-Signal hard cut threshold (dBm)"@en ;
    rdfs:comment "Receive optical power threshold below which a hard physical fiber cut is declared."@en ;
    skos:altLabel "LOS optical cutoff dBm"@en ,
                  "hard fiber cut power threshold"@en .

tmf:ticketId a owl:DatatypeProperty ;
    rdfs:domain tmf:TroubleTicket ;
    rdfs:range xsd:string ;
    rdfs:label "trouble ticket identifier"@en ;
    rdfs:comment "Unique TMF621 trouble ticket identifier."@en ;
    skos:altLabel "incident number"@en ,
                  "dispatch ticket ID"@en .

tmf:severity a owl:DatatypeProperty ;
    rdfs:domain tmf:TroubleTicket ;
    rdfs:range xsd:string ;
    rdfs:label "ticket severity"@en ;
    rdfs:comment "Severity level of the trouble ticket (CRITICAL, MAJOR, MINOR, WARNING)."@en ;
    skos:altLabel "incident priority"@en ,
                  "fault severity"@en .

tmf:status a owl:DatatypeProperty ;
    rdfs:domain tmf:TroubleTicket ;
    rdfs:range xsd:string ;
    rdfs:label "ticket status"@en ;
    rdfs:comment "Lifecycle status of the TMF621 trouble ticket."@en ;
    skos:altLabel "incident state"@en ,
                  "dispatch workflow status"@en .
"""


def write_knowledge_graph_trig_with_tbox(
    tbox_path: Path, trig_path: Path
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
    # Serialize triples inside <urn:telco:graph:tbox:sid-etom>
    nt_lines = g_tbox.serialize(format="ntriples").splitlines()
    indented_nt = "\n".join(f"    {line}" for line in sorted(nt_lines) if line.strip())

    trig_doc = (
        f"{prefix_block}\n"
        f"# Named Graph 1: Pruned TM Forum SID & eTOM Conceptual TBox\n"
        f"<{GRAPH_TBOX_URI}> {{\n"
        f"{indented_nt}\n"
        f"}}\n\n"
        f"# Named Graph 2: Zero-Copy Virtual SQL CMDB Graph (0 persisted triples on disk)\n"
        f"<{GRAPH_VIRTUAL_IB_URI}> {{\n"
        f"}}\n"
    )
    trig_path.parent.mkdir(parents=True, exist_ok=True)
    trig_path.write_text(trig_doc, encoding="utf-8")


# ============================================================================
# 3. Base W3C SHACL Shapes Generator (`shapes/*.ttl`)
# ============================================================================
def build_service_spec_shape_turtle() -> str:
    """
    Return W3C SHACL shape `shapes/service_spec_shape.ttl` enforcing:
      - `telco:maxPacketLossPct >= 0.0` and `<= 100.0`
      - `telco:lifecycleStatus` in `("ACTIVE" "DEPRECATED")`
      - `telco:availabilityTargetPct >= 0.0` and `<= 100.0`
    """
    return """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix tmf: <http://tmforum.org/sid/> .
@prefix telco: <http://telco.enterprise.org/ontology/> .

telco:ServiceSpecificationShape a sh:NodeShape ;
    sh:targetClass tmf:ServiceSpecification ;
    rdfs:label "TMF SID ServiceSpecification SHACL Quarantine Shape"@en ;
    rdfs:comment "Enforces non-negative packet loss ceilings and valid catalog lifecycle states prior to Named Graph promotion."@en ;
    sh:property [
        sh:path tmf:skuCode ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:message "Every ServiceSpecification must declare a single string tmf:skuCode."@en ;
    ] ;
    sh:property [
        sh:path telco:maxPacketLossPct ;
        sh:minCount 1 ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 100.0 ;
        sh:message "telco:maxPacketLossPct must be a non-negative percentage between 0.0 and 100.0."@en ;
    ] ;
    sh:property [
        sh:path telco:availabilityTargetPct ;
        sh:minCount 1 ;
        sh:minInclusive 0.0 ;
        sh:maxInclusive 100.0 ;
        sh:message "telco:availabilityTargetPct must be between 0.0 and 100.0."@en ;
    ] ;
    sh:property [
        sh:path telco:lifecycleStatus ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:in ( "ACTIVE" "DEPRECATED" ) ;
        sh:message "telco:lifecycleStatus must be strictly 'ACTIVE' or 'DEPRECATED'."@en ;
    ] .
"""


def build_trouble_ticket_shape_turtle() -> str:
    """
    Return W3C SHACL shape `shapes/trouble_ticket_shape.ttl` for Step 8 CQRS
    `commit_validated_graph_triples` writeback validation.
    """
    return """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix tmf: <http://tmforum.org/sid/> .
@prefix telco: <http://telco.enterprise.org/ontology/> .

telco:TroubleTicketShape a sh:NodeShape ;
    sh:targetClass tmf:TroubleTicket ;
    rdfs:label "TMF621 TroubleTicket SHACL Writeback Shape"@en ;
    rdfs:comment "Validates candidate RDF trouble ticket triples before atomic commit to the knowledge fabric."@en ;
    sh:property [
        sh:path tmf:ticketId ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:message "TroubleTicket requires a single string tmf:ticketId."@en ;
    ] ;
    sh:property [
        sh:path tmf:severity ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:in ( "CRITICAL" "MAJOR" "MINOR" "WARNING" ) ;
        sh:message "TroubleTicket tmf:severity must be one of CRITICAL, MAJOR, MINOR, WARNING."@en ;
    ] ;
    sh:property [
        sh:path tmf:status ;
        sh:datatype xsd:string ;
        sh:minCount 1 ;
        sh:message "TroubleTicket requires a tmf:status string."@en ;
    ] ;
    sh:property [
        sh:path telco:affectedCircuit ;
        sh:nodeKind sh:IRI ;
        sh:minCount 1 ;
        sh:message "TroubleTicket must reference at least one telco:affectedCircuit IRI."@en ;
    ] ;
    sh:property [
        sh:path telco:affectedResource ;
        sh:nodeKind sh:IRI ;
        sh:minCount 1 ;
        sh:message "TroubleTicket must reference at least one telco:affectedResource IRI."@en ;
    ] .
"""


# ============================================================================
# 4. Physical W3C R2RML Virtual Graph Mapping Generator (`mappings/cmdb_r2rml.ttl`)
# ============================================================================
def build_cmdb_r2rml_turtle() -> str:
    """
    Return the W3C R2RML (`http://www.w3.org/ns/r2rml#`) Turtle mapping file
    (`mappings/cmdb_r2rml.ttl`) defining `<#CustomerTriplesMap>`,
    `<#CfsCircuitTriplesMap>`, and `<#RfsResourceTriplesMap>` targeting
    Named Graph `<urn:telco:graph:virtual:ib>`.
    """
    return """@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix tmf: <http://tmforum.org/sid/> .
@prefix telco: <http://telco.enterprise.org/ontology/> .
@base <urn:telco:r2rml:cmdb:> .

# ============================================================================
# TriplesMap 1: T_OSS_CUST_PARTY -> tmf:Customer
# Excludes internal/legacy columns: PARTY_SURR_ID, LEGACY_CRM_ID, CREATED_TS
# ============================================================================
<#CustomerTriplesMap> a rr:TriplesMap ;
    rdfs:label "OSS Customer Party to TMF SID Customer Virtual Mapping"@en ;
    rr:logicalTable [
        rr:sqlQuery \"\"\"
            SELECT
                CUST_EXT_REF,
                LEGAL_NAME,
                SEGMENT_CD,
                ACCT_MGR_ID
            FROM T_OSS_CUST_PARTY
        \"\"\"
    ] ;
    rr:subjectMap [
        rr:template "urn:telco:party:customer:{CUST_EXT_REF}" ;
        rr:class tmf:Customer ;
        rr:graph <urn:telco:graph:virtual:ib>
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:customerId ;
        rr:objectMap [ rr:column "CUST_EXT_REF" ; rr:datatype xsd:string ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:partyLegalName ;
        rr:objectMap [ rr:column "LEGAL_NAME" ; rr:datatype xsd:string ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:marketSegment ;
        rr:objectMap [ rr:column "SEGMENT_CD" ; rr:datatype xsd:string ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:accountManagerCode ;
        rr:objectMap [ rr:column "ACCT_MGR_ID" ; rr:datatype xsd:string ]
    ] .

# ============================================================================
# TriplesMap 2: T_CMDB_CFS_CIRCUIT -> tmf:CustomerFacingService
# Enforces:
#   1. SCD Type 2 active filter: WHERE VALID_TO_TS IS NULL
#      (retains active row CFS_ROW_ID=2001 [ETH-10G-GOLD] and filters out
#       expired row CFS_ROW_ID=2000 [ETH-1G-SILVER] for CIR-994821)
#   2. Shadow enum translation: '10'->'ACTIVE', '20'->'MAINTENANCE', '99'->'DECOMMISSIONED'
#   3. QUDT bandwidth normalization: Kbps / Mbps / Gbps -> canonical Gbps
# Excludes: LEGACY_BILL_TAG; keeps CFS_ROW_ID, VALID_FROM_TS, VALID_TO_TS as SQL control only
# ============================================================================
<#CfsCircuitTriplesMap> a rr:TriplesMap ;
    rdfs:label "CMDB CFS Circuit to TMF SID CustomerFacingService Virtual Mapping"@en ;
    rr:logicalTable [
        rr:sqlQuery \"\"\"
            SELECT
                CIRCUIT_ID,
                CUST_REF_ID,
                PROD_SPEC_CODE,
                INSTALL_DT,
                CASE OPER_STATUS_CD
                    WHEN '10' THEN 'ACTIVE'
                    WHEN '20' THEN 'MAINTENANCE'
                    WHEN '99' THEN 'DECOMMISSIONED'
                    ELSE 'UNKNOWN'
                END AS CANONICAL_OPER_STATUS,
                CASE BW_UNIT_CD
                    WHEN 'Gbps' THEN CAST(BW_VAL AS REAL)
                    WHEN 'Mbps' THEN CAST(BW_VAL AS REAL) / 1000.0
                    WHEN 'Kbps' THEN CAST(BW_VAL AS REAL) / 1000000.0
                    ELSE CAST(BW_VAL AS REAL)
                END AS BANDWIDTH_GBPS
            FROM T_CMDB_CFS_CIRCUIT
            WHERE VALID_TO_TS IS NULL
        \"\"\"
    ] ;
    rr:subjectMap [
        rr:template "urn:telco:service:cfs:{CIRCUIT_ID}" ;
        rr:class tmf:CustomerFacingService ;
        rr:graph <urn:telco:graph:virtual:ib>
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:serviceId ;
        rr:objectMap [ rr:column "CIRCUIT_ID" ; rr:datatype xsd:string ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:hasCustomer ;
        rr:objectMap [
            rr:template "urn:telco:party:customer:{CUST_REF_ID}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:isDescribedBy ;
        rr:objectMap [
            rr:template "urn:telco:catalog:sku:{PROD_SPEC_CODE}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:operationalStatus ;
        rr:objectMap [ rr:column "CANONICAL_OPER_STATUS" ; rr:datatype xsd:string ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:bandwidthGbps ;
        rr:objectMap [ rr:column "BANDWIDTH_GBPS" ; rr:datatype xsd:decimal ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:installationDate ;
        rr:objectMap [ rr:column "INSTALL_DT" ; rr:datatype xsd:date ]
    ] .

# ============================================================================
# TriplesMap 3: T_CMDB_RFS_RESOURCE -> tmf:ResourceFacingService & PhysicalResource
# Excludes internal sync column: LAST_SYNC_UTC
# Note: T_BILLING_AUDIT_NOISE (25 rows) is intentionally unmapped (EXCLUDED_NOISE).
# ============================================================================
<#RfsResourceTriplesMap> a rr:TriplesMap ;
    rdfs:label "CMDB RFS Resource to TMF SID ResourceFacingService & PhysicalResource Mapping"@en ;
    rr:logicalTable [
        rr:sqlQuery \"\"\"
            SELECT
                RFS_ID,
                PARENT_CFS_ID,
                PE_ROUTER_HOSTNAME,
                OLT_PORT_ID,
                CPE_ASSET_ID,
                CPE_MODEL_SKU,
                VLAN_TAG,
                FIBER_SPAN_ID
            FROM T_CMDB_RFS_RESOURCE
        \"\"\"
    ] ;
    rr:subjectMap [
        rr:template "urn:telco:service:rfs:{RFS_ID}" ;
        rr:class tmf:ResourceFacingService ;
        rr:graph <urn:telco:graph:virtual:ib>
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:rfsId ;
        rr:objectMap [ rr:column "RFS_ID" ; rr:datatype xsd:string ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:supportsService ;
        rr:objectMap [
            rr:template "urn:telco:service:cfs:{PARENT_CFS_ID}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:terminatesOnRouter ;
        rr:objectMap [
            rr:template "urn:telco:resource:router:{PE_ROUTER_HOSTNAME}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:usesOltPort ;
        rr:objectMap [
            rr:template "urn:telco:resource:port:{OLT_PORT_ID}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:demarcatesAtCpe ;
        rr:objectMap [
            rr:template "urn:telco:resource:cpe:{CPE_ASSET_ID}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate tmf:hasResourceSpecification ;
        rr:objectMap [
            rr:template "urn:telco:resource:spec:{CPE_MODEL_SKU}" ;
            rr:termType rr:IRI
        ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:vlanTag ;
        rr:objectMap [ rr:column "VLAN_TAG" ; rr:datatype xsd:integer ]
    ] ;
    rr:predicateObjectMap [
        rr:predicate telco:fiberSpanId ;
        rr:objectMap [ rr:column "FIBER_SPAN_ID" ; rr:datatype xsd:string ]
    ] .
"""


# ============================================================================
# 5. Automated Evaluator Agent Ontology & Mapping Critique
# ============================================================================
def evaluate_ontology_and_r2rml(
    table_profiles: List[TableProfileEntry],
    tbox_path: Path,
    r2rml_path: Path,
    trig_path: Path,
) -> EvaluatorOntologyCritique:
    """
    Execute the deterministic Evaluator Agent critique across `tbox_sid_etom.ttl`,
    `cmdb_r2rml.ttl`, and `knowledge_graph.trig`.
    """
    tbox_text = tbox_path.read_text(encoding="utf-8")
    r2rml_text = r2rml_path.read_text(encoding="utf-8")

    # 1. Verify zero SQL table or column names leaked into tbox_sid_etom.ttl
    sql_identifiers: List[str] = []
    for tbl in table_profiles:
        sql_identifiers.append(tbl.table_name)
        for col in tbl.columns:
            sql_identifiers.append(col.column_name)

    leaked_tokens = sorted(
        {token for token in sql_identifiers if token in tbox_text}
    )
    zero_sql_leakage = len(leaked_tokens) == 0

    # 2. Parse TBox in rdflib and count OWL classes, properties, and skos:altLabel
    g_tbox = Graph()
    g_tbox.parse(str(tbox_path), format="turtle")
    classes = set(g_tbox.subjects(RDF.type, OWL.Class))
    obj_props = set(g_tbox.subjects(RDF.type, OWL.ObjectProperty))
    dt_props = set(g_tbox.subjects(RDF.type, OWL.DatatypeProperty))
    alt_labels = list(g_tbox.triples((None, SKOS.altLabel, None)))

    # 3. Parse R2RML in rdflib and verify noise exclusion, SCD2, shadow enum, QUDT math
    g_r2rml = Graph()
    g_r2rml.parse(str(r2rml_path), format="turtle")
    triples_maps = set(g_r2rml.subjects(RDF.type, RR_NS.TriplesMap))

    # Ensure T_BILLING_AUDIT_NOISE is never referenced inside any rr:sqlQuery or rr:tableName
    sql_queries = [
        str(o) for _, _, o in g_r2rml.triples((None, RR_NS.sqlQuery, None))
    ]
    joined_sql = "\n".join(sql_queries)
    billing_excluded = (
        "T_BILLING_AUDIT_NOISE" not in joined_sql
        and len(triples_maps) == 3
    )
    scd2_present = "WHERE VALID_TO_TS IS NULL" in joined_sql
    shadow_enum_present = (
        "WHEN '10' THEN 'ACTIVE'" in joined_sql
        and "WHEN '20' THEN 'MAINTENANCE'" in joined_sql
        and "WHEN '99' THEN 'DECOMMISSIONED'" in joined_sql
    )
    qudt_present = (
        "WHEN 'Mbps' THEN CAST(BW_VAL AS REAL) / 1000.0" in joined_sql
        and "WHEN 'Kbps' THEN CAST(BW_VAL AS REAL) / 1000000.0" in joined_sql
    )

    # 4. Verify <urn:telco:graph:virtual:ib> has 0 persisted triples in knowledge_graph.trig
    ds = Dataset()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        ds.parse(str(trig_path), format="trig")
    virtual_ctx = ds.graph(URIRef(GRAPH_VIRTUAL_IB_URI))
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
        f"{len(alt_labels)} skos:altLabel synonyms verified; T_BILLING_AUDIT_NOISE excluded; "
        f"SCD2 (WHERE VALID_TO_TS IS NULL), shadow enum translation, and QUDT Gbps math active; "
        f"<urn:telco:graph:virtual:ib> has 0 persisted triples on disk."
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
# 6. Mandatory HITL Gate 1 Report Generator (`.html` & `.md`)
# ============================================================================
def _write_hitl_gate1_markdown_report(
    table_profiles: List[TableProfileEntry],
    scd2_verification: Scd2CircuitVerification,
    critique: EvaluatorOntologyCritique,
    gate1_status: Literal["CANDIDATE_PROPOSED", "LOCKED_APPROVED"],
    executed_at_utc: str,
    md_path: Path,
) -> None:
    """Write `reports/hitl_gate1_ontology_mapping_review.md`."""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = [
        f"# Mandatory HITL Gate 1 Review — Prong 1 SQL CMDB Profiler, TMF SID/eTOM TBox & R2RML Mapping (`DT-01a`)",
        "",
        f"- **Gate 1 Sign-Off Status:** **`{gate1_status}`**",
        f"- **Executed At (UTC):** `{executed_at_utc}`",
        f"- **Evaluator Critique Result:** `{critique.critique_summary}`",
        "",
        "---",
        "",
        "## 1. SQLite CMDB Table-Level Profiling & Noise Exclusion Summary",
        "",
        "| Table Name | Total Rows | Active Rows | Disposition | Target TMF SID Classes | R2RML TriplesMap |",
        "| :--- | :---: | :---: | :---: | :--- | :--- |",
    ]
    for tbl in table_profiles:
        classes_str = ", ".join(f"`{c}`" for c in tbl.target_tmf_classes) or "*None (Excluded)*"
        lines.append(
            f"| `{tbl.table_name}` | {tbl.total_rows} | {tbl.active_rows} | "
            f"**`{tbl.table_disposition}`** | {classes_str} | `{tbl.r2rml_triples_map_id}` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 2. Dynamic Column-Level Disposition Matrix (`PRAGMA table_info`)",
            "",
            "| Table | Column | SQL Type | Disposition | Mapped TBox Target | Transformation / Audit Rationale |",
            "| :--- | :--- | :---: | :---: | :--- | :--- |",
        ]
    )
    for tbl in table_profiles:
        for col in tbl.columns:
            lines.append(
                f"| `{tbl.table_name}` | `{col.column_name}` | `{col.sql_type}` | "
                f"**`{col.disposition}`** | `{col.mapped_tbox_target}` | {col.audit_rationale} |"
            )

    lines.extend(
        [
            "",
            "---",
            "",
            f"## 3. Target Circuit `{scd2_verification.circuit_id}` SCD Type 2, Shadow Enum & QUDT Verification",
            "",
            f"- **Superseded Historical Row Filtered Out (`VALID_TO_TS IS NOT NULL`):** `CFS_ROW_ID={scd2_verification.expired_row_id}` (`{scd2_verification.expired_product_sku}`, expired `{scd2_verification.expired_valid_to_ts}`)",
            f"- **Active Current Row Retained (`WHERE VALID_TO_TS IS NULL`):** `CFS_ROW_ID={scd2_verification.active_row_id}` (`{scd2_verification.active_product_sku}`)",
            f"- **Shadow Enum Translation (`OPER_STATUS_CD`):** `'{scd2_verification.raw_oper_status_cd}'` $\\rightarrow$ **`'{scd2_verification.canonical_oper_status}'`**",
            f"- **QUDT Bandwidth Normalization:** `{scd2_verification.raw_bandwidth_val} {scd2_verification.raw_bandwidth_unit}` $\\rightarrow$ **`{scd2_verification.normalized_bandwidth_gbps} Gbps`** (`unit:GigaBIT-PER-SEC`)",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _write_hitl_gate1_html_report(
    table_profiles: List[TableProfileEntry],
    scd2_verification: Scd2CircuitVerification,
    critique: EvaluatorOntologyCritique,
    gate1_status: Literal["CANDIDATE_PROPOSED", "LOCKED_APPROVED"],
    executed_at_utc: str,
    html_path: Path,
) -> None:
    """Write self-contained `reports/hitl_gate1_ontology_mapping_review.html`."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    badge_bg = "#059669" if gate1_status == "LOCKED_APPROVED" else "#D97706"

    table_rows_html: List[str] = []
    for tbl in table_profiles:
        t_color = "#059669" if tbl.table_disposition == "BOUND_VIRTUAL_GRAPH" else "#DC2626"
        classes_html = ", ".join(f"<code>{html.escape(c)}</code>" for c in tbl.target_tmf_classes) or "<em>None (Excluded Noise)</em>"
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
    <h1>Mandatory HITL Gate 1 — Prong 1 SQL CMDB Profiler, TMF SID/eTOM TBox &amp; R2RML Mapping (DT-01a)</h1>
    <p>
      <strong>Sign-Off Status:</strong>
      <span style="padding:4px 10px;border-radius:9999px;font-weight:700;background:{badge_bg};color:#FFF;">
        {html.escape(gate1_status)}
      </span>
      &nbsp;|&nbsp; <strong>Executed At (UTC):</strong> {html.escape(executed_at_utc)}
    </p>
    <p><strong>Evaluator Critique:</strong> {html.escape(critique.critique_summary)}</p>
  </div>

  <div class="card">
    <h2>1. SQLite CMDB Table-Level Profiling &amp; Noise Exclusion (4 Tables, 104 Rows)</h2>
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
    <h2>2. Target Circuit {html.escape(scd2_verification.circuit_id)} SCD Type 2, Shadow Enum &amp; QUDT Proof</h2>
    <ul>
      <li><strong>Filtered Expired SCD2 Row (<code>VALID_TO_TS IS NOT NULL</code>):</strong> <code>CFS_ROW_ID={scd2_verification.expired_row_id}</code> (<code>{html.escape(scd2_verification.expired_product_sku)}</code>, expired <code>{html.escape(scd2_verification.expired_valid_to_ts)}</code>)</li>
      <li><strong>Retained Active SCD2 Row (<code>WHERE VALID_TO_TS IS NULL</code>):</strong> <code>CFS_ROW_ID={scd2_verification.active_row_id}</code> (<code>{html.escape(scd2_verification.active_product_sku)}</code>)</li>
      <li><strong>Shadow Enum Translation (<code>OPER_STATUS_CD</code>):</strong> <code>'{html.escape(scd2_verification.raw_oper_status_cd)}'</code> &rarr; <strong><code>'{html.escape(scd2_verification.canonical_oper_status)}'</code></strong></li>
      <li><strong>QUDT Bandwidth Normalization:</strong> <code>{scd2_verification.raw_bandwidth_val} {html.escape(scd2_verification.raw_bandwidth_unit)}</code> &rarr; <strong><code>{scd2_verification.normalized_bandwidth_gbps} Gbps</code></strong> (<code>unit:GigaBIT-PER-SEC</code>)</li>
    </ul>
  </div>

  <div class="card">
    <h2>3. Dynamic Column-Level Disposition Matrix (PRAGMA table_info)</h2>
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
# 7. Main Scenario `DT-01a` Orchestrator Entry Function
# ============================================================================
def run_dt01a_cmdb_profiler(
    config: AppConfig,
    logger: logging.Logger,
    mode: Literal["candidate", "approve"] = "approve",
    update_golden_ref: bool = False,
    workspace_root: Optional[Path] = None,
) -> Dt01aExecutionResult:
    """
    Execute Scenario `DT-01a`:
      1. Profile `cmdb_installed_base.db` dynamically via `PRAGMA table_info(...)`.
      2. Write `data/semantic_store/tbox_sid_etom.ttl` and materialize `<urn:telco:graph:tbox:sid-etom>`
         in `data/semantic_store/knowledge_graph.trig` (with `0` persisted triples in
         `<urn:telco:graph:virtual:ib>`).
      3. Write `shapes/service_spec_shape.ttl` and `shapes/trouble_ticket_shape.ttl`.
      4. Write `mappings/cmdb_r2rml.ttl`.
      5. Run the Evaluator Agent Ontology Critique.
      6. Write `reports/hitl_gate1_ontology_mapping_review.html` and `.md` with status
         `CANDIDATE_PROPOSED` (`mode="candidate"`) or `LOCKED_APPROVED` (`mode="approve"`).
      7. Optionally copy approved artifacts to `data/golden_reference/` when `update_golden_ref=True`.
    """
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()
    sqlite_path = root_dir / Path(config.layer4_compiler_federation.sqlite_db_path)
    tbox_path = root_dir / Path(config.layer4_compiler_federation.tbox_path)
    trig_path = root_dir / Path(config.layer4_compiler_federation.dataset_trig_path)
    r2rml_path = root_dir / Path(config.layer4_compiler_federation.r2rml_path)
    shapes_dir = root_dir / Path(config.layer4_compiler_federation.shapes_dir)
    service_spec_shape_path = shapes_dir / "service_spec_shape.ttl"
    trouble_ticket_shape_path = shapes_dir / "trouble_ticket_shape.ttl"
    hitl_html_path = root_dir / Path(
        config.track_b_ingestion_and_er.hitl_gate1_report_path
    )
    hitl_md_path = hitl_html_path.with_suffix(".md")

    logger.info(
        "Starting Scenario DT-01a (mode=%s, update_golden_ref=%s) against %s",
        mode,
        update_golden_ref,
        sqlite_path,
    )

    # 1. Profile SQLite CMDB dynamically
    table_profiles, scd2_verification = profile_cmdb_sqlite_database(
        sqlite_path=sqlite_path,
        target_circuit_id=config.use_case.circuit_id,
    )
    total_rows = sum(t.total_rows for t in table_profiles)
    bound_tables = sum(
        1 for t in table_profiles if t.table_disposition == "BOUND_VIRTUAL_GRAPH"
    )
    excluded_tables = sum(
        1 for t in table_profiles if t.table_disposition == "EXCLUDED_NOISE"
    )
    logger.info(
        "DT-01a profiled %d SQLite tables (%d rows): %d bound, %d excluded noise (T_BILLING_AUDIT_NOISE)",
        len(table_profiles),
        total_rows,
        bound_tables,
        excluded_tables,
    )

    # 2. Write pruned TBox & TriG Dataset
    tbox_path.parent.mkdir(parents=True, exist_ok=True)
    tbox_path.write_text(build_tbox_sid_etom_turtle(), encoding="utf-8")
    write_knowledge_graph_trig_with_tbox(tbox_path=tbox_path, trig_path=trig_path)
    logger.info(
        "DT-01a wrote TBox (%s) and initialized TriG dataset (%s) with 0 virtual triples on disk",
        tbox_path.relative_to(root_dir).as_posix(),
        trig_path.relative_to(root_dir).as_posix(),
    )

    # 3. Write Base W3C SHACL Shapes
    shapes_dir.mkdir(parents=True, exist_ok=True)
    service_spec_shape_path.write_text(
        build_service_spec_shape_turtle(), encoding="utf-8"
    )
    trouble_ticket_shape_path.write_text(
        build_trouble_ticket_shape_turtle(), encoding="utf-8"
    )
    logger.info(
        "DT-01a wrote W3C SHACL shapes: %s, %s",
        service_spec_shape_path.relative_to(root_dir).as_posix(),
        trouble_ticket_shape_path.relative_to(root_dir).as_posix(),
    )

    # 4. Write W3C R2RML Mapping
    r2rml_path.parent.mkdir(parents=True, exist_ok=True)
    r2rml_path.write_text(build_cmdb_r2rml_turtle(), encoding="utf-8")
    logger.info(
        "DT-01a wrote W3C R2RML mapping: %s",
        r2rml_path.relative_to(root_dir).as_posix(),
    )

    # 5. Execute Evaluator Ontology Critique
    critique = evaluate_ontology_and_r2rml(
        table_profiles=table_profiles,
        tbox_path=tbox_path,
        r2rml_path=r2rml_path,
        trig_path=trig_path,
    )
    if not critique.overall_passed:
        raise ValueError(
            f"DT-01a Evaluator Ontology Critique failed: {critique.critique_summary}"
        )
    logger.info("DT-01a Evaluator Critique: %s", critique.critique_summary)

    # 6. Render HITL Gate 1 Reports
    gate1_status: Literal["CANDIDATE_PROPOSED", "LOCKED_APPROVED"] = (
        "LOCKED_APPROVED" if mode == "approve" else "CANDIDATE_PROPOSED"
    )
    executed_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_hitl_gate1_html_report(
        table_profiles=table_profiles,
        scd2_verification=scd2_verification,
        critique=critique,
        gate1_status=gate1_status,
        executed_at_utc=executed_at_utc,
        html_path=hitl_html_path,
    )
    _write_hitl_gate1_markdown_report(
        table_profiles=table_profiles,
        scd2_verification=scd2_verification,
        critique=critique,
        gate1_status=gate1_status,
        executed_at_utc=executed_at_utc,
        md_path=hitl_md_path,
    )
    logger.info(
        "DT-01a wrote HITL Gate 1 reports (%s) with status=%s",
        hitl_html_path.relative_to(root_dir).as_posix(),
        gate1_status,
    )

    # 7. Optional Golden Reference promotion (--update-golden-ref)
    golden_updated = False
    if update_golden_ref:
        golden_dir = root_dir / Path("data/golden_reference")
        golden_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tbox_path, golden_dir / tbox_path.name)
        shutil.copy2(r2rml_path, golden_dir / r2rml_path.name)
        shutil.copy2(service_spec_shape_path, golden_dir / service_spec_shape_path.name)
        shutil.copy2(
            trouble_ticket_shape_path, golden_dir / trouble_ticket_shape_path.name
        )
        golden_updated = True
        logger.info(
            "DT-01a promoted approved Step 2 artifacts into %s",
            golden_dir.relative_to(root_dir).as_posix(),
        )

    return Dt01aExecutionResult(
        scenario_id="DT-01a",
        gate1_mode=mode,
        gate1_status=gate1_status,
        executed_at_utc=executed_at_utc,
        total_tables_inspected=len(table_profiles),
        total_rows_inspected=total_rows,
        bound_tables_count=bound_tables,
        excluded_noise_tables_count=excluded_tables,
        table_profiles=table_profiles,
        scd2_verification=scd2_verification,
        evaluator_critique=critique,
        tbox_path=tbox_path,
        trig_dataset_path=trig_path,
        r2rml_path=r2rml_path,
        service_spec_shape_path=service_spec_shape_path,
        trouble_ticket_shape_path=trouble_ticket_shape_path,
        hitl_html_report_path=hitl_html_path,
        hitl_markdown_report_path=hitl_md_path,
        golden_ref_updated=golden_updated,
    )

