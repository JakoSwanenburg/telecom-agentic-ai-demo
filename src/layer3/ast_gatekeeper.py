"""
Static rdflib AST Security Gatekeeper & Closed-Vocabulary TBox Validator (Step 6 / Layer 3).

Deterministically validates SPARQL queries before execution against Layer 4:
1. Blocks SPARQL UPDATE mutation keywords (INSERT, DELETE, DROP, CLEAR, LOAD, CREATE, MOVE, COPY, ADD).
2. Detects physical SQL table/column leakage via generic structural patterns (zero hardcoded SQL names).
3. Parses the query via rdflib's SPARQL parser + algebra translator to enforce read-only query types.
4. Enforces closed-vocabulary validation against the SID/eTOM TBox (and promoted TriG vocabulary).
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any, Iterable, Optional, Set

from rdflib import Dataset, Graph, URIRef
from rdflib.paths import Path as RdflibPath
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery

from src.models import SparqlAstAuditResult

_TMF_NS = "http://tmforum.org/sid/"
_TELCO_NS = "http://telco.enterprise.org/ontology/"

_MUTATION_KEYWORD_RE = re.compile(
    r"\b(INSERT|DELETE|DROP|CLEAR|LOAD|CREATE|MOVE|COPY|ADD)\b",
    re.IGNORECASE,
)

# Generic physical-SQL leakage patterns (no hardcoded table or column names)
_SQL_LEAKAGE_PATTERNS = (
    re.compile(r"\bT_[A-Z0-9_]+\b"),
    re.compile(r"\bPRAGMA\b", re.IGNORECASE),
    re.compile(r"\bSQLITE_MASTER\b", re.IGNORECASE),
    re.compile(r"\bROWID\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_]+_SURR_ID\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_]+_ROW_ID\b", re.IGNORECASE),
)

_ALLOWED_READ_QUERY_ALGEBRA_TYPES = frozenset(
    {"SelectQuery", "AskQuery", "ConstructQuery", "DescribeQuery"}
)

# Virtual-graph predicate projected dynamically by Layer 4 R2RML-to-SQLite compiler
_LAYER4_VIRTUAL_PREDICATES = frozenset({f"{_TELCO_NS}cpeModelSku"})


def _strip_comments_and_strings(query_text: str) -> str:
    """Remove SPARQL comments and string literals prior to keyword scanning."""
    no_comments = re.sub(r"#[^\n]*", " ", query_text)
    return re.sub(
        r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"]*"|\'[^\']*\'',
        " ",
        no_comments,
    )


def _collect_vocabulary_uris(
    tbox_path: Path,
    trig_path: Optional[Path] = None,
) -> Set[str]:
    """Load allowed `tmf:` and `telco:` URIRefs from the TBox (and optional TriG store)."""
    if not tbox_path.exists():
        raise FileNotFoundError(f"TBox file not found for AST validation: {tbox_path}")

    allowed: Set[str] = set(_LAYER4_VIRTUAL_PREDICATES)
    tbox_graph = Graph()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
        tbox_graph.parse(str(tbox_path), format="turtle")

    for s, p, o in tbox_graph:
        for term in (s, p, o):
            if isinstance(term, URIRef):
                uri = str(term)
                if uri.startswith(_TMF_NS) or uri.startswith(_TELCO_NS):
                    allowed.add(uri)

    if trig_path is not None and trig_path.exists():
        ds = Dataset()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
            ds.parse(str(trig_path), format="trig")
        for s, p, o, _ in ds.quads((None, None, None, None)):
            for term in (s, p, o):
                if isinstance(term, URIRef):
                    uri = str(term)
                    if uri.startswith(_TMF_NS) or uri.startswith(_TELCO_NS):
                        allowed.add(uri)

    return allowed


def _walk_algebra_uris(node: Any, collected: Set[str]) -> None:
    """Recursively collect all URIRefs from an rdflib SPARQL algebra tree."""
    if isinstance(node, URIRef):
        collected.add(str(node))
        return
    if isinstance(node, RdflibPath):
        for attr in ("args", "path"):
            sub = getattr(node, attr, None)
            if sub is not None:
                _walk_algebra_uris(sub, collected)
        return
    if isinstance(node, dict):
        for val in node.values():
            _walk_algebra_uris(val, collected)
        return
    if isinstance(node, (list, tuple, set, frozenset)):
        for item in node:
            _walk_algebra_uris(item, collected)
        return
    if hasattr(node, "items"):
        for _, val in node.items():
            _walk_algebra_uris(val, collected)


def _find_sql_leakage(query_text: str) -> Iterable[str]:
    """Return unique generic SQL leakage tokens found in query text."""
    seen: Set[str] = set()
    ordered: list[str] = []
    for pattern in _SQL_LEAKAGE_PATTERNS:
        for match in pattern.finditer(query_text):
            token = match.group(0)
            if token not in seen:
                seen.add(token)
                ordered.append(token)
    return ordered


def validate_sparql_ast(
    query_text: str,
    tbox_path: Path,
    trig_path: Optional[Path] = None,
) -> SparqlAstAuditResult:
    """
    Statically validate a SPARQL query using rdflib's parser/algebra and closed-vocabulary TBox checks.
    """
    stripped = _strip_comments_and_strings(query_text)
    blocked_mutations = sorted(
        {m.group(1).upper() for m in _MUTATION_KEYWORD_RE.finditer(stripped)}
    )
    sql_leakage_matches = list(_find_sql_leakage(query_text))

    if blocked_mutations:
        return SparqlAstAuditResult(
            passed=False,
            query_type="MUTATION_BLOCKED",
            blocked_mutations=blocked_mutations,
            sql_leakage_matches=sql_leakage_matches,
            unknown_uris=[],
            syntax_error=f"Blocked SPARQL mutation keywords: {', '.join(blocked_mutations)}",
            checked_uris_count=0,
        )

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"^rdflib\.")
            parsed = parseQuery(query_text)
            algebra = translateQuery(parsed)
    except Exception as exc:
        return SparqlAstAuditResult(
            passed=False,
            query_type=None,
            blocked_mutations=[],
            sql_leakage_matches=sql_leakage_matches,
            unknown_uris=[],
            syntax_error=f"SPARQL parse/algebra error: {exc}",
            checked_uris_count=0,
        )

    query_type = getattr(algebra.algebra, "name", None)
    if query_type not in _ALLOWED_READ_QUERY_ALGEBRA_TYPES:
        return SparqlAstAuditResult(
            passed=False,
            query_type=str(query_type),
            blocked_mutations=[],
            sql_leakage_matches=sql_leakage_matches,
            unknown_uris=[],
            syntax_error=f"Disallowed SPARQL algebra type: {query_type}",
            checked_uris_count=0,
        )

    referenced_uris: Set[str] = set()
    _walk_algebra_uris(algebra.algebra, referenced_uris)

    allowed_vocab = _collect_vocabulary_uris(tbox_path=tbox_path, trig_path=trig_path)
    domain_uris = sorted(
        uri
        for uri in referenced_uris
        if uri.startswith(_TMF_NS) or uri.startswith(_TELCO_NS)
    )
    unknown_uris = [uri for uri in domain_uris if uri not in allowed_vocab]

    passed = (
        len(blocked_mutations) == 0
        and len(sql_leakage_matches) == 0
        and len(unknown_uris) == 0
    )

    return SparqlAstAuditResult(
        passed=passed,
        query_type=str(query_type),
        blocked_mutations=blocked_mutations,
        sql_leakage_matches=sql_leakage_matches,
        unknown_uris=unknown_uris,
        syntax_error=None,
        checked_uris_count=len(domain_uris),
    )

