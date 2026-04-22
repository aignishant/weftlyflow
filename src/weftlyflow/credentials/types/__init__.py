"""Concrete credential type implementations.

    bearer_token.py     : ``Authorization: Bearer <token>``.
    basic_auth.py       : HTTP Basic auth (username + password).
    api_key_header.py   : API key injected as an arbitrary header.
    api_key_query.py    : API key appended as a query parameter.
    oauth2_generic.py   : OAuth2 auth-code flow, stores tokens.
    slack_api.py        : Slack Web API bot/user token.
    slack_oauth2.py     : Slack OAuth2 install — pre-filled endpoints + scopes.

Per-service OAuth2 types ship alongside their integration node.
"""

from __future__ import annotations

from weftlyflow.credentials.types.api_key_header import ApiKeyHeaderCredential
from weftlyflow.credentials.types.api_key_query import ApiKeyQueryCredential
from weftlyflow.credentials.types.basic_auth import BasicAuthCredential
from weftlyflow.credentials.types.bearer_token import BearerTokenCredential
from weftlyflow.credentials.types.oauth2_generic import OAuth2GenericCredential
from weftlyflow.credentials.types.slack_api import SlackApiCredential
from weftlyflow.credentials.types.slack_oauth2 import SlackOAuth2Credential

__all__ = [
    "ApiKeyHeaderCredential",
    "ApiKeyQueryCredential",
    "BasicAuthCredential",
    "BearerTokenCredential",
    "OAuth2GenericCredential",
    "SlackApiCredential",
    "SlackOAuth2Credential",
]
