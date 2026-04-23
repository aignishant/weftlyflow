"""AWS S3 credential — SigV4 request signing (access key + secret + region).

Unlike every other credential in the catalog, AWS S3 does *not* use a
static token or header pair. It uses **Signature Version 4**
(https://docs.aws.amazon.com/general/latest/gr/sigv4_signing.html), an
HMAC-SHA256 chain over a canonical request string, a string-to-sign,
and a multi-step derived signing key (``kDate → kRegion → kService →
kSigning``). Each request's signature is unique to its path, headers,
payload hash, and timestamp, so signing happens at request time rather
than at credential-store time.

This credential therefore carries the three long-lived inputs
(``access_key_id``, ``secret_access_key``, ``region``) plus an
optional session token for STS-issued credentials. The
:meth:`sign` helper is the authoritative entry point used by the S3
node; :meth:`inject` delegates to it so the credential can also be
used by the generic HTTP Request node with ``auth_type='sigv4'``.

The self-test calls ``GET /`` on the regional endpoint (``ListBuckets``)
which returns 200 with the caller's bucket list on valid credentials
and 403 on invalid ones.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
from typing import Any, ClassVar
from urllib.parse import quote, urlencode

import httpx

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_SERVICE: str = "s3"
_ALGORITHM: str = "AWS4-HMAC-SHA256"
_UNSIGNED_PAYLOAD: str = "UNSIGNED-PAYLOAD"
_TEST_TIMEOUT_SECONDS: float = 10.0


def regional_host(region: str, *, bucket: str | None = None) -> str:
    """Return the virtual-host S3 endpoint for ``region`` and optional ``bucket``.

    * ``us-east-1`` -> ``s3.amazonaws.com`` (legacy default).
    * ``<region>`` -> ``s3.<region>.amazonaws.com``.
    * with ``bucket`` -> ``<bucket>.s3.<region>.amazonaws.com``.
    """
    cleaned = region.strip().lower()
    if not cleaned:
        msg = "AWS S3: 'region' is required"
        raise ValueError(msg)
    service_host = (
        "s3.amazonaws.com" if cleaned == "us-east-1"
        else f"s3.{cleaned}.amazonaws.com"
    )
    if bucket:
        return f"{bucket}.{service_host}"
    return service_host


def sign_request(
    *,
    method: str,
    host: str,
    path: str,
    query: dict[str, Any] | None,
    headers: dict[str, str],
    body: bytes,
    access_key_id: str,
    secret_access_key: str,
    region: str,
    session_token: str = "",
    now: _dt.datetime | None = None,
    sign_payload: bool = False,
) -> dict[str, str]:
    """Return signed request headers for an S3 SigV4 call.

    Builds the canonical request, string-to-sign, and derived signing
    key per the AWS SigV4 spec and returns the ``Authorization`` +
    ``x-amz-date`` + ``x-amz-content-sha256`` (+ optional
    ``x-amz-security-token``) headers to merge into the outbound
    request.
    """
    if not access_key_id or not secret_access_key:
        msg = "AWS S3: access_key_id and secret_access_key are required"
        raise ValueError(msg)
    timestamp = (now or _dt.datetime.now(tz=_dt.UTC)).replace(microsecond=0)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = timestamp.strftime("%Y%m%d")
    payload_hash = (
        hashlib.sha256(body).hexdigest() if sign_payload else _UNSIGNED_PAYLOAD
    )

    signed_headers_map: dict[str, str] = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if session_token:
        signed_headers_map["x-amz-security-token"] = session_token
    for key, value in headers.items():
        signed_headers_map[key.lower()] = str(value).strip()

    sorted_keys = sorted(signed_headers_map)
    canonical_headers = "".join(
        f"{key}:{signed_headers_map[key]}\n" for key in sorted_keys
    )
    signed_headers = ";".join(sorted_keys)

    canonical_query = _canonical_query(query or {})
    canonical_path = _canonical_path(path)
    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_path,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ],
    )

    credential_scope = f"{date_stamp}/{region}/{_SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            _ALGORITHM,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ],
    )

    signing_key = _derive_signing_key(secret_access_key, date_stamp, region)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256,
    ).hexdigest()

    authorization = (
        f"{_ALGORITHM} "
        f"Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    result = {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }
    if session_token:
        result["x-amz-security-token"] = session_token
    return result


def _derive_signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    k_date = hmac.new(
        f"AWS4{secret_key}".encode(),
        date_stamp.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, _SERVICE.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def _canonical_path(path: str) -> str:
    if not path or not path.startswith("/"):
        path = "/" + (path or "")
    return "/".join(quote(segment, safe="~") for segment in path.split("/"))


def _canonical_query(query: dict[str, Any]) -> str:
    if not query:
        return ""
    flat: list[tuple[str, str]] = []
    for key, value in query.items():
        if isinstance(value, (list, tuple)):
            flat.extend((str(key), str(v)) for v in value)
        else:
            flat.append((str(key), "" if value is None else str(value)))
    flat.sort()
    return urlencode(flat, quote_via=quote, safe="~")


class AwsS3Credential(BaseCredentialType):
    """Sign S3 requests with SigV4 (access key + secret + region)."""

    slug: ClassVar[str] = "weftlyflow.aws_s3"
    display_name: ClassVar[str] = "AWS S3"
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = (
        "https://docs.aws.amazon.com/general/latest/gr/sigv4_signing.html"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="access_key_id",
            display_name="Access Key ID",
            type="string",
            required=True,
            description="AWS access key ID (AKIA... or ASIA... for STS).",
        ),
        PropertySchema(
            name="secret_access_key",
            display_name="Secret Access Key",
            type="string",
            required=True,
            description="AWS secret access key.",
            type_options={"password": True},
        ),
        PropertySchema(
            name="region",
            display_name="Region",
            type="string",
            required=True,
            default="us-east-1",
            description="AWS region (e.g. 'us-east-1', 'eu-west-2').",
        ),
        PropertySchema(
            name="session_token",
            display_name="Session Token",
            type="string",
            required=False,
            description="STS session token (required for ASIA... keys).",
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Sign ``request`` with SigV4 and attach the auth headers."""
        body = request.content or b""
        host = request.url.host
        signed = sign_request(
            method=request.method,
            host=host,
            path=request.url.path or "/",
            query=dict(request.url.params),
            headers={},
            body=body,
            access_key_id=str(creds.get("access_key_id", "")).strip(),
            secret_access_key=str(creds.get("secret_access_key", "")).strip(),
            region=str(creds.get("region", "")).strip(),
            session_token=str(creds.get("session_token", "")).strip(),
        )
        for key, value in signed.items():
            request.headers[key] = value
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Call ``ListBuckets`` on the regional endpoint and report."""
        access_key = str(creds.get("access_key_id") or "").strip()
        secret_key = str(creds.get("secret_access_key") or "").strip()
        region = str(creds.get("region") or "").strip()
        session_token = str(creds.get("session_token") or "").strip()
        if not access_key:
            return CredentialTestResult(ok=False, message="access_key_id is empty")
        if not secret_key:
            return CredentialTestResult(
                ok=False, message="secret_access_key is empty",
            )
        if not region:
            return CredentialTestResult(ok=False, message="region is empty")
        host = regional_host(region)
        signed = sign_request(
            method="GET",
            host=host,
            path="/",
            query={},
            headers={},
            body=b"",
            access_key_id=access_key,
            secret_access_key=secret_key,
            region=region,
            session_token=session_token,
        )
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"https://{host}/", headers={**signed, "Host": host},
                )
        except httpx.HTTPError as exc:
            return CredentialTestResult(ok=False, message=f"network error: {exc}")
        if response.status_code != httpx.codes.OK:
            return CredentialTestResult(
                ok=False,
                message=f"AWS rejected signature: HTTP {response.status_code}",
            )
        return CredentialTestResult(ok=True, message="authenticated")


TYPE = AwsS3Credential
