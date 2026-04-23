"""Elasticsearch API credential — ``Authorization: ApiKey <base64(id:key)>``.

Elasticsearch (https://www.elastic.co/guide/en/elasticsearch/reference/
current/security-api-create-api-key.html) uses a *prefixed* token that
is itself a colon-encoded base64 of ``<id>:<api_key>``. The header
reads ``Authorization: ApiKey <b64(id:key)>`` — distinct from Basic
auth (``Basic`` prefix), Bearer, or raw-token schemes.

Every deployment lives at its own URL (self-hosted on-prem, Elastic
Cloud, or an ECK-managed cluster), so the credential carries both the
encoded key and the base URL.

The self-test calls ``GET /`` which every Elasticsearch node responds
to with ``cluster_name`` / ``version`` info.
"""

from __future__ import annotations

from base64 import b64encode
from typing import Any, ClassVar

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_PATH: str = "/"
_TEST_TIMEOUT_SECONDS: float = 10.0


def base_url_from(raw_base_url: str) -> str:
    """Normalize ``raw_base_url`` to ``<scheme>://<host>[:port]`` (no trailing slash)."""
    cleaned = raw_base_url.strip().rstrip("/")
    if not cleaned:
        msg = "Elasticsearch: 'base_url' is required"
        raise ValueError(msg)
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    return cleaned


def api_key_header(api_key_id: str, api_key: str) -> str:
    """Return the ``Authorization`` header value for an ``id``/``key`` pair."""
    pair = f"{api_key_id}:{api_key}".encode()
    return "ApiKey " + b64encode(pair).decode("ascii")


class ElasticsearchApiCredential(BaseCredentialType):
    """Inject ``Authorization: ApiKey <b64(id:key)>`` on every request."""

    slug: ClassVar[str] = "weftlyflow.elasticsearch_api"
    display_name: ClassVar[str] = "Elasticsearch API"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://www.elastic.co/guide/en/elasticsearch/reference/"
        "current/security-api-create-api-key.html"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="api_key_id",
            display_name="API Key ID",
            type="string",
            required=True,
            description="`id` component of the Elasticsearch API key.",
        ),
        PropertySchema(
            name="api_key",
            display_name="API Key",
            type="string",
            required=True,
            description="`api_key` component (the secret half).",
            type_options={"password": True},
        ),
        PropertySchema(
            name="base_url",
            display_name="Base URL",
            type="string",
            required=True,
            description="Cluster URL, e.g. 'https://my-deployment.es.us-east-1.aws.found.io:9243'.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Set ``Authorization: ApiKey <b64(id:key)>`` on ``request``."""
        key_id = str(creds.get("api_key_id", "")).strip()
        secret = str(creds.get("api_key", "")).strip()
        request.headers["Authorization"] = api_key_header(key_id, secret)
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``GET /`` on the cluster and report."""
        key_id = str(creds.get("api_key_id") or "").strip()
        secret = str(creds.get("api_key") or "").strip()
        if not key_id:
            return CredentialTestResult(ok=False, message="api_key_id is empty")
        if not secret:
            return CredentialTestResult(ok=False, message="api_key is empty")
        try:
            base = base_url_from(str(creds.get("base_url") or ""))
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{base}{_TEST_PATH}",
                    headers={
                        "Authorization": api_key_header(key_id, secret),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"elasticsearch rejected key: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = ElasticsearchApiCredential
