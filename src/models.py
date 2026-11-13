"""
Shared Pydantic v2 Data Models for Configuration, Stage 0 Artifacts, MCP Primitive
Catalog, CQRS Runtime State, DT-00 Clean-Slate Wipe, and SYS-01 State Inspector.

All data structures passed across multiple functions use strict Pydantic v2
validation (`ConfigDict(extra="forbid", frozen=True)`) per AGENTS.md Part 2.2 & Part 3.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Configuration Schema Models (Root `config.yaml`)
# ============================================================================
class ProjectSettings(BaseModel):
    """Metadata and environment configuration for the project workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    prefix: str = Field(..., min_length=1)
    use_case_id: str = Field(..., min_length=1)
    use_case_title: str = Field(..., min_length=1)
    environment: str = Field(..., pattern=r"^(local|cloud|dev|staging|prod)$")


class GcpSettings(BaseModel):
    """Single-project GCP configuration (1-to-1 workspace mapping per Part 5.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(..., min_length=1)
    region: str = Field(default="europe-west4", min_length=1)
    artifact_bucket_name: str = Field(..., min_length=1)
    runtime_service_account: str = Field(..., min_length=1)


class LoggingSettings(BaseModel):
    """Dual logging configuration (console + local rotating file vs. cloud stdout)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_dir: str = Field(default="logs", min_length=1)
    log_filename: str = Field(default="telco_agent.log", min_length=1)
    max_bytes: int = Field(default=5242880, ge=1024)
    backup_count: int = Field(default=3, ge=1)


class PathsSettings(BaseModel):
    """Relative directory and file paths within the project workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_sources_dir: str = Field(..., min_length=1)
    sql_subdir: str = Field(..., min_length=1)
    excel_subdir: str = Field(..., min_length=1)
    pdf_subdir: str = Field(..., min_length=1)
    sop_subdir: str = Field(..., min_length=1)
    manifest_filename: str = Field(..., min_length=1)


class Stage0Settings(BaseModel):
    """Target identifiers and filenames for Stage 0 (Activity 0.2) raw sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int = Field(default=42)
    sql_db_filename: str = Field(..., min_length=1)
    sql_dump_filename: str = Field(..., min_length=1)
    excel_catalog_filename: str = Field(..., min_length=1)
    hw_manual_pdf_filename: str = Field(..., min_length=1)
    msa_contract_pdf_filename: str = Field(..., min_length=1)
    sop_runbook_docx_filename: str = Field(..., min_length=1)
    sop_runbook_md_filename: str = Field(..., min_length=1)
    target_customer_id: str = Field(..., min_length=1)
    target_customer_legal_name: str = Field(..., min_length=1)
    target_customer_bv_name: str = Field(..., min_length=1)
    target_customer_kvk: str = Field(..., min_length=1)
    target_circuit_id: str = Field(..., min_length=1)
    target_product_sku: str = Field(..., min_length=1)
    target_upgrade_sku: str = Field(..., min_length=1)
    target_pe_router: str = Field(..., min_length=1)
    target_olt_port: str = Field(..., min_length=1)
    target_rfs_id: str = Field(..., min_length=1)
    target_cpe_asset_id: str = Field(..., min_length=1)
    target_cpe_model_sku: str = Field(..., min_length=1)
    target_sop_id: str = Field(..., min_length=1)


