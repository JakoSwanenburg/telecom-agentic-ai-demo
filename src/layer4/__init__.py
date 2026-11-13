"""
Layer 4: Deterministic R2RML-to-SQLite Pushdown Compiler & Federated Multi-Graph Executor.
"""

from src.layer4.r2rml_sqlite_compiler import (
    GRAPH_VIRTUAL_IB,
    compile_r2rml_to_virtual_graph,
    validate_layer4_prerequisites,
)
from src.layer4.federated_executor import (
    execute_readonly_sparql,
    query_federated_circuit_context,
)

__all__ = [
    "GRAPH_VIRTUAL_IB",
    "compile_r2rml_to_virtual_graph",
    "execute_readonly_sparql",
    "query_federated_circuit_context",
    "validate_layer4_prerequisites",
]

