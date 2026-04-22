"""Unit tests for :class:`SlackApiCredential` — inject + auth.test probe."""

from __future__ import annotations

import httpx
import respx
from httpx import Response

from weftlyflow.credentials.types.slack_api import SlackApiCredential


def _fresh_request() -> httpx.Request:
    return httpx.Request("POST", "https://slack.com/api/chat.postMessage")


async def test_inject_sets_bearer_authorization_header() -> None:
    req = _fresh_request()
    out = await SlackApiCredential().inject({"access_token": "xoxb-123"}, req)
    assert out.headers["Authorization"] == "Bearer xoxb-123"


async def test_test_fails_when_token_empty() -> None:
    res = await SlackApiCredential().test({"access_token": ""})
    assert res.ok is False
    assert "empty" in res.message.lower()


@respx.mock
async def test_test_hits_auth_test_and_reports_identity() -> None:
    respx.post("https://slack.com/api/auth.test").mock(
        return_value=Response(
            200,
            json={"ok": True, "team": "AcmeCo", "user": "weftybot"},
        ),
    )
    res = await SlackApiCredential().test({"access_token": "xoxb-abc"})
    assert res.ok is True
    assert "weftybot" in res.message
    assert "AcmeCo" in res.message


@respx.mock
async def test_test_surfaces_slack_error() -> None:
    respx.post("https://slack.com/api/auth.test").mock(
        return_value=Response(200, json={"ok": False, "error": "invalid_auth"}),
    )
    res = await SlackApiCredential().test({"access_token": "xoxb-bad"})
    assert res.ok is False
    assert "invalid_auth" in res.message


@respx.mock
async def test_test_handles_network_failure() -> None:
    respx.post("https://slack.com/api/auth.test").mock(
        side_effect=httpx.ConnectError("boom"),
    )
    res = await SlackApiCredential().test({"access_token": "xoxb-abc"})
    assert res.ok is False
    assert "network error" in res.message.lower()
