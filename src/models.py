"""
Shared Pydantic v2 Data Models for Configuration and Stage 0 Artifact Generation.

All data structures passed across multiple functions use strict Pydantic v2
validation (`ConfigDict(extra="forbid", frozen=True)`) per AGENTS.md Part 2.2 & Part 3.1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Configuration Schema Models
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


class AppConfig(BaseModel):
    """Top-level validated application configuration loaded from `config.yaml`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project: ProjectSettings
    gcp: GcpSettings
    logging: LoggingSettings
    paths: PathsSettings
    stage0: Stage0Settings
    ai: AiSettings


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

