"""Expression engine — resolves ``{{ ... }}`` templates against the run context.

Weftlyflow expressions are a **restricted Python** subset, not a bespoke language.
We reuse the Python parser (via RestrictedPython) with a hardened globals dict
that exposes only the intentional proxies (``$json``, ``$input``, ``$now``, etc.)
and a small allow-list of builtins.

Modules (populated in Phase 4):
    tokenizer  : split a template into literal + expression chunks.
    sandbox    : RestrictedPython compile + guarded eval.
    resolver   : glue between tokenizer, sandbox, and proxies.
    proxies    : the ``$``-prefixed objects exposed in expressions.
    extensions : tasteful helper methods on strings/lists/dates.

See IMPLEMENTATION_BIBLE.md §10 and `memory/cheatsheet_restrictedpython.md`.
"""

from __future__ import annotations
