"""
Scenario `DT-00` State Manager — Wipe & Reset to Clean Slate (`src/state_manager.py`).

Implements:
  - `initialize_cqrs_state`: Resets `data/cqrs_state/cqrs_runtime_state.json` to
    0 active port mutex locks and full token-bucket capacity (`3/3`).
  - `load_cqrs_state`: Loads and validates `cqrs_runtime_state.json` via Pydantic v2.
  - `reset_to_clean_slate`: Executes Scenario `DT-00` by clearing all materialized
    Named Graphs, unbinding R2RML virtual mappings, deleting compiled Worker Agent
    skills and HITL build reports, resetting CQRS state, and optionally toggling
    the MCP catalog gap flag (`enable_tmf621_dispatch_primitive`) while preserving
    `data/raw_sources/` and `data/golden_reference/` untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import List, Optional

from src.catalog_manager import set_tmf621_primitive_enabled
from src.config import get_workspace_root
from src.models import AppConfig, CleanSlateWipeSummary, CqrsRuntimeState


def resolve_cqrs_state_path(
    config: AppConfig, workspace_root: Optional[Path] = None
) -> Path:
    """Resolve the absolute path to `data/cqrs_state/cqrs_runtime_state.json`."""
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()
    return root_dir / Path(config.cqrs_action_plane.state_file_path)


def initialize_cqrs_state(
    config: AppConfig, workspace_root: Optional[Path] = None
) -> CqrsRuntimeState:
    """
    Create or reset `data/cqrs_state/cqrs_runtime_state.json` with 0 active mutex
    locks and full token-bucket capacity (`rate_limit_max_tokens`).
    """
    state_path = resolve_cqrs_state_path(config, workspace_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = CqrsRuntimeState(
        active_telemetry_preset=config.cqrs_action_plane.active_telemetry_preset,
        active_mutex_locks={},
        rate_limit_remaining_tokens=config.cqrs_action_plane.rate_limit_max_tokens,
        rate_limit_max_tokens=config.cqrs_action_plane.rate_limit_max_tokens,
        rate_limit_window_seconds=config.cqrs_action_plane.rate_limit_window_seconds,
        last_reset_utc=now_utc,
    )
    state_path.write_text(
        json.dumps(state.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return state


def load_cqrs_state(
    config: AppConfig, workspace_root: Optional[Path] = None
) -> CqrsRuntimeState:
    """
    Load and validate `data/cqrs_state/cqrs_runtime_state.json`.

    If the state file does not exist yet, initializes it to the baseline state.
    """
    state_path = resolve_cqrs_state_path(config, workspace_root)
    if not state_path.exists():
        return initialize_cqrs_state(config, workspace_root)

    raw_data = json.loads(state_path.read_text(encoding="utf-8"))
    return CqrsRuntimeState.model_validate(raw_data)


def reset_to_clean_slate(
    config: AppConfig,
    logger: logging.Logger,
    set_catalog_gap: bool = False,
    workspace_root: Optional[Path] = None,
) -> CleanSlateWipeSummary:
    """
    Execute Scenario `DT-00` (Wipe & Reset to Clean Slate).

    - Preserves `data/raw_sources/` and `data/golden_reference/` untouched.
    - Removes active semantic store & mapping artifacts (`knowledge_graph.trig`,
      `tbox_sid_etom.ttl`, `cmdb_r2rml.ttl`, `excel_catalog_rml.yaml`, `shapes/*.ttl`).
    - Removes compiled Layer 2 worker skills (`skill_sop_402.yaml`, `guardrails_sop_402.json`).
    - Removes generated build/HITL reports (`hitl_gate1_ontology_mapping_review.html`,
      `hitl_gate2_ingestion_er_curation.html`, `shacl_quarantine_report.html`,
      `missing_primitive_spec.json`, `hitl_sop_skill_review.html`).
    - Resets `data/cqrs_state/cqrs_runtime_state.json` (0 active locks, 3/3 tokens).
    - Sets `enable_tmf621_dispatch_primitive` to `not set_catalog_gap`.
    """
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()
    logger.info("Executing Scenario DT-00 (Wipe & Reset to Clean Slate) in %s", root_dir)

    target_rel_paths: List[Path] = [
        Path(config.layer4_compiler_federation.dataset_trig_path),
        Path(config.layer4_compiler_federation.tbox_path),
        Path(config.layer3_nl2semantics.stored_sparql_templates_path),
        Path(config.track_b_ingestion_and_er.gate1_candidate_proposal_path),
        Path(config.track_b_ingestion_and_er.gate2_candidate_proposal_path),
        Path(config.layer4_compiler_federation.r2rml_path),
        Path(config.layer4_compiler_federation.excel_rml_path),
        Path(config.layer2_worker_and_sop.active_skill_path),
        Path(config.layer2_worker_and_sop.active_guardrails_path),
        Path(config.layer2_worker_and_sop.gate3_candidate_proposal_path),
        Path(config.layer2_worker_and_sop.missing_primitive_spec_path),
        Path(config.layer2_worker_and_sop.hitl_sop_review_report_path),
        Path(config.layer2_worker_and_sop.hitl_sop_review_report_path).with_suffix(".md"),
        Path(config.track_b_ingestion_and_er.hitl_gate1_report_path),
        Path(config.track_b_ingestion_and_er.hitl_gate1_report_path).with_suffix(".md"),
        Path(config.track_b_ingestion_and_er.hitl_gate2_report_path),
        Path(config.track_b_ingestion_and_er.hitl_gate2_report_path).with_suffix(".md"),
        Path(config.track_b_ingestion_and_er.shacl_quarantine_report_path),
        Path(config.track_b_ingestion_and_er.shacl_quarantine_report_path).with_suffix(".md"),
        Path(config.track_b_ingestion_and_er.shacl_quarantine_summary_path),
        Path(config.layer4_compiler_federation.layer4_federation_proof_report_path),
        Path(config.layer4_compiler_federation.layer4_federation_proof_report_path).with_suffix(".md"),
        Path(config.layer3_nl2semantics.rt05_comparison_report_path),
        Path(config.layer3_nl2semantics.rt05_comparison_report_path).with_suffix(".md"),
        Path(config.cqrs_action_plane.ticket_journal_path),
        Path(config.cqrs_action_plane.step8_verification_report_path),
        Path(config.cqrs_action_plane.step8_verification_report_path).with_suffix(".md"),
        Path(config.layer1_orchestrator.export_ai_studio_schema_path),
    ]

    removed_files: List[str] = []
    for rel_path in target_rel_paths:
        abs_path = root_dir / rel_path
        if abs_path.exists() and abs_path.is_file():
            abs_path.unlink()
            removed_files.append(rel_path.as_posix())
            logger.info("DT-00 removed artifact: %s", rel_path.as_posix())

    # Remove any SHACL shape files in shapes/
    shapes_dir = root_dir / Path(config.layer4_compiler_federation.shapes_dir)
    if shapes_dir.exists() and shapes_dir.is_dir():
        for ttl_file in sorted(shapes_dir.glob("*.ttl")):
            ttl_file.unlink()
            rel_str = ttl_file.relative_to(root_dir).as_posix()
            removed_files.append(rel_str)
            logger.info("DT-00 removed SHACL shape: %s", rel_str)

    # Ensure standard target directories exist (even when empty)
    for rel_dir in [
        Path("data/semantic_store"),
        Path("data/golden_reference"),
        Path("data/cqrs_state"),
        Path("mappings"),
        Path("shapes"),
        Path("skills"),
        Path("reports"),
    ]:
        (root_dir / rel_dir).mkdir(parents=True, exist_ok=True)

    # Reset CQRS runtime state (0 locks, 3/3 tokens)
    cqrs_state = initialize_cqrs_state(config, root_dir)
    cqrs_state_path = resolve_cqrs_state_path(config, root_dir)
    logger.info(
        "DT-00 reset CQRS runtime state at %s (active_locks=%d, tokens=%d/%d)",
        cqrs_state_path.relative_to(root_dir).as_posix(),
        len(cqrs_state.active_mutex_locks),
        cqrs_state.rate_limit_remaining_tokens,
        cqrs_state.rate_limit_max_tokens,
    )

    # Update MCP Primitives Catalog gap flag
    enable_tmf621 = not set_catalog_gap
    updated_catalog = set_tmf621_primitive_enabled(
        enabled=enable_tmf621,
        config=config,
        workspace_root=root_dir,
    )
    logger.info(
        "DT-00 updated MCP Primitives Catalog: enable_tmf621_dispatch_primitive=%s",
        updated_catalog.enable_tmf621_dispatch_primitive,
    )

    # Verify Stage 0 raw sources remain preserved
    raw_dir = root_dir / Path(config.paths.raw_sources_dir)
    preserved_raw_files = (
        [f for f in raw_dir.rglob("*") if f.is_file()] if raw_dir.exists() else []
    )
    logger.info(
        "DT-00 preserved %d Stage 0 raw source files in %s",
        len(preserved_raw_files),
        config.paths.raw_sources_dir,
    )

    return CleanSlateWipeSummary(
        scenario_id="DT-00",
        removed_files=removed_files,
        preserved_raw_sources_count=len(preserved_raw_files),
        catalog_gap_enabled=set_catalog_gap,
        enable_tmf621_dispatch_primitive=updated_catalog.enable_tmf621_dispatch_primitive,
        cqrs_state_path=cqrs_state_path,
        reset_timestamp_utc=cqrs_state.last_reset_utc,
    )

