"""Credential system — plugin types + Fernet encryption at rest.

Public surface:

* :class:`BaseCredentialType` / :class:`CredentialTestResult` — plugin API.
* :class:`CredentialCipher` / :func:`generate_key` — Fernet wrapper for
  encrypting + decrypting credential payloads.
* :class:`CredentialTypeRegistry` — slug → class lookup.

See weftlyinfo.md §11.
"""

from __future__ import annotations

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.credentials.cipher import CredentialCipher, generate_key, random_nonce
from weftlyflow.credentials.registry import (
    CredentialRegistryError,
    CredentialTypeRegistry,
)
from weftlyflow.credentials.resolver import (
    CredentialResolver,
    DatabaseCredentialResolver,
    InMemoryCredentialResolver,
)

__all__ = [
    "BaseCredentialType",
    "CredentialCipher",
    "CredentialRegistryError",
    "CredentialResolver",
    "CredentialTestResult",
    "CredentialTypeRegistry",
    "DatabaseCredentialResolver",
    "InMemoryCredentialResolver",
    "generate_key",
    "random_nonce",
]
