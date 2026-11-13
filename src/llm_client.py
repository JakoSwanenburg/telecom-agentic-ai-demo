"""
Shared Multi-Model `google-genai` Client & Schema Utilities.

Provides:
- Per-component Gemini model resolution (`config.ai.component_models` with fallback to
  `config.ai.model_name`) so each solution component can use a distinct Gemini model.
- Shared `google.genai.Client` initialization (`GEMINI_API_KEY` if set, otherwise
  Vertex AI with local `gcloud` OAuth2 token or ADC).
- Recursive JSON Schema sanitizer (`strip_unsupported_vertex_schema_keys`) for
  Vertex AI constrained-decoding OpenAPI compatibility.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

from google import genai
from google.oauth2.credentials import Credentials as OAuth2Credentials

from src.models import AppConfig

UNSUPPORTED_VERTEX_SCHEMA_KEYS = {
    "additionalProperties",
    "default",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
}


def strip_unsupported_vertex_schema_keys(schema_node: Any) -> Any:
    """
    Recursively remove JSON Schema validation keywords unsupported by Vertex AI's
    constrained-decoding OpenAPI parser (`additionalProperties`, `default`, `minItems`,
    `minLength`, etc.) while preserving structural types, required fields, enums,
    and descriptions. Full Pydantic v2 validation is enforced after decoding via
    `Model.model_validate_json(response.text)`.
    """
    if isinstance(schema_node, dict):
        cleaned: Dict[str, Any] = {}
        for key, value in schema_node.items():
            if key in UNSUPPORTED_VERTEX_SCHEMA_KEYS:
                continue
            cleaned[key] = strip_unsupported_vertex_schema_keys(value)
        return cleaned
    if isinstance(schema_node, list):
        return [strip_unsupported_vertex_schema_keys(item) for item in schema_node]
    return schema_node


def resolve_gcloud_access_token(account: str = "j.swanenburg@planet.nl") -> Optional[str]:
    """
    Obtain a short-lived OAuth2 access token from `gcloud auth print-access-token`
    for local development when Application Default Credentials are not active.
    """
    gcloud_bin = shutil.which("gcloud.cmd") or shutil.which("gcloud")
    if not gcloud_bin:
        return None
    try:
        proc = subprocess.run(
            [gcloud_bin, "auth", "print-access-token", f"--account={account}", "--quiet"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        return None
    return None


def resolve_model_for_component(config: AppConfig, component_name: str) -> str:
    """
    Resolve the configured Gemini model ID for a specific solution component.

    Checks `config.ai.component_models[component_name]` first, falling back to
    `config.ai.model_name` if not explicitly overridden. Fails fast if empty.
    """
    component_model = config.ai.component_models.get(component_name, "").strip()
    if component_model:
        return component_model
    default_model = config.ai.model_name.strip()
    if not default_model:
        raise ValueError(
            f"No Gemini model configured for component '{component_name}' and "
            "config.ai.model_name is empty."
        )
    return default_model


def create_genai_client(config: AppConfig, logger: logging.Logger) -> genai.Client:
    """
    Create a `google.genai.Client`:
      - If `GEMINI_API_KEY` is set in environment variables, use it.
      - Otherwise, use Vertex AI (`vertexai=True`) against `config.gcp.project_id`
        and `config.ai.location`.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        logger.info("Initializing google-genai client via GEMINI_API_KEY")
        return genai.Client(api_key=api_key)

    logger.info(
        "GEMINI_API_KEY not set; initializing google-genai client via Vertex AI "
        "(project=%s, location=%s)",
        config.gcp.project_id,
        config.ai.location,
    )
    if config.project.environment == "local":
        token = resolve_gcloud_access_token("j.swanenburg@planet.nl")
        if token:
            creds = OAuth2Credentials(
                token=token,
                quota_project_id=config.gcp.project_id,
            )
            return genai.Client(
                vertexai=True,
                project=config.gcp.project_id,
                location=config.ai.location,
                credentials=creds,
            )

    return genai.Client(
        vertexai=True,
        project=config.gcp.project_id,
        location=config.ai.location,
    )

