"""Shared helpers used by more than one built-in node.

Kept deliberately tiny. Functions that are only used inside a single node
package must live in that package, not here — this module is the bar for
"multiple nodes need this".
"""

from __future__ import annotations

from weftlyflow.nodes.utils.paths import del_path, get_path, set_path
from weftlyflow.nodes.utils.predicates import (
    PREDICATE_OPERATORS,
    PredicateOperator,
    evaluate_predicate,
)

__all__ = [
    "PREDICATE_OPERATORS",
    "PredicateOperator",
    "del_path",
    "evaluate_predicate",
    "get_path",
    "set_path",
]
