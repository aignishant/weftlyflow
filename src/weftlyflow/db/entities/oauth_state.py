"""OAuth2 ``state`` tokens — short-lived CSRF guard.

One row per in-flight OAuth2 handshake. The ``state`` value sent to the
provider must match a row here when the provider redirects back to
``GET /oauth2/callback``. Rows older than their ``expires_at`` are
considered dead and may be swept by a periodic task.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from weftlyflow.db.base import Base


class OAuthStateEntity(Base):
    """``state`` → credential mapping; drop on use or expiry."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    credential_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(400), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
