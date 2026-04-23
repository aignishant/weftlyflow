"""AWS Secrets Manager secret provider.

Resolves references of the form ``aws:<secret-id>[#<field>]`` using the
standard boto3 SDK. The provider is behind the ``aws-secrets`` optional
dependency — importing this module without boto3 installed raises an
``ImportError`` at module load.

Reference semantics:

* ``aws:prod/slack``                 — return the raw ``SecretString``.
* ``aws:prod/slack#bot_token``       — parse ``SecretString`` as JSON and
                                        return the value of ``bot_token``.
* ``aws:arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/slack-AbCdEf``
                                      — full ARNs are accepted verbatim.

Design notes:

* **Sync SDK, async surface.** boto3 is sync-only; we wrap the single
  blocking call in :func:`asyncio.to_thread` so the provider conforms to
  :class:`SecretProvider` without pulling in aioboto3's heavier tree.
* **One client per provider.** The boto3 ``Session`` + ``SecretsManager``
  client are constructed once at init time (thread-safe for reads) rather
  than per-call. This matters because session construction does IMDS /
  credential-chain work that should not happen on every lookup.
* **No caching.** AWS Secrets Manager itself is cheap and rarely rate-limits;
  any caching strategy is application-specific and should live in the
  resolver, not the provider.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)


class AWSSecretsManagerAuthError(SecretProviderError):
    """Raised when AWS returns an auth-related error (invalid/expired creds, deny)."""


_AUTH_ERROR_CODES: frozenset[str] = frozenset(
    {
        "UnrecognizedClientException",
        "InvalidClientTokenId",
        "ExpiredTokenException",
        "AccessDeniedException",
    },
)

_NOT_FOUND_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ResourceNotFoundException",
    },
)


class AWSSecretsManagerProvider:
    """Async-facing wrapper over boto3's ``secretsmanager`` client.

    Example:
        >>> provider = AWSSecretsManagerProvider(region_name="us-east-1")  # doctest: +SKIP
        >>> await provider.get(parse_reference("aws:prod/slack#bot_token"))  # doctest: +SKIP
        'xoxb-...'
    """

    scheme: str = "aws"

    __slots__ = ("_client",)

    def __init__(
        self,
        *,
        region_name: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
        client: Any | None = None,
    ) -> None:
        """Build a provider bound to one AWS account + region.

        Args:
            region_name: AWS region, e.g. ``"us-east-1"``. ``None`` defers
                to the boto3 default-region chain (``AWS_REGION``,
                ``AWS_DEFAULT_REGION``, instance metadata).
            aws_access_key_id: Static access key. ``None`` uses the default
                credential chain (env, IMDS, IRSA, ...).
            aws_secret_access_key: Static secret key. Ignored unless
                ``aws_access_key_id`` is set.
            aws_session_token: Optional STS session token for short-lived
                credentials.
            client: Pre-built client used in tests (with ``botocore.stub.Stubber``).
                Production callers should pass ``None``.
        """
        if client is not None:
            self._client = client
            return
        session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name,
        )
        self._client = session.client("secretsmanager")

    async def get(self, reference: SecretReference) -> str:
        """Return the plaintext secret for ``reference``.

        Raises:
            SecretProviderError: The reference scheme is wrong, the secret
                was binary-only (no ``SecretString``), or a ``#field`` was
                requested but the payload is not valid JSON.
            AWSSecretsManagerAuthError: AWS rejected the caller's credentials
                or the IAM policy denied the read.
            SecretNotFoundError: The secret does not exist, or the requested
                field is absent from the JSON payload.
        """
        if reference.scheme != self.scheme:
            msg = f"AWSSecretsManagerProvider cannot handle scheme {reference.scheme!r}"
            raise SecretProviderError(msg)

        payload = await self._read(reference.path)
        secret_string = payload.get("SecretString")
        if not isinstance(secret_string, str):
            msg = (
                f"AWS secret {reference.path!r} has no SecretString "
                f"(binary-only secrets are unsupported)"
            )
            raise SecretProviderError(msg)

        if reference.field is None:
            return secret_string

        try:
            data = json.loads(secret_string)
        except json.JSONDecodeError as exc:
            msg = f"AWS secret {reference.path!r} is not JSON — cannot extract #{reference.field}"
            raise SecretProviderError(msg) from exc
        if not isinstance(data, dict):
            msg = f"AWS secret {reference.path!r} JSON root is not an object"
            raise SecretProviderError(msg)
        if reference.field not in data:
            msg = f"AWS secret has no field {reference.field!r}"
            raise SecretNotFoundError(msg)
        value = data[reference.field]
        if not isinstance(value, str):
            msg = f"AWS secret field {reference.field!r} is not a string"
            raise SecretProviderError(msg)
        return value

    async def _read(self, secret_id: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                self._client.get_secret_value,
                SecretId=secret_id,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in _NOT_FOUND_ERROR_CODES:
                msg = f"AWS secret {secret_id!r} not found"
                raise SecretNotFoundError(msg) from exc
            if code in _AUTH_ERROR_CODES:
                msg = f"AWS rejected the request for {secret_id!r}: {code}"
                raise AWSSecretsManagerAuthError(msg) from exc
            msg = f"AWS Secrets Manager error for {secret_id!r}: {code or 'unknown'}"
            raise SecretProviderError(msg) from exc
        except BotoCoreError as exc:
            msg = f"AWS SDK error for {secret_id!r}: {type(exc).__name__}"
            raise SecretProviderError(msg) from exc
