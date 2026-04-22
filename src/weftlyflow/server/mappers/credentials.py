"""Mappers between :class:`CredentialEntity` and the wire DTOs.

Plaintext never goes through here — the ciphertext column stays opaque.
The router passes decrypted payloads directly to the credential-type
:meth:`inject` without letting them touch the response.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from weftlyflow.server.schemas.credentials import (
    CredentialResponse,
    CredentialSummary,
    CredentialTypeResponse,
)

if TYPE_CHECKING:
    from weftlyflow.credentials.base import BaseCredentialType
    from weftlyflow.db.entities.credential import CredentialEntity


def credential_to_response(entity: CredentialEntity) -> CredentialResponse:
    """Project an entity row into the wire response (no secrets)."""
    return CredentialResponse(
        id=entity.id,
        project_id=entity.project_id,
        name=entity.name,
        type=entity.type,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def credential_to_summary(entity: CredentialEntity) -> CredentialSummary:
    """Project an entity row into a list-response summary."""
    return CredentialSummary(
        id=entity.id,
        project_id=entity.project_id,
        name=entity.name,
        type=entity.type,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def credential_type_to_response(cred_cls: type[BaseCredentialType]) -> CredentialTypeResponse:
    """Project a :class:`BaseCredentialType` subclass into the catalog response."""
    props: list[dict[str, Any]] = [asdict(prop) for prop in cred_cls.properties]
    # Scrub defaults we don't want on the wire (e.g. ``None`` options lists).
    for prop in props:
        if prop.get("options") is None:
            prop.pop("options", None)
        if prop.get("display_options") is None:
            prop.pop("display_options", None)
        if prop.get("type_options") is None:
            prop.pop("type_options", None)
    return CredentialTypeResponse(
        slug=cred_cls.slug,
        display_name=cred_cls.display_name,
        generic=cred_cls.generic,
        properties=props,
    )
