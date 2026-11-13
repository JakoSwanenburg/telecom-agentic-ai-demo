"""
Shared OBO JWT verification and CQRS state persistence helpers for Southbound MCP servers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple

import jwt

from src.config import get_workspace_root, load_config
from src.logger import setup_logger
from src.models import (
    AppConfig,
    CqrsRuntimeState,
    OboAuthMetadata,
    Tmf621TicketRecord,
)
from src.state_manager import resolve_cqrs_state_path


def utc_now_iso() -> str:
    """Return current timezone-aware UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_mcp_context(
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    root_dir: Optional[Path] = None,
    logger_name: str = "telco_agent.mcp",
) -> Tuple[Path, AppConfig, logging.Logger]:
    """Resolve workspace root, validated AppConfig, and configured logger."""
    workspace_root = root_dir or get_workspace_root()
    active_config = config or load_config(workspace_root / "config.yaml")
    active_logger = logger or setup_logger(
        active_config, logger_name=logger_name, workspace_root=workspace_root
    )
    return workspace_root, active_config, active_logger


def validate_obo_jwt(
    obo_jwt: Optional[str],
    required_scope: str,
    require_jwt: bool,
    bypass_auth_mode: Literal[
        "STANDALONE_MCP_BYPASS", "STANDALONE_RT05_BYPASS"
    ] = "STANDALONE_MCP_BYPASS",
) -> OboAuthMetadata:
    """
    Decode and validate an OBO JWT token (`sub`, `scp`/`scope`, `exp`) via PyJWT.

    Raises `PermissionError` when:
    - `obo_jwt is None` and `require_jwt` is `True`
    - `obo_jwt` is empty, malformed, expired, missing `sub`, or lacks `required_scope`.
    """
    if obo_jwt is None:
        if require_jwt:
            raise PermissionError("Missing mandatory OBO JWT token")
        return OboAuthMetadata(
            obo_jwt_present=False,
            obo_jwt_verified=False,
            obo_subject=None,
            auth_mode=bypass_auth_mode,
        )

    if not isinstance(obo_jwt, str) or not obo_jwt.strip():
        raise PermissionError("Invalid OBO JWT token: empty token string.")

    try:
        payload: dict[str, Any] = jwt.decode(
            obo_jwt,
            options={"verify_signature": False, "verify_exp": True},
        )
    except jwt.PyJWTError as exc:
        raise PermissionError(f"Invalid or expired OBO JWT token: {exc}") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise PermissionError("OBO JWT token missing mandatory 'sub' claim.")

    raw_scopes = payload.get("scp", payload.get("scope", []))
    if isinstance(raw_scopes, str):
        scopes = set(raw_scopes.split())
    elif isinstance(raw_scopes, list):
        scopes = {str(item) for item in raw_scopes}
    else:
        scopes = set()

    if required_scope not in scopes:
        raise PermissionError(
            f"OBO JWT token lacks required scope '{required_scope}' (found={sorted(scopes)})."
        )

    return OboAuthMetadata(
        obo_jwt_present=True,
        obo_jwt_verified=True,
        obo_subject=sub,
        auth_mode="OBO_JWT_VERIFIED",
    )


def save_cqrs_state(
    state: CqrsRuntimeState,
    config: AppConfig,
    workspace_root: Path,
) -> Path:
    """Atomically persist validated `CqrsRuntimeState` to disk."""
    state_path = resolve_cqrs_state_path(config, workspace_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(state.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(state_path)
    return state_path


def resolve_ticket_journal_path(
    config: AppConfig, workspace_root: Path
) -> Path:
    """Resolve absolute path to `tmf621_ticket_journal.json`."""
    return workspace_root / Path(config.cqrs_action_plane.ticket_journal_path)


def load_ticket_journal(journal_path: Path) -> List[Tmf621TicketRecord]:
    """Load and validate persisted TMF621 trouble tickets from JSON."""
    if not journal_path.exists():
        return []
    raw_items = json.loads(journal_path.read_text(encoding="utf-8"))
    if not isinstance(raw_items, list):
        raise ValueError(
            f"Expected JSON list in {journal_path}, got {type(raw_items).__name__}."
        )
    return [Tmf621TicketRecord.model_validate(item) for item in raw_items]


def save_ticket_journal(
    journal_path: Path, records: List[Tmf621TicketRecord]
) -> None:
    """Atomically persist validated TMF621 trouble ticket records."""
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = journal_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps([r.model_dump() for r in records], indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(journal_path)
