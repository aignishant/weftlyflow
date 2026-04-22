"""Credentials — encrypted secrets scoped to a project.

The ``data_ciphertext`` column is a Fernet token (base64 ASCII). The token
embeds its own nonce + HMAC + timestamp so we don't need a separate column.
"""

from __future__ import annotations

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base
from weftlyflow.db.entities.mixins import IdMixin, TimestampMixin


class CredentialEntity(Base, IdMixin, TimestampMixin):
    """Encrypted credential row — plaintext never leaves the API process."""

    __tablename__ = "credentials"

    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    data_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
