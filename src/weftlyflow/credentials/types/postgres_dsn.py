"""Postgres DSN credential - shared by every Postgres-backed node.

Unlike every other built-in credential, this one doesn't attach to an
HTTP request. Postgres speaks its own wire protocol, so ``inject`` is
a no-op and nodes read the ``dsn`` field directly from the decrypted
payload via :meth:`~weftlyflow.engine.context.ExecutionContext.load_credential`.

The self-test opens a single async connection and runs ``SELECT 1`` -
enough to prove the DSN resolves, authenticates, and reaches a live
server without assuming any particular schema or extension.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import httpx
import psycopg

from weftlyflow.credentials.base import BaseCredentialType, CredentialTestResult
from weftlyflow.domain.node_spec import PropertySchema

_TEST_TIMEOUT_SECONDS: Final[float] = 10.0


class PostgresDsnCredential(BaseCredentialType):
    """Stores a full ``postgresql://`` DSN; no HTTP injection."""

    slug: ClassVar[str] = "weftlyflow.postgres_dsn"
    display_name: ClassVar[str] = "Postgres Connection"
    generic: ClassVar[bool] = True
    documentation_url: ClassVar[str | None] = (
        "https://www.postgresql.org/docs/current/libpq-connect.html"
        "#LIBPQ-CONNSTRING"
    )
    properties: ClassVar[list[PropertySchema]] = [
        PropertySchema(
            name="dsn",
            display_name="DSN",
            type="string",
            required=True,
            description=(
                "Full connection string, e.g. "
                "postgresql://user:pass@host:5432/db."
            ),
            type_options={"password": True},
        ),
    ]

    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """No-op: Postgres does not use HTTP transport."""
        del creds
        return request

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Open a short-lived async connection and run ``SELECT 1``."""
        dsn = str(creds.get("dsn") or "").strip()
        if not dsn:
            return CredentialTestResult(ok=False, message="dsn is empty")
        try:
            async with await psycopg.AsyncConnection.connect(
                dsn, connect_timeout=int(_TEST_TIMEOUT_SECONDS),
            ) as conn, conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        except (psycopg.Error, OSError) as exc:
            return CredentialTestResult(ok=False, message=f"connection failed: {exc}")
        return CredentialTestResult(ok=True, message="connected")


TYPE = PostgresDsnCredential
