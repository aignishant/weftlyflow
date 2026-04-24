"""External-secret providers — pluggable backends for secrets outside the DB.

A **secret provider** maps an opaque reference (e.g. ``"env:SLACK_TOKEN"``
or ``"vault:kv/data/slack#token"``) to a plaintext secret value at runtime.
Credentials in the database can store a reference string instead of (or in
addition to) the encrypted payload; the resolver will call the matching
provider when a node asks for the credential.

Why this layer exists:

* **Rotation** — the DB does not need to be re-encrypted when a secret
  rotates upstream.
* **Compliance** — secrets may be required to live in a vault rather than
  this process's storage.
* **Dev ergonomics** — developers can point credentials at environment
  variables without running a real vault.

See weftlyinfo.md §11.4. This subpackage contains the provider
abstractions, the built-in :class:`EnvSecretProvider`, the
:class:`VaultSecretProvider` (HashiCorp Vault KV v2), the
:class:`OnePasswordSecretProvider` (1Password Connect), and the
:class:`AWSSecretsManagerProvider` (behind the ``aws-secrets`` optional
extra). Any additional backend must conform to :class:`SecretProvider`.

``AWSSecretsManagerProvider`` is imported lazily because the module itself
imports ``boto3`` at top level; pulling it in unconditionally would make
boto3 a hard dependency of the ``credentials`` subpackage. Call
:func:`load_aws_provider` (or import it directly from the submodule) once
the ``aws-secrets`` extra is installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProvider,
    SecretProviderError,
    SecretReference,
    parse_reference,
)
from weftlyflow.credentials.external.env_provider import EnvSecretProvider
from weftlyflow.credentials.external.onepassword_provider import (
    OnePasswordAuthError,
    OnePasswordSecretProvider,
)
from weftlyflow.credentials.external.registry import (
    SecretProviderRegistry,
    UnknownSecretSchemeError,
)
from weftlyflow.credentials.external.vault_provider import (
    VaultAuthError,
    VaultSecretProvider,
)

if TYPE_CHECKING:
    from weftlyflow.credentials.external.aws_provider import (
        AWSSecretsManagerProvider,
    )


def load_aws_provider() -> type[AWSSecretsManagerProvider]:
    """Import and return :class:`AWSSecretsManagerProvider`.

    Kept lazy so the ``credentials`` subpackage doesn't force ``boto3`` on
    installations that don't enable AWS Secrets Manager. Raises
    :class:`ImportError` with an actionable message when the ``aws-secrets``
    extra is missing.
    """
    try:
        from weftlyflow.credentials.external.aws_provider import (  # noqa: PLC0415
            AWSSecretsManagerProvider,
        )
    except ImportError as exc:
        msg = (
            "AWSSecretsManagerProvider requires the 'aws-secrets' extra — "
            "install with ``pip install 'weftlyflow[aws-secrets]'``."
        )
        raise ImportError(msg) from exc
    return AWSSecretsManagerProvider


__all__ = [
    "EnvSecretProvider",
    "OnePasswordAuthError",
    "OnePasswordSecretProvider",
    "SecretNotFoundError",
    "SecretProvider",
    "SecretProviderError",
    "SecretProviderRegistry",
    "SecretReference",
    "UnknownSecretSchemeError",
    "VaultAuthError",
    "VaultSecretProvider",
    "load_aws_provider",
    "parse_reference",
]
