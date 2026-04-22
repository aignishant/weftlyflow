"""Unit tests for the five built-in credential types."""

from __future__ import annotations

import base64

import httpx
import pytest

from weftlyflow.credentials.registry import CredentialTypeRegistry
from weftlyflow.credentials.types import (
    ApiKeyHeaderCredential,
    ApiKeyQueryCredential,
    BasicAuthCredential,
    BearerTokenCredential,
    OAuth2GenericCredential,
    SlackOAuth2Credential,
)


def _fresh_request() -> httpx.Request:
    return httpx.Request("GET", "https://example.com/path")


async def test_bearer_token_adds_authorization_header() -> None:
    req = _fresh_request()
    out = await BearerTokenCredential().inject({"token": "abc"}, req)
    assert out.headers["Authorization"] == "Bearer abc"


async def test_bearer_test_reports_missing_token() -> None:
    res = await BearerTokenCredential().test({"token": ""})
    assert res.ok is False


async def test_basic_auth_base64_encodes_credentials() -> None:
    req = _fresh_request()
    out = await BasicAuthCredential().inject({"username": "u", "password": "p"}, req)
    expected = "Basic " + base64.b64encode(b"u:p").decode("ascii")
    assert out.headers["Authorization"] == expected


async def test_api_key_header_uses_custom_header_name() -> None:
    req = _fresh_request()
    out = await ApiKeyHeaderCredential().inject(
        {"header_name": "X-Custom", "api_key": "k"}, req,
    )
    assert out.headers["X-Custom"] == "k"


async def test_api_key_header_default_name_when_missing() -> None:
    req = _fresh_request()
    out = await ApiKeyHeaderCredential().inject(
        {"header_name": "", "api_key": "k"}, req,
    )
    assert out.headers["X-API-Key"] == "k"


async def test_api_key_query_appends_to_url() -> None:
    req = _fresh_request()
    out = await ApiKeyQueryCredential().inject(
        {"param_name": "api_key", "api_key": "k"}, req,
    )
    assert "api_key=k" in str(out.url)


async def test_oauth2_injects_access_token() -> None:
    req = _fresh_request()
    out = await OAuth2GenericCredential().inject(
        {"access_token": "tok"}, req,
    )
    assert out.headers["Authorization"] == "Bearer tok"


async def test_oauth2_test_complains_without_token() -> None:
    res = await OAuth2GenericCredential().test({"access_token": ""})
    assert res.ok is False
    assert "access_token" in res.message.lower()


async def test_slack_oauth2_injects_bearer_token() -> None:
    req = _fresh_request()
    out = await SlackOAuth2Credential().inject({"access_token": "xoxb-oauth"}, req)
    assert out.headers["Authorization"] == "Bearer xoxb-oauth"


async def test_slack_oauth2_test_complains_without_token() -> None:
    res = await SlackOAuth2Credential().test({"access_token": ""})
    assert res.ok is False
    assert "access_token" in res.message.lower()


def test_slack_oauth2_has_slack_default_endpoints() -> None:
    props = {p.name: p for p in SlackOAuth2Credential.properties}
    assert props["authorization_url"].default == "https://slack.com/oauth/v2/authorize"
    assert props["token_url"].default == "https://slack.com/api/oauth.v2.access"
    assert "chat:write" in str(props["scope"].default)


def test_registry_load_builtins_registers_all_builtins() -> None:
    reg = CredentialTypeRegistry()
    added = reg.load_builtins()
    assert added == 31
    slugs = {cls.slug for cls in reg.catalog()}
    assert slugs == {
        "weftlyflow.bearer_token",
        "weftlyflow.basic_auth",
        "weftlyflow.api_key_header",
        "weftlyflow.api_key_query",
        "weftlyflow.oauth2_generic",
        "weftlyflow.slack_api",
        "weftlyflow.slack_oauth2",
        "weftlyflow.notion_api",
        "weftlyflow.google_sheets_oauth2",
        "weftlyflow.discord_bot",
        "weftlyflow.telegram_bot",
        "weftlyflow.trello_api",
        "weftlyflow.hubspot_private_app",
        "weftlyflow.jira_cloud",
        "weftlyflow.shopify_admin",
        "weftlyflow.clickup_api",
        "weftlyflow.twilio_api",
        "weftlyflow.gitlab_token",
        "weftlyflow.intercom_api",
        "weftlyflow.monday_api",
        "weftlyflow.zendesk_api",
        "weftlyflow.brevo_api",
        "weftlyflow.pagerduty_api",
        "weftlyflow.algolia_api",
        "weftlyflow.mailchimp_api",
        "weftlyflow.pipedrive_api",
        "weftlyflow.zoho_crm_oauth2",
        "weftlyflow.mattermost_api",
        "weftlyflow.cloudflare_api",
        "weftlyflow.freshdesk_api",
        "weftlyflow.supabase_api",
    }


def test_registry_rejects_duplicate() -> None:
    reg = CredentialTypeRegistry()
    reg.register(BearerTokenCredential)
    with pytest.raises(Exception, match="already registered"):
        reg.register(BearerTokenCredential)
    # Replace flag allows overwrite.
    reg.register(BearerTokenCredential, replace=True)
