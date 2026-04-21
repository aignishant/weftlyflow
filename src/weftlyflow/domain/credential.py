"""Credential domain types — pointer + metadata only, never plaintext.

The actual secrets live encrypted in the database. These dataclasses describe
a credential at the domain level (what type, which project, who owns it) so
the engine and the UI have something to pass around without decrypting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CredentialDescriptor:
    """A credential row stripped of its plaintext.

    Attributes:
        id: ``cr_<ulid>``.
        project_id: Owning project.
        name: User-facing name.
        type: Credential-type slug (matches :mod:`weftlyflow.credentials.types`).
        created_at: UTC timestamp.
        updated_at: UTC timestamp.
    """

    id: str
    project_id: str
    name: str
    type: str
    created_at: datetime
    updated_at: datetime
