"""
Southbound FastMCP Server: `semantic-read-mcp` (Step 6 / Layer 3).

Exposes `query_knowledge_fabric` over the Layer 3 NL2Semantics engine and Layer 4
R2RML pushdown federation, enforcing configurable OBO JWT scope verification.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer

from src.config import get_workspace_root, load_config
from src.layer3.nl2semantics_engine import run_layer3_nl2semantics
from src.logger import setup_logger
from src.mcp_servers.common import validate_obo_jwt
from src.models import AppConfig

mcp = MCPServer("semantic-read-mcp")


def _validate_obo_jwt(
    obo_jwt: Optional[str],
    config: AppConfig,
) -> Dict[str, Any]:
    """Validate optional/mandatory OBO JWT token and required scope."""
    return validate_obo_jwt(
        obo_jwt=obo_jwt,
        required_scope=config.layer3_nl2semantics.required_obo_scope,
        require_jwt=config.layer3_nl2semantics.require_obo_jwt,
        bypass_auth_mode="STANDALONE_RT05_BYPASS",
    ).model_dump()


def execute_query_knowledge_fabric(
    natural_language_intent: str,
    target_circuit_id: Optional[str] = None,
    execution_mode: Optional[str] = None,
    obo_jwt: Optional[str] = None,
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    root_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Core implementation for `query_knowledge_fabric` usable both in-process and via FastMCP."""
    workspace_root = root_dir or get_workspace_root()
    active_config = config or load_config(workspace_root / "config.yaml")
    active_logger = logger or setup_logger(active_config, "semantic_read_mcp", workspace_root)

    auth_metadata = _validate_obo_jwt(obo_jwt=obo_jwt, config=active_config)
    result = run_layer3_nl2semantics(
        natural_language_intent=natural_language_intent,
        config=active_config,
        logger=active_logger,
        target_circuit_id=target_circuit_id,
        execution_mode=execution_mode,
        root_dir=workspace_root,
    )
    return {
        "auth_metadata": auth_metadata,
        "layer3_result": result.model_dump(mode="json"),
    }


@mcp.tool()
def query_knowledge_fabric(
    natural_language_intent: str,
    target_circuit_id: Optional[str] = None,
    execution_mode: Optional[str] = None,
    obo_jwt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Translate a natural-language telecom assurance intent into read-only federated SPARQL
    via Layer 3 (Voicebox Hybrid / Zero-Shot / Dual Comparison) and execute against Layer 4.
    """
    return execute_query_knowledge_fabric(
        natural_language_intent=natural_language_intent,
        target_circuit_id=target_circuit_id,
        execution_mode=execution_mode,
        obo_jwt=obo_jwt,
    )


if __name__ == "__main__":
    mcp.run()
