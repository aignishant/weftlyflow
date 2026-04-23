"""Tests for the ``/api/v1/auth/sso/saml/*`` router.

These cover the thin router layer — the provider itself is exercised by
``test_saml_provider.py``. For the ACS happy path we stub
:meth:`SAMLProvider.complete` so the tests do not need a real signed
assertion; DB-backed happy-path assertions live in the integration tier.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from weftlyflow.auth.sso.base import SSOError
from weftlyflow.auth.sso.state_token import make_state_token
from weftlyflow.config import get_settings
from weftlyflow.server.app import create_app


@pytest.fixture
def client_without_saml() -> TestClient:
    """App without a SAML provider configured — routes should 404."""
    app = create_app()
    with TestClient(app) as c:
        yield c


def _client_with_provider(provider: MagicMock) -> TestClient:
    app = create_app()
    client = TestClient(app)
    # TestClient's context manager runs lifespan; reach in afterwards so the
    # injected provider survives. We drive lifespan manually with __enter__.
    client.__enter__()
    app.state.sso_saml_provider = provider
    return client


def test_metadata_404_when_provider_missing(client_without_saml: TestClient) -> None:
    resp = client_without_saml.get("/api/v1/auth/sso/saml/metadata")

    assert resp.status_code == 404


def test_login_404_when_provider_missing(client_without_saml: TestClient) -> None:
    resp = client_without_saml.get("/api/v1/auth/sso/saml/login", follow_redirects=False)

    assert resp.status_code == 404


def test_acs_404_when_provider_missing(client_without_saml: TestClient) -> None:
    resp = client_without_saml.post(
        "/api/v1/auth/sso/saml/acs",
        data={"SAMLResponse": "x", "RelayState": "y"},
    )

    assert resp.status_code == 404


def test_metadata_returns_xml() -> None:
    provider = MagicMock()
    provider.prime = AsyncMock()
    provider.metadata_xml = MagicMock(return_value="<md:EntityDescriptor/>")

    client = _client_with_provider(provider)
    try:
        resp = client.get("/api/v1/auth/sso/saml/metadata")
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/samlmetadata+xml")
    assert resp.text == "<md:EntityDescriptor/>"
    provider.prime.assert_awaited_once()


def test_login_redirects_to_idp() -> None:
    provider = MagicMock()
    provider.prime = AsyncMock()
    provider.authorization_url = MagicMock(return_value="https://idp.example/sso?SAMLRequest=abc")

    client = _client_with_provider(provider)
    try:
        resp = client.get("/api/v1/auth/sso/saml/login", follow_redirects=False)
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://idp.example/sso")
    # The call was made with a state kwarg.
    (_args, kwargs) = provider.authorization_url.call_args
    assert "state" in kwargs
    assert kwargs["state"]


def test_acs_rejects_missing_relaystate() -> None:
    provider = MagicMock()
    provider.prime = AsyncMock()

    client = _client_with_provider(provider)
    try:
        resp = client.post(
            "/api/v1/auth/sso/saml/acs",
            data={"SAMLResponse": "ignored"},
        )
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 400
    assert "missing RelayState" in resp.text


def test_acs_rejects_forged_relaystate() -> None:
    provider = MagicMock()
    provider.prime = AsyncMock()

    client = _client_with_provider(provider)
    try:
        resp = client.post(
            "/api/v1/auth/sso/saml/acs",
            data={"SAMLResponse": "ignored", "RelayState": "not-a-real-token"},
        )
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 400
    assert "invalid RelayState" in resp.text


def test_acs_surfaces_provider_errors() -> None:
    provider = MagicMock()
    provider.prime = AsyncMock()
    provider.complete = AsyncMock(side_effect=SSOError("signature mismatch"))

    settings = get_settings()
    good_state = make_state_token(secret_key=settings.secret_key.get_secret_value())

    client = _client_with_provider(provider)
    try:
        resp = client.post(
            "/api/v1/auth/sso/saml/acs",
            data={"SAMLResponse": "ignored", "RelayState": good_state},
        )
    finally:
        client.__exit__(None, None, None)

    assert resp.status_code == 400
    assert "signature mismatch" in resp.text
