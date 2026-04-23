"""In-memory registry of :class:`BaseCredentialType` subclasses.

Populated at process start via :meth:`CredentialTypeRegistry.load_builtins`
and treated as read-only afterwards. Mirrors the shape of
:class:`~weftlyflow.nodes.registry.NodeRegistry` so contributors only have
one mental model.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from weftlyflow.credentials.base import BaseCredentialType
from weftlyflow.domain.errors import CredentialTypeNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterable


_BUILTIN_TYPES: tuple[str, ...] = (
    "weftlyflow.credentials.types.bearer_token",
    "weftlyflow.credentials.types.basic_auth",
    "weftlyflow.credentials.types.api_key_header",
    "weftlyflow.credentials.types.api_key_query",
    "weftlyflow.credentials.types.oauth2_generic",
    "weftlyflow.credentials.types.slack_api",
    "weftlyflow.credentials.types.slack_oauth2",
    "weftlyflow.credentials.types.notion_api",
    "weftlyflow.credentials.types.google_sheets_oauth2",
    "weftlyflow.credentials.types.discord_bot",
    "weftlyflow.credentials.types.telegram_bot",
    "weftlyflow.credentials.types.trello_api",
    "weftlyflow.credentials.types.hubspot_private_app",
    "weftlyflow.credentials.types.jira_cloud",
    "weftlyflow.credentials.types.shopify_admin",
    "weftlyflow.credentials.types.clickup_api",
    "weftlyflow.credentials.types.twilio_api",
    "weftlyflow.credentials.types.gitlab_token",
    "weftlyflow.credentials.types.intercom_api",
    "weftlyflow.credentials.types.monday_api",
    "weftlyflow.credentials.types.zendesk_api",
    "weftlyflow.credentials.types.brevo_api",
    "weftlyflow.credentials.types.pagerduty_api",
    "weftlyflow.credentials.types.algolia_api",
    "weftlyflow.credentials.types.mailchimp_api",
    "weftlyflow.credentials.types.pipedrive_api",
    "weftlyflow.credentials.types.zoho_crm_oauth2",
    "weftlyflow.credentials.types.mattermost_api",
    "weftlyflow.credentials.types.cloudflare_api",
    "weftlyflow.credentials.types.freshdesk_api",
    "weftlyflow.credentials.types.supabase_api",
    "weftlyflow.credentials.types.okta_api",
    "weftlyflow.credentials.types.linear_api",
    "weftlyflow.credentials.types.pushover_api",
    "weftlyflow.credentials.types.elasticsearch_api",
    "weftlyflow.credentials.types.dropbox_api",
    "weftlyflow.credentials.types.twitch_api",
    "weftlyflow.credentials.types.salesforce_api",
    "weftlyflow.credentials.types.zoom_api",
    "weftlyflow.credentials.types.microsoft_graph",
    "weftlyflow.credentials.types.asana_api",
    "weftlyflow.credentials.types.box_api",
    "weftlyflow.credentials.types.snowflake_api",
    "weftlyflow.credentials.types.datadog_api",
    "weftlyflow.credentials.types.activecampaign_api",
    "weftlyflow.credentials.types.aws_s3",
    "weftlyflow.credentials.types.openai_api",
    "weftlyflow.credentials.types.xero_api",
    "weftlyflow.credentials.types.netsuite_api",
    "weftlyflow.credentials.types.quickbooks_oauth2",
    "weftlyflow.credentials.types.square_api",
    "weftlyflow.credentials.types.facebook_graph",
    "weftlyflow.credentials.types.anthropic_api",
    "weftlyflow.credentials.types.bitbucket_api",
    "weftlyflow.credentials.types.paypal_api",
    "weftlyflow.credentials.types.mapbox_api",
    "weftlyflow.credentials.types.rocket_chat_api",
    "weftlyflow.credentials.types.contentful_api",
    "weftlyflow.credentials.types.hasura_api",
    "weftlyflow.credentials.types.ghost_admin",
    "weftlyflow.credentials.types.pinecone_api",
    "weftlyflow.credentials.types.gmail_oauth2",
    "weftlyflow.credentials.types.google_drive_oauth2",
)


class CredentialRegistryError(Exception):
    """Raised for registry misuse (duplicate slug, missing attribute)."""


class CredentialTypeRegistry:
    """Lookup table keyed by :attr:`BaseCredentialType.slug`."""

    __slots__ = ("_by_slug",)

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_slug: dict[str, type[BaseCredentialType]] = {}

    def register(
        self,
        cred_cls: type[BaseCredentialType],
        *,
        replace: bool = False,
    ) -> type[BaseCredentialType]:
        """Register ``cred_cls`` under its declared ``slug``."""
        slug = getattr(cred_cls, "slug", None)
        if not isinstance(slug, str) or not slug:
            msg = f"{cred_cls.__qualname__} is missing a string `slug` class attribute"
            raise CredentialRegistryError(msg)
        if slug in self._by_slug and not replace:
            msg = f"credential type already registered: {slug!r}"
            raise CredentialRegistryError(msg)
        self._by_slug[slug] = cred_cls
        return cred_cls

    def register_many(
        self,
        classes: Iterable[type[BaseCredentialType]],
        *,
        replace: bool = False,
    ) -> None:
        """Bulk register — used by tests."""
        for cls in classes:
            self.register(cls, replace=replace)

    def get(self, slug: str) -> type[BaseCredentialType]:
        """Return the registered class for ``slug`` or raise."""
        try:
            return self._by_slug[slug]
        except KeyError as exc:
            msg = f"no credential type registered for {slug!r}"
            raise CredentialTypeNotFoundError(msg) from exc

    def __contains__(self, slug: object) -> bool:
        """Support ``"weftlyflow.bearer_token" in registry``."""
        return isinstance(slug, str) and slug in self._by_slug

    def __len__(self) -> int:
        """Return the number of registered types."""
        return len(self._by_slug)

    def catalog(self) -> list[type[BaseCredentialType]]:
        """Return a snapshot of every registered class."""
        return list(self._by_slug.values())

    def load_builtins(self) -> int:
        """Import every built-in credential-type module and register its ``TYPE``.

        Returns the number of newly-added classes.
        """
        before = len(self)
        for module_name in _BUILTIN_TYPES:
            module = import_module(module_name)
            cred_cls = getattr(module, "TYPE", None)
            if cred_cls is None:
                msg = f"{module_name} is missing a top-level `TYPE` attribute"
                raise CredentialRegistryError(msg)
            if not isinstance(cred_cls, type) or not issubclass(cred_cls, BaseCredentialType):
                msg = f"{module_name}.TYPE is not a BaseCredentialType subclass"
                raise CredentialRegistryError(msg)
            self.register(cred_cls)
        return len(self) - before
