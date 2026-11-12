"""
Southbound MCP Platform Primitive Catalog Manager (`src/catalog_manager.py`).

Loads, validates, queries, and toggles the generic southbound MCP platform
primitives defined in `config/mcp_primitives_catalog.json` (`Option 2.1D-Catalog`
and `Option 6A-Generic`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from src.config import get_workspace_root
from src.models import AppConfig, McpPrimitiveDefinition, McpPrimitivesCatalog


def resolve_catalog_path(
    config: AppConfig, workspace_root: Optional[Path] = None
) -> Path:
    """Resolve the absolute path to `config/mcp_primitives_catalog.json`."""
    root_dir = workspace_root if workspace_root is not None else get_workspace_root()
    return root_dir / Path(config.layer2_worker_and_sop.mcp_catalog_path)


def create_default_catalog() -> McpPrimitivesCatalog:
    """Build the default validated `McpPrimitivesCatalog` instance."""
    return McpPrimitivesCatalog(
        catalog_version="1.0.0",
        enable_tmf621_dispatch_primitive=True,
        primitives=[
            McpPrimitiveDefinition(
                primitive_uri="mcp://semantic-read/query_knowledge_fabric",
                server_id="semantic-read-mcp",
                plane="semantic_read_plane",
                description=(
                    "Executes read-only federated semantic queries across Layer 3 "
                    "NL2Semantics and Layer 4 R2RML/Named Graphs."
                ),
                supported_protocols=["SPARQL_1_1_FEDERATED_READ"],
                required_args=["intent_query", "circuit_id", "obo_jwt"],
                enabled=True,
            ),
            McpPrimitiveDefinition(
                primitive_uri="cqrs://singleton-check/probe_resource_state",
                server_id="singleton-check-mcp",
                plane="cqrs_action_plane",
                description=(
                    "Executes real-time non-cached singleton hardware telemetry probes "
                    "and acquires short-lived port mutex locks."
                ),
                supported_protocols=["gNMI_OPTICAL_TELEMETRY"],
                required_args=[
                    "resource_iri",
                    "requested_metrics",
                    "bypass_cache",
                    "acquire_mutex_ttl_sec",
                    "obo_jwt",
                ],
                enabled=True,
            ),
            McpPrimitiveDefinition(
                primitive_uri="cqrs://transactional-write/execute_governed_mutation",
                server_id="transactional-write-mcp",
                plane="cqrs_action_plane",
                description=(
                    "Executes OBO-authenticated, mutex-locked, token-bucket-governed "
                    "southbound OSS/NMS state mutations."
                ),
                supported_protocols=[
                    "TMF640_SERVICE_ACTIVATION",
                    "TMF621_TROUBLE_TICKET",
                ],
                required_args=[
                    "protocol",
                    "operation",
                    "params",
                    "resource_iri",
                    "singleton_lock_token",
                    "obo_jwt",
                ],
                enabled=True,
            ),
            McpPrimitiveDefinition(
                primitive_uri="cqrs://transactional-write/commit_validated_graph_triples",
                server_id="transactional-write-mcp",
                plane="cqrs_action_plane",
                description=(
                    "Validates candidate RDF triples against pySHACL shapes and "
                    "atomically commits them to a curated Named Graph."
                ),
                supported_protocols=["SHACL_VALIDATED_RDF_COMMIT"],
                required_args=[
                    "candidate_turtle",
                    "target_graph",
                    "shacl_shape",
                    "singleton_lock_token",
                    "obo_jwt",
                ],
                enabled=True,
            ),
        ],
    )


def load_catalog(
    config: AppConfig, workspace_root: Optional[Path] = None
) -> McpPrimitivesCatalog:
    """
    Load and validate `config/mcp_primitives_catalog.json` via Pydantic v2.

    Fails fast with `FileNotFoundError` or `ValueError` if missing or invalid.
    """
    catalog_path = resolve_catalog_path(config, workspace_root)
    if not catalog_path.exists() or not catalog_path.is_file():
        raise FileNotFoundError(
            f"MCP Primitives Catalog not found at expected path: {catalog_path}"
        )

    raw_data = json.loads(catalog_path.read_text(encoding="utf-8"))
    return McpPrimitivesCatalog.model_validate(raw_data)


def save_catalog(
    catalog: McpPrimitivesCatalog,
    config: AppConfig,
    workspace_root: Optional[Path] = None,
) -> Path:
    """Persist a validated `McpPrimitivesCatalog` to `config/mcp_primitives_catalog.json`."""
    catalog_path = resolve_catalog_path(config, workspace_root)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(catalog.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return catalog_path


def set_tmf621_primitive_enabled(
    enabled: bool,
    config: AppConfig,
    workspace_root: Optional[Path] = None,
) -> McpPrimitivesCatalog:
    """
    Toggle `enable_tmf621_dispatch_primitive` in the MCP Primitive Catalog.

    When `enabled=False` (for Scenario `DT-02a`), `TMF621_TROUBLE_TICKET` is removed
    from `execute_governed_mutation.supported_protocols`. When `enabled=True`
    (for Scenario `DT-02b`), `TMF621_TROUBLE_TICKET` is restored.
    """
    catalog_path = resolve_catalog_path(config, workspace_root)
    if catalog_path.exists():
        current = load_catalog(config, workspace_root)
    else:
        current = create_default_catalog()

    updated_primitives: List[McpPrimitiveDefinition] = []
    for prim in current.primitives:
        if prim.primitive_uri == "cqrs://transactional-write/execute_governed_mutation":
            protocols = [
                p for p in prim.supported_protocols if p != "TMF621_TROUBLE_TICKET"
            ]
            if enabled:
                protocols.append("TMF621_TROUBLE_TICKET")
            updated_primitives.append(
                McpPrimitiveDefinition(
                    primitive_uri=prim.primitive_uri,
                    server_id=prim.server_id,
                    plane=prim.plane,
                    description=prim.description,
                    supported_protocols=protocols,
                    required_args=prim.required_args,
                    enabled=prim.enabled,
                )
            )
        else:
            updated_primitives.append(prim)

    updated_catalog = McpPrimitivesCatalog(
        catalog_version=current.catalog_version,
        enable_tmf621_dispatch_primitive=enabled,
        primitives=updated_primitives,
    )
    save_catalog(updated_catalog, config, workspace_root)
    return updated_catalog


def get_active_protocols_for_primitive(
    catalog: McpPrimitivesCatalog, primitive_uri: str
) -> List[str]:
    """Return the active supported protocols for a given `primitive_uri`."""
    for prim in catalog.primitives:
        if prim.primitive_uri == primitive_uri and prim.enabled:
            if (
                not catalog.enable_tmf621_dispatch_primitive
                and "TMF621_TROUBLE_TICKET" in prim.supported_protocols
            ):
                return [
                    p for p in prim.supported_protocols if p != "TMF621_TROUBLE_TICKET"
                ]
            return list(prim.supported_protocols)
    return []

