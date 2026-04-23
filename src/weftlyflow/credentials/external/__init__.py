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

See IMPLEMENTATION_BIBLE.md §11.4. This subpackage contains only the
provider abstractions and the built-in :class:`EnvSecretProvider`. Vault /
AWS / 1Password adapters will arrive later and must conform to
:class:`SecretProvider`.
"""

from __future__ import annotations

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProvider,
    SecretProviderError,
    SecretReference,
    parse_reference,
)
from weftlyflow.credentials.external.env_provider import EnvSecretProvider
from weftlyflow.credentials.external.registry import SecretProviderRegistry

__all__ = [
    "EnvSecretProvider",
    "SecretNotFoundError",
    "SecretProvider",
    "SecretProviderError",
    "SecretProviderRegistry",
    "SecretReference",
    "parse_reference",
]
