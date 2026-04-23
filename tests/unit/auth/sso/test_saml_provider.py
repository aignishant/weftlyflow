"""Unit tests for :mod:`weftlyflow.auth.sso.saml`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from weftlyflow.auth.sso.base import SSOError
from weftlyflow.auth.sso.saml import SAMLConfig, SAMLProvider

_IDP_METADATA_XML: str = (
    '<?xml version="1.0"?>'
    '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"'
    ' entityID="https://idp.example.com/saml">'
    '<md:IDPSSODescriptor WantAuthnRequestsSigned="false"'
    ' protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
    '<md:SingleSignOnService'
    ' Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"'
    ' Location="https://idp.example.com/sso"/>'
    "<md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>"
    "</md:IDPSSODescriptor>"
    "</md:EntityDescriptor>"
)


@pytest.fixture
def config() -> SAMLConfig:
    return SAMLConfig(
        sp_entity_id="https://sp.example.com/api/v1/auth/sso/saml/metadata",
        sp_acs_url="https://sp.example.com/api/v1/auth/sso/saml/acs",
        idp_metadata_xml=_IDP_METADATA_XML,
        want_assertions_signed=False,
    )


async def test_authorization_url_fails_before_prime(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)

    with pytest.raises(SSOError, match="call prime"):
        provider.authorization_url(state="s")


async def test_prime_parses_idp_metadata(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)

    await provider.prime()

    idp = provider._require_idp()
    assert idp["entityId"] == "https://idp.example.com/saml"
    assert idp["singleSignOnService"]["url"] == "https://idp.example.com/sso"


async def test_prime_is_idempotent(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)

    await provider.prime()
    first = provider._require_idp()
    await provider.prime()
    second = provider._require_idp()

    assert first is second


async def test_prime_rejects_metadata_without_idp(config: SAMLConfig) -> None:
    bad = SAMLConfig(
        sp_entity_id=config.sp_entity_id,
        sp_acs_url=config.sp_acs_url,
        # SP-only metadata, no <IDPSSODescriptor>
        idp_metadata_xml="""<?xml version="1.0"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="x"/>""",
    )
    provider = SAMLProvider(bad)

    with pytest.raises(SSOError, match="IDPSSODescriptor"):
        await provider.prime()


async def test_authorization_url_carries_relaystate(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    url = provider.authorization_url(state="my-state-token")

    assert url.startswith("https://idp.example.com/sso")
    # OneLogin URL-encodes RelayState value.
    assert "RelayState=my-state-token" in url
    assert "SAMLRequest=" in url


async def test_metadata_xml_works_before_prime(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)

    xml = provider.metadata_xml()

    assert "<md:EntityDescriptor" in xml or "EntityDescriptor" in xml
    assert config.sp_entity_id in xml
    assert config.sp_acs_url in xml


async def test_metadata_xml_works_after_prime(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    xml = provider.metadata_xml()

    assert config.sp_entity_id in xml


async def test_complete_requires_saml_response(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    with pytest.raises(SSOError, match="missing SAMLResponse"):
        await provider.complete({})


async def test_complete_surfaces_onelogin_errors(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    fake_auth = MagicMock()
    fake_auth.process_response = MagicMock()
    fake_auth.get_errors.return_value = ["invalid_response"]
    fake_auth.get_last_error_reason.return_value = "signature mismatch"

    with _patch_auth(provider, fake_auth), pytest.raises(SSOError, match="signature mismatch"):
        await provider.complete({"SAMLResponse": "ignored"})


async def test_complete_requires_authenticated(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    fake_auth = MagicMock()
    fake_auth.process_response = MagicMock()
    fake_auth.get_errors.return_value = []
    fake_auth.is_authenticated.return_value = False

    with _patch_auth(provider, fake_auth), pytest.raises(SSOError, match="did not authenticate"):
        await provider.complete({"SAMLResponse": "ignored"})


async def test_complete_returns_userinfo_with_email_attr(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    fake_auth = MagicMock()
    fake_auth.process_response = MagicMock()
    fake_auth.get_errors.return_value = []
    fake_auth.is_authenticated.return_value = True
    fake_auth.get_attributes.return_value = {
        "email": ["Alice@Example.com"],
        "displayName": ["Alice Liddell"],
    }
    fake_auth.get_nameid.return_value = "alice-12345"
    fake_auth.get_nameid_format.return_value = (
        "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    )

    with _patch_auth(provider, fake_auth):
        info = await provider.complete({"SAMLResponse": "ignored"})

    assert info.subject == "alice-12345"
    assert info.email == "alice@example.com"
    assert info.email_verified is True
    assert info.display_name == "Alice Liddell"
    assert info.issuer == "https://idp.example.com/saml"


async def test_complete_falls_back_to_email_nameid(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    fake_auth = MagicMock()
    fake_auth.process_response = MagicMock()
    fake_auth.get_errors.return_value = []
    fake_auth.is_authenticated.return_value = True
    fake_auth.get_attributes.return_value = {}
    fake_auth.get_nameid.return_value = "bob@example.com"
    fake_auth.get_nameid_format.return_value = (
        "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    )

    with _patch_auth(provider, fake_auth):
        info = await provider.complete({"SAMLResponse": "ignored"})

    assert info.subject == "bob@example.com"
    assert info.email == "bob@example.com"


async def test_complete_rejects_unusable_subject(config: SAMLConfig) -> None:
    provider = SAMLProvider(config)
    await provider.prime()

    fake_auth = MagicMock()
    fake_auth.process_response = MagicMock()
    fake_auth.get_errors.return_value = []
    fake_auth.is_authenticated.return_value = True
    fake_auth.get_attributes.return_value = {}
    fake_auth.get_nameid.return_value = "opaque-sub-no-email"
    fake_auth.get_nameid_format.return_value = (
        "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    )

    with _patch_auth(provider, fake_auth), pytest.raises(SSOError, match="lacks an email"):
        await provider.complete({"SAMLResponse": "ignored"})


async def test_signed_requests_enabled_when_keypair_provided() -> None:
    config = SAMLConfig(
        sp_entity_id="https://sp.example.com/metadata",
        sp_acs_url="https://sp.example.com/acs",
        idp_metadata_xml=_IDP_METADATA_XML,
        # Any non-empty strings flip the flag; actual signing would demand
        # valid PEM material but we only assert the settings wiring here.
        x509_cert="stub-cert",
        private_key="stub-key",
        want_assertions_signed=False,
    )
    provider = SAMLProvider(config)
    await provider.prime()

    assert provider._settings_dict is not None
    assert provider._settings_dict["security"]["authnRequestsSigned"] is True


def _patch_auth(_provider: SAMLProvider, fake_auth: MagicMock) -> object:
    """Return a context manager that swaps :func:`SAMLProvider._make_auth`.

    ``SAMLProvider`` uses ``__slots__`` so ``patch.object(instance, ...)`` is
    blocked — patch the class method instead.
    """
    return patch.object(
        SAMLProvider,
        "_make_auth",
        lambda self, **_kwargs: fake_auth,
    )