class AiSettings(BaseModel):
    """Configurable LLM and agent parameters per Part 2.7."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_name: str = Field(..., min_length=1)
    component_models: Dict[str, str] = Field(default_factory=dict)
    location: str = Field(default="europe-west4", min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=1)
    thinking_budget: int = Field(default=1024, ge=0)


class UseCaseSettings(BaseModel):
    """Activity 0.3 locked use-case ground truth parameters (`UC-001`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    use_case_id: str = Field(default="UC-001", min_length=1)
    title: str = Field(..., min_length=1)
    customer_name: str = Field(default="A Corporate Enterprise", min_length=1)
    customer_id: str = Field(default="CUST-ENT-409", min_length=1)
    customer_bv_name: str = Field(default="A Corporate Enterprise B.V.", min_length=1)
    customer_registration_kvk: str = Field(default="NL-8841209", min_length=1)
    circuit_id: str = Field(default="CIR-994821", min_length=1)
    active_product_sku: str = Field(default="ETH-10G-GOLD", min_length=1)
    expired_product_sku: str = Field(default="ETH-1G-SILVER", min_length=1)
    cfs_expired_row_id: int = Field(default=2000, ge=1)
    cfs_active_row_id: int = Field(default=2001, ge=1)
    pe_router_hostname: str = Field(default="NLD-HAG-PE02", min_length=1)
    olt_port_id: str = Field(default="OLT04-P12", min_length=1)
    rfs_id: str = Field(default="RFS-OLT04-P12", min_length=1)
    cpe_asset_id: str = Field(default="CPE-ASN-7741", min_length=1)
    cpe_model_sku: str = Field(default="NOK-7210-SAS-Mxp", min_length=1)
    sop_id: str = Field(default="SOP-ASSUR-402", min_length=1)


class Layer1OrchestratorSettings(BaseModel):
    """Decision 1 (`Option 1D`): Dual-Interface Northbound Gateway settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: str = Field(default="1D", min_length=1)
    transport_mode: Literal["in_process", "sse"] = Field(default="in_process")
    sse_port: int = Field(default=8000, ge=1024, le=65535)
    llm_model: str = Field(default="gemini-2.5-flash", min_length=1)
    export_ai_studio_schema_path: str = Field(
        default="reports/ai_studio_tool_declarations.json", min_length=1
    )


class Layer2WorkerAndSopSettings(BaseModel):
    """Decision 2 (`Option 2.1D-Catalog` + `Option 2.2A`): SOP Compiler & Worker Agent settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compiler_option_id: str = Field(default="2.1D-Catalog", min_length=1)
    runtime_option_id: str = Field(default="2.2A", min_length=1)
    active_skill_path: str = Field(default="skills/skill_sop_402.yaml", min_length=1)
    active_guardrails_path: str = Field(default="skills/guardrails_sop_402.json", min_length=1)
    missing_primitive_spec_path: str = Field(
        default="reports/missing_primitive_spec.json", min_length=1
    )
    hitl_sop_review_report_path: str = Field(
        default="reports/hitl_sop_skill_review.html", min_length=1
    )
    mcp_catalog_path: str = Field(default="config/mcp_primitives_catalog.json", min_length=1)


class Layer3Nl2SemanticsSettings(BaseModel):
    """Decision 3 (`Option 3C-Dual`): Dual Shadow Comparison NL2Semantics settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: str = Field(default="3C-Dual", min_length=1)
    execution_mode: Literal["dual_comparison", "voicebox_hybrid", "zero_shot_llm"] = Field(
        default="dual_comparison"
    )


class Layer4CompilerFederationSettings(BaseModel):
    """Decision 4 (`Option 4A`): `rdflib.Dataset` Named Graphs & R2RML-to-SQLite Pushdown settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: str = Field(default="4A", min_length=1)
    dataset_trig_path: str = Field(default="data/semantic_store/knowledge_graph.trig", min_length=1)
    tbox_path: str = Field(default="data/semantic_store/tbox_sid_etom.ttl", min_length=1)
    r2rml_path: str = Field(default="mappings/cmdb_r2rml.ttl", min_length=1)
    excel_rml_path: str = Field(default="mappings/excel_catalog_rml.yaml", min_length=1)
    shapes_dir: str = Field(default="shapes", min_length=1)
    sqlite_db_path: str = Field(
        default="data/raw_sources/sql/cmdb_installed_base.db", min_length=1
    )


class TrackBIngestionAndErSettings(BaseModel):
    """Decision 5 (`Option 5A-HITL`): Dual-HITL Semantic Modeling, Quarantine & ER settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: str = Field(default="5A-HITL", min_length=1)
    use_case_charter_path: str = Field(
        default="data/raw_sources/uc001_use_case_charter.md", min_length=1
    )
    tmf_sid_etom_vocab_path: str = Field(
        default="data/reference_standards/tmf_sid_etom_vocab.json", min_length=1
    )
    gate1_candidate_proposal_path: str = Field(
        default="data/semantic_store/gate1_candidate_proposal.json", min_length=1
    )
    profiler_prompt_template_path: str = Field(
        default="prompts/s1_cmdb_schema_profiler_prompt.md", min_length=1
    )
    excel_profiler_prompt_template_path: str = Field(
        default="prompts/s2_excel_catalog_profiler_prompt.md", min_length=1
    )
    hitl_gate1_report_path: str = Field(
        default="reports/hitl_gate1_ontology_mapping_review.html", min_length=1
    )
    hitl_gate2_report_path: str = Field(
        default="reports/hitl_gate2_ingestion_er_curation.html", min_length=1
    )
    shacl_quarantine_report_path: str = Field(
        default="reports/shacl_quarantine_report.html", min_length=1
    )
    shacl_quarantine_summary_path: str = Field(
        default="reports/shacl_quarantine_summary.json", min_length=1
    )


class CqrsActionPlaneSettings(BaseModel):
    """Decision 6 (`Option 6A-Generic`): Reusable CQRS Platform Primitives & State Store settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    option_id: str = Field(default="6A-Generic", min_length=1)
    state_file_path: str = Field(
        default="data/cqrs_state/cqrs_runtime_state.json", min_length=1
    )
    active_telemetry_preset: Literal[
        "branch_a_soft_degradation",
        "branch_b_hard_fiber_cut",
        "branch_c_maintenance_lock",
    ] = Field(default="branch_a_soft_degradation")
    rate_limit_max_tokens: int = Field(default=3, ge=1)
    rate_limit_window_seconds: int = Field(default=300, ge=1)
    mutex_ttl_seconds: int = Field(default=60, ge=1)


class AppConfig(BaseModel):
    """Top-level validated application configuration loaded from `config.yaml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project: ProjectSettings
    gcp: GcpSettings
    logging: LoggingSettings
    paths: PathsSettings
    stage0: Stage0Settings
    ai: AiSettings
    use_case: UseCaseSettings
    layer1_orchestrator: Layer1OrchestratorSettings
    layer2_worker_and_sop: Layer2WorkerAndSopSettings
    layer3_nl2semantics: Layer3Nl2SemanticsSettings
    layer4_compiler_federation: Layer4CompilerFederationSettings
    track_b_ingestion_and_er: TrackBIngestionAndErSettings
    cqrs_action_plane: CqrsActionPlaneSettings


# ============================================================================
# Southbound MCP Platform Primitive Catalog Models (`config/mcp_primitives_catalog.json`)
# ============================================================================
class McpPrimitiveDefinition(BaseModel):
    """Metadata and supported protocols for a generic southbound MCP platform primitive."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    primitive_uri: str = Field(..., min_length=1)
    server_id: str = Field(..., min_length=1)
    plane: Literal["semantic_read_plane", "cqrs_action_plane"]
    description: str = Field(..., min_length=1)
    supported_protocols: List[str] = Field(default_factory=list)
    required_args: List[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)


class McpPrimitivesCatalog(BaseModel):
    """Validated Southbound MCP Platform Primitive Catalog (`Option 2.1D-Catalog` & `6A-Generic`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: str = Field(..., min_length=1)
    enable_tmf621_dispatch_primitive: bool = Field(default=True)
    primitives: List[McpPrimitiveDefinition] = Field(..., min_length=4)


# ============================================================================
# CQRS Runtime State Store Models (`data/cqrs_state/cqrs_runtime_state.json`)
# ============================================================================
class MutexLockEntry(BaseModel):
    """Active resource mutex lock entry in the CQRS state store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_iri: str = Field(..., min_length=1)
    lock_token: str = Field(..., min_length=1)
    acquired_at_utc: str = Field(..., min_length=1)
    expires_at_utc: str = Field(..., min_length=1)
    owner_subject: str = Field(..., min_length=1)


class CqrsRuntimeState(BaseModel):
    """Inspectable JSON state backing the CQRS Singleton Check & Transactional Write servers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_telemetry_preset: Literal[
        "branch_a_soft_degradation",
        "branch_b_hard_fiber_cut",
        "branch_c_maintenance_lock",
    ]
    active_mutex_locks: Dict[str, MutexLockEntry] = Field(default_factory=dict)
    rate_limit_remaining_tokens: int = Field(..., ge=0)
    rate_limit_max_tokens: int = Field(..., ge=1)
    rate_limit_window_seconds: int = Field(..., ge=1)
    last_reset_utc: str = Field(..., min_length=1)


# ============================================================================
# DT-00 Clean-Slate Wipe & SYS-01 Live State Inspector Models
# ============================================================================
class CleanSlateWipeSummary(BaseModel):
    """Summary returned by Scenario `DT-00` (`reset_to_clean_slate`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: Literal["DT-00"] = "DT-00"
    removed_files: List[str] = Field(default_factory=list)
    preserved_raw_sources_count: int = Field(..., ge=0)
    catalog_gap_enabled: bool
    enable_tmf621_dispatch_primitive: bool
    cqrs_state_path: Path
    reset_timestamp_utc: str = Field(..., min_length=1)


class InspectedElementStatus(BaseModel):
    """Status row for one of the 7 architectural elements in `SYS-01`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    element_number: int = Field(..., ge=1, le=7)
    element_name: str = Field(..., min_length=1)
    underlying_artifact: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)
    metrics_summary: str = Field(..., min_length=1)


class SystemStateReport(BaseModel):
    """Complete `SYS-01` Live System State Inspector report across all 7 elements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inspector_id: Literal["SYS-01"] = "SYS-01"
    inspected_at_utc: str = Field(..., min_length=1)
    use_case_id: str = Field(..., min_length=1)
    elements: List[InspectedElementStatus] = Field(..., min_length=7, max_length=7)
    html_report_path: Path
    markdown_report_path: Path


# ============================================================================
# Stage 0 Generator Result Models (Shared Between Generator, Manifest & Verifier)
# ============================================================================
class SqlTableCounts(BaseModel):
    """Row counts for each of the 4 relational SQL CMDB tables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    T_OSS_CUST_PARTY: int = Field(..., ge=1)
    T_CMDB_CFS_CIRCUIT: int = Field(..., ge=1)
    T_CMDB_RFS_RESOURCE: int = Field(..., ge=1)
    T_BILLING_AUDIT_NOISE: int = Field(..., ge=1)

    @property
    def total_rows(self) -> int:
        """Return total row count across all 4 CMDB tables."""
        return (
            self.T_OSS_CUST_PARTY
            + self.T_CMDB_CFS_CIRCUIT
            + self.T_CMDB_RFS_RESOURCE
            + self.T_BILLING_AUDIT_NOISE
        )


class SqlArtifactResult(BaseModel):
    """Validated metadata returned by Prong 1 SQL CMDB generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    db_path: Path
    dump_path: Path
    table_counts: SqlTableCounts


class ExcelTabCounts(BaseModel):
    """Row counts for each of the 3 worksheets in the Excel SLA Catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    Residential_FTTH_Plans: int = Field(..., ge=1)
    B2B_Enterprise_SLA_Matrix: int = Field(..., ge=1)
    Deprecated_Legacy_SKUs: int = Field(..., ge=1)

    @property
    def total_skus(self) -> int:
        """Return total SKU rows across all 3 worksheets."""
        return (
            self.Residential_FTTH_Plans
            + self.B2B_Enterprise_SLA_Matrix
            + self.Deprecated_Legacy_SKUs
        )


class ExcelArtifactResult(BaseModel):
    """Validated metadata returned by Prong 2 Excel Catalog generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    excel_path: Path
    tab_counts: ExcelTabCounts


class PdfArtifactResult(BaseModel):
    """Validated metadata returned by Prong 3 PDF generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hw_pdf_path: Path
    hw_pdf_pages: int = Field(..., ge=4)
    msa_pdf_path: Path
    msa_pdf_pages: int = Field(..., ge=3)


class SopArtifactResult(BaseModel):
    """Validated metadata returned by Multi-Procedure SOP Runbook generator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    docx_path: Path
    md_path: Path
    section_count: int = Field(..., ge=6)
    target_sop_id: str = Field(..., min_length=1)


class Stage0GenerationSummary(BaseModel):
    """Complete validated summary of all generated Stage 0 (Activity 0.2) artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_dir: Path
    sql: SqlArtifactResult
    excel: ExcelArtifactResult
    pdf: PdfArtifactResult
    sop: SopArtifactResult
    manifest_path: Path
    verified_sql_join: Tuple[str, str, str, str, str, int, str, str, str, str, str]
    verified_eth_gold_loss_pct: float
    verified_eth_gold_upgrade_sku: str
    verified_eth_gold_auto_remediation: str


# ============================================================================
# Step 2 (`DT-01a`) Prong 1 SQL CMDB Profiler, TBox, R2RML & HITL Gate 1 Models
# ============================================================================
ColumnDisposition = Literal[
    "MAPPED_TO_TBOX",
    "PHYSICAL_SCD2_CONTROL_ONLY",
    "EXCLUDED_INTERNAL_OR_LEGACY",
    "EXCLUDED_LEGACY",
    "EXCLUDED_SYNC_METADATA",
    "EXCLUDED_NOISE",
]


class ColumnProfileEntry(BaseModel):
    """Dynamic SQLite column profile entry with TMF SID/eTOM mapping or exclusion rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(..., min_length=1)
    column_name: str = Field(..., min_length=1)
    sql_type: str = Field(..., min_length=1)
    not_null: bool
    is_primary_key: bool
    disposition: ColumnDisposition
    mapped_tbox_target: str = Field(..., min_length=1)
    transformation_rule: str = Field(..., min_length=1)
    audit_rationale: str = Field(..., min_length=1)


class TableProfileEntry(BaseModel):
    """Dynamic SQLite table profile entry across the discovered relational tables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(..., min_length=1)
    total_rows: int = Field(..., ge=0)
    active_rows: int = Field(..., ge=0)
    table_disposition: Literal["BOUND_VIRTUAL_GRAPH", "EXCLUDED_NOISE"]
    target_tmf_classes: List[str] = Field(default_factory=list)
    canonical_iri_templates: List[str] = Field(default_factory=list)
    r2rml_triples_map_id: str = Field(..., min_length=1)
    columns: List[ColumnProfileEntry] = Field(..., min_length=1)


class Scd2CircuitVerification(BaseModel):
    """Ground-truth verification of SCD Type 2, shadow enum & QUDT math for a versioned circuit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    circuit_id: str = Field(..., min_length=1)
    expired_row_id: int = Field(..., ge=1)
    expired_product_sku: str = Field(..., min_length=1)
    expired_valid_to_ts: str = Field(..., min_length=1)
    active_row_id: int = Field(..., ge=1)
    active_product_sku: str = Field(..., min_length=1)
    raw_oper_status_cd: str = Field(..., min_length=1)
    canonical_oper_status: str = Field(..., min_length=1)
    raw_bandwidth_val: float = Field(..., gt=0.0)
    raw_bandwidth_unit: str = Field(..., min_length=1)
    normalized_bandwidth_gbps: float = Field(..., gt=0.0)


class IntrospectedColumnInfo(BaseModel):
    """Raw column metadata dynamically discovered via `PRAGMA table_info` and SQL sampling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column_name: str = Field(..., min_length=1)
    sql_type: str = Field(..., min_length=1)
    not_null: bool
    is_primary_key: bool
    null_count: int = Field(..., ge=0)
    distinct_count: int = Field(..., ge=0)
    low_cardinality_values: List[str] = Field(default_factory=list)


class IntrospectedForeignKeyInfo(BaseModel):
    """Raw foreign key metadata dynamically discovered via `PRAGMA foreign_key_list`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_column: str = Field(..., min_length=1)
    target_table: str = Field(..., min_length=1)
    target_column: str = Field(..., min_length=1)


class IntrospectedTableInfo(BaseModel):
    """Raw relational table introspection dynamically extracted from SQLite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(..., min_length=1)
    total_rows: int = Field(..., ge=0)
    columns: List[IntrospectedColumnInfo] = Field(..., min_length=1)
    foreign_keys: List[IntrospectedForeignKeyInfo] = Field(default_factory=list)
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)


class SqliteDatabaseIntrospection(BaseModel):
    """Complete schema-independent introspection of a relational SQLite database."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_filename: str = Field(..., min_length=1)
    total_tables: int = Field(..., ge=1)
    total_rows: int = Field(..., ge=1)
    tables: List[IntrospectedTableInfo] = Field(..., min_length=1)


class ProposedEtomProcess(BaseModel):
    """In-scope TM Forum eTOM (GB921) business process selected for the TBox."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    process_iri: str = Field(..., min_length=1)
    process_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    comment: str = Field(..., min_length=1)
    skos_alt_labels: List[str] = Field(..., min_length=2)


class ProposedOntologyClass(BaseModel):
    """Pruned TM Forum SID (GB922) / Telecom OWL class proposed for the TBox."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    class_iri: str = Field(..., min_length=1)
    sub_class_of_iri: Optional[str] = None
    label: str = Field(..., min_length=1)
    comment: str = Field(..., min_length=1)
    skos_alt_labels: List[str] = Field(..., min_length=2)
    aligned_etom_process_iris: List[str] = Field(..., min_length=1)


class ProposedOntologyProperty(BaseModel):
    """OWL ObjectProperty or DatatypeProperty proposed for the TBox."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    property_iri: str = Field(..., min_length=1)
    property_type: Literal["owl:ObjectProperty", "owl:DatatypeProperty"]
    domain_iri: str = Field(..., min_length=1)
    range_iri: str = Field(..., min_length=1)
    qudt_applicable_unit_iri: Optional[str] = None
    label: str = Field(..., min_length=1)
    comment: str = Field(..., min_length=1)
    skos_alt_labels: List[str] = Field(..., min_length=2)


class R2rmlPredicateObjectMapSpec(BaseModel):
    """Structured W3C R2RML `rr:predicateObjectMap` specification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    predicate_iri: str = Field(..., min_length=1)
    mapping_kind: Literal["column_literal", "iri_template"]
    column_or_template: str = Field(..., min_length=1)
    datatype_iri: Optional[str] = None


class ProposedTableMapping(BaseModel):
    """Structured table profiling & W3C R2RML mapping specification in the Gate 1 proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(..., min_length=1)
    total_rows: int = Field(..., ge=0)
    active_rows: int = Field(..., ge=0)
    table_disposition: Literal["BOUND_VIRTUAL_GRAPH", "EXCLUDED_NOISE"]
    target_tmf_classes: List[str] = Field(default_factory=list)
    canonical_iri_templates: List[str] = Field(default_factory=list)
    r2rml_triples_map_id: str = Field(..., min_length=1)
    r2rml_label: Optional[str] = None
    sql_query: Optional[str] = None
    subject_iri_template: Optional[str] = None
    subject_class_iri: Optional[str] = None
    predicate_object_mappings: List[R2rmlPredicateObjectMapSpec] = Field(
        default_factory=list
    )
    columns: List[ColumnProfileEntry] = Field(..., min_length=1)

    def to_table_profile_entry(self) -> TableProfileEntry:
        """Convert to `TableProfileEntry` for reporting and `SYS-01` compatibility."""
        return TableProfileEntry(
            table_name=self.table_name,
            total_rows=self.total_rows,
            active_rows=self.active_rows,
            table_disposition=self.table_disposition,
            target_tmf_classes=self.target_tmf_classes,
            canonical_iri_templates=self.canonical_iri_templates,
            r2rml_triples_map_id=self.r2rml_triples_map_id,
            columns=self.columns,
        )


class ProposedShaclPropertyConstraint(BaseModel):
    """Property constraint inside a proposed W3C SHACL NodeShape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path_iri: str = Field(..., min_length=1)
    datatype_iri: Optional[str] = None
    node_kind_iri: Optional[str] = None
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    min_inclusive: Optional[float] = None
    max_inclusive: Optional[float] = None
    allowed_values: List[str] = Field(default_factory=list)
    message: str = Field(..., min_length=1)


class ProposedShaclNodeShape(BaseModel):
    """Structured W3C SHACL NodeShape specification compiled to `shapes/<filename>`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_filename: str = Field(..., min_length=1)
    shape_iri: str = Field(..., min_length=1)
    target_class_iri: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    comment: str = Field(..., min_length=1)
    property_constraints: List[ProposedShaclPropertyConstraint] = Field(..., min_length=1)


class CandidateOntologyAndMappingProposal(BaseModel):
    """
    Complete schema-independent HITL Gate 1 Candidate Proposal (`gate1_candidate_proposal.json`)
    generated by the AI Schema Profiler from (1) Use Case Charter, (2) TMF SID/eTOM Vocabulary,
    and (3) Dynamic SQLite Introspection.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(..., min_length=1)
    use_case_id: str = Field(..., min_length=1)
    generated_at_utc: str = Field(..., min_length=1)
    llm_model_used: str = Field(..., min_length=1)
    ontology_iri: str = Field(default="urn:telco:graph:tbox:sid-etom", min_length=1)
    virtual_graph_iri: str = Field(default="urn:telco:graph:virtual:ib", min_length=1)
    ontology_label: str = Field(..., min_length=1)
    ontology_comment: str = Field(..., min_length=1)
    etom_processes: List[ProposedEtomProcess] = Field(..., min_length=2)
    proposed_classes: List[ProposedOntologyClass] = Field(..., min_length=12)
    proposed_properties: List[ProposedOntologyProperty] = Field(..., min_length=10)
    table_mappings: List[ProposedTableMapping] = Field(..., min_length=1)
    scd2_verification: Scd2CircuitVerification
    shacl_shapes: List[ProposedShaclNodeShape] = Field(..., min_length=2)
    architect_verification_questions: List[str] = Field(..., min_length=4)


class EvaluatorOntologyCritique(BaseModel):
    """Automated Evaluator Agent critique of the candidate TBox and R2RML mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    zero_sql_leakage_in_tbox: bool
    leaked_sql_tokens: List[str] = Field(default_factory=list)
    billing_noise_table_excluded: bool
    scd2_active_filter_present: bool
    shadow_enum_translation_present: bool
    qudt_bandwidth_normalization_present: bool
    virtual_graph_zero_persisted_triples: bool
    tbox_class_count: int = Field(..., ge=12)
    tbox_property_count: int = Field(..., ge=10)
    tbox_skos_alt_label_count: int = Field(..., ge=24)
    overall_passed: bool
    critique_summary: str = Field(..., min_length=1)


class Dt01aExecutionResult(BaseModel):
    """Complete validated summary returned by Scenario `DT-01a` (`run_dt01a_cmdb_profiler`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: Literal["DT-01a"] = "DT-01a"
    gate1_mode: Literal["candidate", "approve"]
    gate1_status: Literal["CANDIDATE_PROPOSED", "LOCKED_APPROVED"]
    executed_at_utc: str = Field(..., min_length=1)
    total_tables_inspected: int = Field(..., ge=1)
    total_rows_inspected: int = Field(..., ge=1)
    bound_tables_count: int = Field(..., ge=1)
    excluded_noise_tables_count: int = Field(..., ge=1)
    table_profiles: List[TableProfileEntry] = Field(..., min_length=1)
    scd2_verification: Scd2CircuitVerification
    evaluator_critique: EvaluatorOntologyCritique
    candidate_proposal_path: Path
    architect_verification_questions: List[str] = Field(..., min_length=4)
    tbox_path: Optional[Path] = None
    trig_dataset_path: Optional[Path] = None
    r2rml_path: Optional[Path] = None
    service_spec_shape_path: Optional[Path] = None
    trouble_ticket_shape_path: Optional[Path] = None
    hitl_html_report_path: Path
    hitl_markdown_report_path: Path
    golden_ref_updated: bool


# ============================================================================
# Step 3 (DT-01b): Multi-Tab Excel Catalog Profiler & pySHACL Quarantine Models
# ============================================================================
class ExcelSheetIntrospection(BaseModel):
    """Dynamic structural snapshot of a single Excel worksheet without hardcoded assumptions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet_name: str = Field(..., min_length=1)
    max_row: int = Field(..., ge=0)
    max_col: int = Field(..., ge=0)
    merged_cell_ranges: List[str] = Field(default_factory=list)
    preview_rows: List[List[str]] = Field(default_factory=list)


class ExcelWorkbookIntrospection(BaseModel):
    """Complete dynamic structural introspection payload for an Excel workbook."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workbook_path: str = Field(..., min_length=1)
    sheet_count: int = Field(..., ge=1)
    sheets: List[ExcelSheetIntrospection] = Field(..., min_length=1)


class ExcelWorksheetClassification(BaseModel):
    """LLM classification decision for a single Excel worksheet tab."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sheet_name: str = Field(..., min_length=1)
    classification: Literal["TARGET_INGEST_TAB", "EXCLUDED_DISTRACTOR_TAB"]
    rationale: str = Field(..., min_length=1)
    header_row_index: Optional[int] = Field(default=None, ge=1)
    data_start_row_index: Optional[int] = Field(default=None, ge=1)
    banner_rows_detected: List[int] = Field(default_factory=list)


class ExcelValueMapEntry(BaseModel):
    """Single deterministic value translation entry for an Excel column."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_value: str = Field(..., min_length=1)
    target_value: str = Field(..., min_length=1)


class ExcelColumnMappingSpec(BaseModel):
    """Column-to-TBox property mapping specification for the target Excel worksheet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_column_header: str = Field(..., min_length=1)
    column_index: int = Field(..., ge=1)
    mapping_status: Literal["MAPPED", "EXCLUDED_NOISE"]
    target_property_qname: Optional[str] = None
    datatype_qname: Optional[str] = None
    is_sku_identifier: bool = False
    is_iri_reference: bool = False
    iri_reference_template: Optional[str] = None
    value_map: List[ExcelValueMapEntry] = Field(default_factory=list)
    rationale: str = Field(..., min_length=1)


class ExcelCatalogMappingProposal(BaseModel):
    """Structured LLM proposal for Prong 2 Excel Catalog profiling and RML generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_sheet_name: str = Field(..., min_length=1)
    target_class_qname: str = Field(..., min_length=1)
    canonical_iri_template: str = Field(..., min_length=1)
    sku_column_header: str = Field(..., min_length=1)
    header_row_index: int = Field(..., ge=1)
    data_start_row_index: int = Field(..., ge=1)
    worksheet_classifications: List[ExcelWorksheetClassification] = Field(
        ..., min_length=1
    )
    column_mappings: List[ExcelColumnMappingSpec] = Field(..., min_length=1)
    mapping_rationale: str = Field(..., min_length=1)


class QuarantinedRowRecord(BaseModel):
    """Detailed audit record for a single Excel row blocked by pySHACL validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    excel_row_number: int = Field(..., ge=1)
    sku_code: Optional[str] = None
    raw_row_values: Dict[str, Any]
    violated_constraint_component: str = Field(..., min_length=1)
    focus_node: str = Field(..., min_length=1)
    result_path: Optional[str] = None
    shacl_message: str = Field(..., min_length=1)
    shacl_report_text: str = Field(..., min_length=1)


class PromotedSkuSummary(BaseModel):
    """Audit summary of a valid B2B SKU promoted to <urn:telco:graph:ref:catalog>."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    excel_row_number: int = Field(..., ge=1)
    sku_code: str = Field(..., min_length=1)
    subject_iri: str = Field(..., min_length=1)
    triple_count: int = Field(..., ge=1)
    max_packet_loss_pct: Optional[float] = None
    availability_target_pct: Optional[float] = None
    lifecycle_status: Optional[str] = None
    auto_remediation_allowed: Optional[bool] = None


class ShaclQuarantineSummary(BaseModel):
    """Machine-readable quarantine metrics persisted for SYS-01 and downstream inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: Literal["DT-01b"] = "DT-01b"
    executed_at_utc: str = Field(..., min_length=1)
    workbook_path: str = Field(..., min_length=1)
    target_sheet_name: str = Field(..., min_length=1)
    header_row_index: int = Field(..., ge=1)
    data_start_row_index: int = Field(..., ge=1)
    excluded_distractor_tabs_count: int = Field(..., ge=0)
    excluded_distractor_tabs: List[str] = Field(default_factory=list)
    total_data_rows_evaluated: int = Field(..., ge=0)
    valid_skus_loaded_count: int = Field(..., ge=0)
    quarantined_rows_count: int = Field(..., ge=0)
    catalog_triples_materialized: int = Field(..., ge=0)
    virtual_ib_triples_count: int = Field(..., ge=0)
    rml_mapping_path: str = Field(..., min_length=1)
    quarantined_rows: List[QuarantinedRowRecord] = Field(default_factory=list)


class Dt01bExecutionResult(BaseModel):
    """Complete validated summary returned by Scenario `DT-01b`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: Literal["DT-01b"] = "DT-01b"
    executed_at_utc: str = Field(..., min_length=1)
    model_used: str = Field(..., min_length=1)
    workbook_path: Path
    rml_mapping_path: Path
    trig_dataset_path: Path
    quarantine_html_report_path: Path
    quarantine_markdown_report_path: Path
    quarantine_summary_json_path: Path
    target_sheet_name: str = Field(..., min_length=1)
    excluded_distractor_tabs_count: int = Field(..., ge=0)
    total_data_rows_evaluated: int = Field(..., ge=0)
    valid_skus_loaded_count: int = Field(..., ge=0)
    quarantined_rows_count: int = Field(..., ge=0)
    catalog_triples_materialized: int = Field(..., ge=0)
    virtual_ib_triples_count: int = Field(..., ge=0)
    promoted_skus: List[PromotedSkuSummary] = Field(default_factory=list)
    quarantined_rows: List[QuarantinedRowRecord] = Field(default_factory=list)



