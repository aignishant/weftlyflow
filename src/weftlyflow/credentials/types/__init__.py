"""Concrete credential type implementations.

Added in Phase 4:
    bearer_token.py     : ``Authorization: Bearer <token>``.
    basic_auth.py       : HTTP Basic auth (username + password).
    api_key_header.py   : API key injected as an arbitrary header.
    api_key_query.py    : API key appended as a query parameter.
    oauth2_generic.py   : OAuth2 client-credentials / auth-code flows.

Per-service OAuth2 types ship alongside their integration node.
"""

from __future__ import annotations
