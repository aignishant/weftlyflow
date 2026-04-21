"""Abstract base for credential type plugins.

Every credential type declares:
    * ``slug``: globally unique identifier (``"weftlyflow.bearer_token"``).
    * ``display_name``: label shown in the UI.
    * ``properties``: form schema (reuses :class:`PropertySchema` from node_spec).
    * ``inject()``: attach the credential to an outgoing HTTP request.
    * ``test()`` (optional): validate the credential against the provider.

See IMPLEMENTATION_BIBLE.md §11.1 and `docs/contributing/credential-plugins.md`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import httpx

    from weftlyflow.domain.node_spec import PropertySchema


@dataclass
class CredentialTestResult:
    """Outcome of :meth:`BaseCredentialType.test`.

    Attributes:
        ok: True when the credential is valid.
        message: Human-readable detail (empty on success is fine).
    """

    ok: bool
    message: str = ""


class BaseCredentialType(ABC):
    """Abstract base for credential type plugins."""

    slug: ClassVar[str]
    display_name: ClassVar[str]
    properties: ClassVar[list[PropertySchema]]
    generic: ClassVar[bool] = False
    documentation_url: ClassVar[str | None] = None

    @abstractmethod
    async def inject(self, creds: dict[str, Any], request: httpx.Request) -> httpx.Request:
        """Return a copy of ``request`` with the credential applied.

        Typical implementations set an ``Authorization`` header or append a
        query parameter.

        Args:
            creds: Decrypted credential values keyed by ``PropertySchema.name``.
            request: The outgoing HTTP request about to be sent.
        """

    async def test(self, creds: dict[str, Any]) -> CredentialTestResult:
        """Self-test the credential. Default: not implemented.

        Override to call a lightweight ``GET /me`` or equivalent endpoint and
        surface a green/red check in the credential editor.
        """
        return CredentialTestResult(ok=True, message="not implemented")
