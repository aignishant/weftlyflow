"""Azure Storage credential — SharedKey HMAC-SHA256 with canonicalization.

Azure Blob/Queue/Table/File services
(https://learn.microsoft.com/rest/api/storageservices/authorize-with-shared-key)
accept a unique ``Authorization: SharedKey <account>:<signature>``
header where the signature is ``base64(HMAC-SHA256(base64_decode(key),
StringToSign))``. The string-to-sign concatenates 12 ordered request
headers (many often empty), a canonicalized ``x-ms-*`` header list
sorted lexicographically, and a canonicalized resource string that
combines the account name, the URL path, and sorted query params.

The algorithm is materially different from AWS SigV4 (no derived
key chain, no region/service scope, no payload hash) and from the
HMAC-SHA256 schemes already in the catalog (Coinbase's four-field
string, Binance's query string, NetSuite's OAuth 1.0a) — hence its
own credential.

:meth:`inject` stamps ``x-ms-date`` and ``x-ms-version`` before
signing so the caller does not need to remember either.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import hashlib
import hmac
from email.utils import format_datetime
from typing import Any, ClassVar, Final
from urllib.parse import parse_qsl, unquote

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_DEFAULT_API_VERSION: Final[str] = "2023-11-03"
_TEST_TIMEOUT_SECONDS: Final[float] = 15.0

# The twelve fixed header slots in SharedKey StringToSign, in order.
_STANDARD_HEADERS: Final[tuple[str, ...]] = (
    "content-encoding",
    "content-language",
    "content-length",
    "content-md5",
    "content-type",
    "date",
    "if-modified-since",
    "if-match",
    "if-none-match",
    "if-unmodified-since",
    "range",
)


def _http_date(now: _dt.datetime | None = None) -> str:
    """Return the current time as an RFC 1123 HTTP date in GMT."""
    value = now or _dt.datetime.now(tz=_dt.UTC)
    return format_datetime(value.astimezone(_dt.UTC), usegmt=True)


def _canonical_headers(headers: dict[str, str]) -> str:
    """Return the canonicalized ``x-ms-*`` header block."""
    ms_headers: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        if not key.startswith("x-ms-"):
            continue
        cleaned = " ".join(value.split()).strip()
        ms_headers[key] = cleaned
    lines = [f"{k}:{ms_headers[k]}" for k in sorted(ms_headers)]
    return "\n".join(lines) + ("\n" if lines else "")


def _canonical_resource(
    *, account_name: str, path: str, query: str,
) -> str:
    r"""Return the canonicalized resource — ``/<account><path>\n<query-block>``."""
    clean_path = path if path.startswith("/") else f"/{path}"
    resource = f"/{account_name}{unquote(clean_path)}"
    if not query:
        return resource
    grouped: dict[str, list[str]] = {}
    for raw_key, raw_value in parse_qsl(query, keep_blank_values=True):
        key = raw_key.lower()
        grouped.setdefault(key, []).append(raw_value)
    lines: list[str] = []
    for key in sorted(grouped):
        joined = ",".join(sorted(grouped[key]))
        lines.append(f"{key}:{joined}")
    return resource + "\n" + "\n".join(lines)


def build_string_to_sign(
    *,
    method: str,
    account_name: str,
    path: str,
    query: str,
    headers: dict[str, str],
    content_length: int,
) -> str:
    """Return the SharedKey StringToSign for the given request components.

    Args:
        method: Upper-case HTTP verb.
        account_name: Storage account name — prepended to the resource string.
        path: Request URL path, starting with ``/``.
        query: Raw query string (without leading ``?``).
        headers: Outgoing request headers (case-insensitive).
        content_length: Number of body bytes. Emit an empty string when zero —
            required for API versions 2015-02-21 and later.
    """
    lowered = {name.lower(): value for name, value in headers.items()}
    length_field = "" if content_length == 0 else str(content_length)
    values: list[str] = [method.upper()]
    for key in _STANDARD_HEADERS:
        if key == "content-length":
            values.append(length_field)
            continue
        values.append(lowered.get(key, ""))
    prefix = "\n".join(values) + "\n"
    return (
        prefix
        + _canonical_headers(headers)
        + _canonical_resource(
            account_name=account_name, path=path, query=query,
        )
    )


def sign_string(string_to_sign: str, account_key: str) -> str:
    """Return ``base64(HMAC-SHA256(base64_decode(account_key), ...))``."""
    try:
        key_bytes = base64.b64decode(account_key, validate=True)
    except (ValueError, binascii.Error) as exc:
        msg = "Azure: account_key must be base64-encoded"
        raise ValueError(msg) from exc
    digest = hmac.new(
        key_bytes, string_to_sign.encode("utf-8"), hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def authorize_request(
    request: httpx.Request,
    *,
    account_name: str,
    account_key: str,
    api_version: str = _DEFAULT_API_VERSION,
    now: _dt.datetime | None = None,
) -> httpx.Request:
    """Stamp required headers and attach the SharedKey Authorization.

    Mutates ``request`` in place so it can be reused inside
    :class:`httpx.Auth` subclasses or a credential ``inject`` override.
    """
    request.headers.setdefault("x-ms-date", _http_date(now))
    request.headers.setdefault("x-ms-version", api_version)
    body = request.content or b""
    string_to_sign = build_string_to_sign(
        method=request.method,
        account_name=account_name,
        path=request.url.path,
        query=request.url.query.decode()
        if isinstance(request.url.query, bytes)
        else request.url.query,
        headers=dict(request.headers),
        content_length=len(body),
    )
    signature = sign_string(string_to_sign, account_key)
    request.headers["Authorization"] = f"SharedKey {account_name}:{signature}"
    return request


def blob_host_for(account_name: str) -> str:
    """Return the Blob-service host for ``account_name``."""
    return f"https://{account_name}.blob.core.windows.net"


class AzureStorageSharedKeyCredential(BaseCredentialType):
    """Sign every request with ``SharedKey <account>:<HMAC-SHA256 sig>``."""

    slug: ClassVar[str] = "weftlyflow.azure_storage_shared_key"
    display_name: ClassVar[str] = "Azure Storage (Shared Key)"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://learn.microsoft.com/rest/api/storageservices/authorize-with-shared-key"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="account_name",
            display_name="Storage Account Name",
            type="string",
            required=True,
            description="Storage account name — the first segment of every host.",
        ),
        PropertySchema(
            name="account_key",
            display_name="Account Key (base64)",
            type="string",
            required=True,
            type_options={"password": True, "rows": 4},
            description="Base64-encoded 512-bit account key (from the Access keys blade).",
        ),
        PropertySchema(
            name="api_version",
            display_name="x-ms-version",
            type="string",
            default=_DEFAULT_API_VERSION,
            description="REST API version date — stamped into x-ms-version.",
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Sign ``request`` in place with the SharedKey scheme."""
        account_name = str(creds.get("account_name", "")).strip()
        account_key = str(creds.get("account_key", "")).strip()
        api_version = str(creds.get("api_version") or _DEFAULT_API_VERSION).strip()
        return authorize_request(
            request,
            account_name=account_name,
            account_key=account_key,
            api_version=api_version,
        )

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call Blob service ``?comp=list`` and report the outcome."""
        account_name = str(creds.get("account_name") or "").strip()
        account_key = str(creds.get("account_key") or "").strip()
        if not account_name or not account_key:
            return CredentialTestResult(
                ok=False, message="account_name and account_key are required",
            )
        url = f"{blob_host_for(account_name)}/?comp=list"
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                request = client.build_request("GET", url)
                signed = await self.inject(creds, request)
                response = await client.send(signed)
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        except ValueError as exc:
            return CredentialTestResult(ok=False, message=str(exc))
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=(
                    f"azure rejected credentials: HTTP {response.status_code}"
                ),
            )
        return CredentialTestResult(ok=True, message="azure credentials valid")


TYPE = AzureStorageSharedKeyCredential
