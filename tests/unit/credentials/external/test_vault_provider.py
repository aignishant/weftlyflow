"""Unit tests for :class:`VaultSecretProvider`."""

from __future__ import annotations

import httpx
import pytest
import respx

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)
from weftlyflow.credentials.external.vault_provider import (
    VaultAuthError,
    VaultSecretProvider,
)

VAULT_ADDR = "https://vault.example.com:8200"
TOKEN = "hvs.test-token"


def _ref(path: str = "secret/data/slack", field: str | None = "bot_token") -> SecretReference:
    return SecretReference(scheme="vault", path=path, field=field)


@pytest.mark.asyncio
@respx.mock
async def test_reads_kv_v2_field() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": "xoxb-999", "app_token": "xapp-1"}}}
    )
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    value = await provider.get(_ref())
    assert value == "xoxb-999"


@pytest.mark.asyncio
@respx.mock
async def test_sends_vault_token_header() -> None:
    route = respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": "x"}}}
    )
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    await provider.get(_ref())
    assert route.calls.last.request.headers["X-Vault-Token"] == TOKEN


@pytest.mark.asyncio
@respx.mock
async def test_sends_namespace_header_when_set() -> None:
    route = respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": "x"}}}
    )
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN, namespace="team-a")
    await provider.get(_ref())
    assert route.calls.last.request.headers["X-Vault-Namespace"] == "team-a"


@pytest.mark.asyncio
@respx.mock
async def test_strips_trailing_slash_from_address() -> None:
    route = respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": "x"}}}
    )
    provider = VaultSecretProvider(address=VAULT_ADDR + "/", token=TOKEN)
    await provider.get(_ref())
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_404_raises_not_found() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(status_code=404)
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(status_code=401)
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(VaultAuthError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_403_raises_auth_error() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(status_code=403)
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(VaultAuthError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_500_raises_provider_error() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(status_code=500)
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_missing_field_raises_not_found() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": "x"}}}
    )
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref(field="missing"))


@pytest.mark.asyncio
@respx.mock
async def test_reference_without_field_rejected() -> None:
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref(field=None))


@pytest.mark.asyncio
@respx.mock
async def test_non_kv_v2_envelope_raises_provider_error() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(json={"unexpected": True})
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_non_string_field_raises_provider_error() -> None:
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": 123}}}
    )
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_rejects_wrong_scheme() -> None:
    provider = VaultSecretProvider(address=VAULT_ADDR, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(SecretReference(scheme="env", path="FOO"))


@pytest.mark.asyncio
async def test_missing_address_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="address"):
        VaultSecretProvider(address="", token=TOKEN)


@pytest.mark.asyncio
async def test_missing_token_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="token"):
        VaultSecretProvider(address=VAULT_ADDR, token="")


@pytest.mark.asyncio
@respx.mock
async def test_injected_client_is_not_closed() -> None:
    """A caller-supplied client must survive the context-manager exit."""
    respx.get(f"{VAULT_ADDR}/v1/secret/data/slack").respond(
        json={"data": {"data": {"bot_token": "x"}}}
    )
    async with httpx.AsyncClient() as client:
        provider = VaultSecretProvider(
            address=VAULT_ADDR, token=TOKEN, http_client=client
        )
        await provider.get(_ref())
        # The injected client must still be usable after the call. If the
        # provider had leaked an ``async with`` onto it, this assertion
        # would fail.
        assert not client.is_closed
