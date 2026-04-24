"""Expression engine — resolves ``{{ ... }}`` templates against the run context.

Weftlyflow expressions are a **restricted Python** subset, not a bespoke language.
We reuse the Python parser (via RestrictedPython) with a hardened globals dict
that exposes only the intentional proxies (``$json``, ``$input``, ``$now``, etc.)
and a small allow-list of builtins.

Modules:
    tokenizer  : split a template into literal + expression chunks.
    sandbox    : RestrictedPython compile + guarded eval.
    resolver   : glue between tokenizer, sandbox, and proxies.
    proxies    : the ``$``-prefixed objects exposed in expressions.
    errors     : re-exports of the expression-family exceptions.

See weftlyinfo.md §10.
"""

from __future__ import annotations

from weftlyflow.expression.errors import (
    ExpressionError,
    ExpressionEvalError,
    ExpressionSecurityError,
    ExpressionSyntaxError,
    ExpressionTimeoutError,
)
from weftlyflow.expression.proxies import (
    InputProxy,
    WeftlyflowDateTime,
    build_proxies,
    filter_env,
)
from weftlyflow.expression.resolver import clear_cache, resolve, resolve_tree
from weftlyflow.expression.tokenizer import (
    ExpressionChunk,
    LiteralChunk,
    contains_expression,
    is_single_expression,
    tokenize,
)

__all__ = [
    "ExpressionChunk",
    "ExpressionError",
    "ExpressionEvalError",
    "ExpressionSecurityError",
    "ExpressionSyntaxError",
    "ExpressionTimeoutError",
    "InputProxy",
    "LiteralChunk",
    "WeftlyflowDateTime",
    "build_proxies",
    "clear_cache",
    "contains_expression",
    "filter_env",
    "is_single_expression",
    "resolve",
    "resolve_tree",
    "tokenize",
]
