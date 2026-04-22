"""Expression-engine exception hierarchy.

Re-exports the canonical classes from :mod:`weftlyflow.domain.errors` so
call sites can write ``from weftlyflow.expression.errors import ...`` without
reaching into the domain package. The domain module is the single source of
truth — do not redefine these classes here.
"""

from __future__ import annotations

from weftlyflow.domain.errors import (
    ExpressionError,
    ExpressionEvalError,
    ExpressionSecurityError,
    ExpressionSyntaxError,
    ExpressionTimeoutError,
)

__all__ = [
    "ExpressionError",
    "ExpressionEvalError",
    "ExpressionSecurityError",
    "ExpressionSyntaxError",
    "ExpressionTimeoutError",
]
