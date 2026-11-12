"""
Shared Pydantic v2 Data Models for Configuration, Stage 0 Artifacts, MCP Primitive
Catalog, CQRS Runtime State, DT-00 Clean-Slate Wipe, and SYS-01 State Inspector.

All data structures passed across multiple functions use strict Pydantic v2
validation (`ConfigDict(extra="forbid", frozen=True)`) per AGENTS.md Part 2.2 & Part 3.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Tuple

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
    hitl_gate1_report_path: str = Field(
        default="reports/hitl_gate1_ontology_mapping_review.html", min_length=1
    )
    hitl_gate2_report_path: str = Field(
        default="reports/hitl_gate2_ingestion_er_curation.html", min_length=1
    )
    shacl_quarantine_report_path: str = Field(
        default="reports/shacl_quarantine_report.html", min_length=1
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
