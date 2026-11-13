"""
Southbound FastMCP Server: `tmf621-trouble-ticket-mcp` (Step 8 / IMP-010).

Exposes `create_or_update_trouble_ticket` with deterministic pre-commit `pySHACL`
validation against `shapes/trouble_ticket_shape.ttl` before persisting to
`data/cqrs_state/tmf621_ticket_journal.json`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pyshacl
from mcp.server.mcpserver import MCPServer
from rdflib import Graph, Literal, Namespace, RDF, URIRef, XSD

from src.mcp_servers.common import (
    load_ticket_journal,
    resolve_mcp_context,
    resolve_ticket_journal_path,
    save_cqrs_state,
    save_ticket_journal,
    utc_now_iso,
    validate_obo_jwt,
)
from src.models import AppConfig, Tmf621TicketRecord, Tmf621TicketResponse
from src.state_manager import load_cqrs_state

mcp = MCPServer("tmf621-trouble-ticket-mcp")

TMF = Namespace("http://tmforum.org/sid/")
TELCO = Namespace("http://telco.enterprise.org/ontology/")


def _to_urn(value: str, default_prefix: str) -> URIRef:
    """Format an identifier as a URN IRI if it is not already a `urn:` URI."""
    cleaned = value.strip()
    if cleaned.startswith("urn:") or cleaned.startswith("http://") or cleaned.startswith("https://"):
        return URIRef(cleaned)
    return URIRef(f"{default_prefix}{cleaned}")


def _build_ticket_rdf_graph(
    ticket_id: str,
    circuit_id: str,
    severity: str,
    status: str,
    affected_resource_id: Optional[str],
) -> tuple[URIRef, Graph]:
    """Build an in-memory RDF graph for `tmf:TroubleTicket` without fabricating missing fields."""
    graph = Graph()
    graph.bind("tmf", TMF)
    graph.bind("telco", TELCO)

    ticket_uri = URIRef(f"urn:telco:ticket:{ticket_id}")
    graph.add((ticket_uri, RDF.type, TMF.TroubleTicket))
    graph.add((ticket_uri, TMF.ticketId, Literal(ticket_id, datatype=XSD.string)))

    if isinstance(severity, str) and severity.strip():
        graph.add((ticket_uri, TMF.severity, Literal(severity.strip())))
    if isinstance(status, str) and status.strip():
        graph.add((ticket_uri, TMF.status, Literal(status.strip(), datatype=XSD.string)))
    if isinstance(circuit_id, str) and circuit_id.strip():
        graph.add((ticket_uri, TELCO.affectedCircuit, _to_urn(circuit_id, "urn:telco:circuit:")))
    if isinstance(affected_resource_id, str) and affected_resource_id.strip():
        graph.add(
            (
                ticket_uri,
                TELCO.affectedResource,
                _to_urn(affected_resource_id, "urn:telco:resource:"),
            )
        )

    return ticket_uri, graph


def execute_create_or_update_trouble_ticket(
    circuit_id: str,
    customer_id: str,
    severity: str,
    status: str,
    resolution_action: str,
    summary: str,
    affected_resource_id: Optional[str] = None,
    external_ticket_id: Optional[str] = None,
    obo_jwt: Optional[str] = None,
    config: Optional[AppConfig] = None,
    logger: Optional[logging.Logger] = None,
    root_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Core implementation for `create_or_update_trouble_ticket` with pre-commit pySHACL gate."""
    workspace_root, active_config, active_logger = resolve_mcp_context(
        config=config,
        logger=logger,
        root_dir=root_dir,
        logger_name="telco_agent.mcp.tmf621_trouble_ticket",
    )
    auth = validate_obo_jwt(
        obo_jwt=obo_jwt,
        required_scope=active_config.mcp_servers.tmf621_trouble_ticket.required_obo_scope,
        require_jwt=active_config.mcp_servers.require_obo_jwt,
    )

    shape_path = workspace_root / Path(
        active_config.mcp_servers.tmf621_trouble_ticket.shacl_shape_path
    )
    if not shape_path.exists():
        raise FileNotFoundError(
            f"TMF621 TroubleTicket SHACL shape not found at {shape_path}."
        )

    state = load_cqrs_state(active_config, workspace_root)
    journal_path = resolve_ticket_journal_path(active_config, workspace_root)
    journal = load_ticket_journal(journal_path)

    existing_idx: Optional[int] = None
    if isinstance(external_ticket_id, str) and external_ticket_id.strip():
        clean_ext_id = external_ticket_id.strip()
        for idx, rec in enumerate(journal):
            if rec.ticket_id == clean_ext_id or rec.external_ticket_id == clean_ext_id:
                existing_idx = idx
                break

    ticket_id = (
        journal[existing_idx].ticket_id
        if existing_idx is not None
        else (
            external_ticket_id.strip()
            if isinstance(external_ticket_id, str) and external_ticket_id.strip()
            else f"TT-621-{len(journal) + 1:04d}"
        )
    )

    ticket_uri, data_graph = _build_ticket_rdf_graph(
        ticket_id=ticket_id,
        circuit_id=circuit_id,
        severity=severity,
        status=status,
        affected_resource_id=affected_resource_id,
    )
    shacl_graph = Graph().parse(shape_path, format="turtle")
    conforms, _, results_text = pyshacl.validate(
        data_graph,
        shacl_graph=shacl_graph,
        inference="none",
        abort_on_first=False,
    )

    if not conforms:
        active_logger.warning(
            "tmf621_trouble_ticket_mcp | REJECTED_SHACL_VIOLATION for ticket=%s | %s",
            ticket_id,
            results_text.strip(),
        )
        return Tmf621TicketResponse(
            persisted=False,
            status="REJECTED_SHACL_VIOLATION",
            shacl_conforms=False,
            explanation=results_text.strip(),
            ticket=None,
            tmf621_tickets_count=state.tmf621_tickets_count,
            auth=auth,
        ).model_dump()

    if not isinstance(customer_id, str) or not customer_id.strip():
        raise ValueError("customer_id must be a non-empty string.")
    if not isinstance(resolution_action, str) or not resolution_action.strip():
        raise ValueError("resolution_action must be a non-empty string.")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary must be a non-empty string.")

    now_utc = utc_now_iso()
    created_at = (
        journal[existing_idx].created_at_utc if existing_idx is not None else now_utc
    )
    record = Tmf621TicketRecord(
        ticket_id=ticket_id,
        ticket_uri=str(ticket_uri),
        circuit_id=circuit_id.strip(),
        customer_id=customer_id.strip(),
        affected_resource_id=str(affected_resource_id).strip(),
        severity=severity.strip(),
        status=status.strip(),
        resolution_action=resolution_action.strip(),
        summary=summary.strip(),
        external_ticket_id=external_ticket_id.strip()
        if isinstance(external_ticket_id, str) and external_ticket_id.strip()
        else None,
        created_at_utc=created_at,
        updated_at_utc=now_utc,
        shacl_conforms=True,
    )

    if existing_idx is not None:
        journal[existing_idx] = record
        op_status = "UPDATED"
        new_tickets_count = state.tmf621_tickets_count
        new_tickets_created = state.tickets_created
    else:
        journal.append(record)
        op_status = "CREATED"
        new_tickets_count = state.tmf621_tickets_count + 1
        new_tickets_created = state.tickets_created + 1

    save_ticket_journal(journal_path, journal)
    updated_state = state.model_copy(
        update={
            "tmf621_tickets_count": new_tickets_count,
            "tickets_created": new_tickets_created,
        }
    )
    save_cqrs_state(updated_state, active_config, workspace_root)

    explanation = (
        f"{op_status} TMF621 TroubleTicket {record.ticket_id} ({record.severity} / {record.status}) "
        f"for circuit {record.circuit_id} and resource {record.affected_resource_id}; pySHACL conforms=True."
    )
    active_logger.info(
        "tmf621_trouble_ticket_mcp | %s | tickets=%d | auth=%s",
        explanation,
        new_tickets_count,
        auth.auth_mode,
    )
    return Tmf621TicketResponse(
        persisted=True,
        status=op_status,
        shacl_conforms=True,
        explanation=explanation,
        ticket=record,
        tmf621_tickets_count=new_tickets_count,
        auth=auth,
    ).model_dump()


@mcp.tool()
def create_or_update_trouble_ticket(
    circuit_id: str,
    customer_id: str,
    severity: str,
    status: str,
    resolution_action: str,
    summary: str,
    affected_resource_id: Optional[str] = None,
    external_ticket_id: Optional[str] = None,
    obo_jwt: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate via pySHACL and create/update a TMF621 Trouble Ticket in the CQRS journal."""
    return execute_create_or_update_trouble_ticket(
        circuit_id=circuit_id,
        customer_id=customer_id,
        severity=severity,
        status=status,
        resolution_action=resolution_action,
        summary=summary,
        affected_resource_id=affected_resource_id,
        external_ticket_id=external_ticket_id,
        obo_jwt=obo_jwt,
    )


if __name__ == "__main__":
    mcp.run()
