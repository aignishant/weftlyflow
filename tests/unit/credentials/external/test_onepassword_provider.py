"""Unit tests for :class:`OnePasswordSecretProvider`."""

from __future__ import annotations

import httpx
import pytest
import respx

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)
from weftlyflow.credentials.external.onepassword_provider import (
    OnePasswordAuthError,
    OnePasswordSecretProvider,
)

CONNECT_URL = "http://onepassword-connect:8080"
TOKEN = "eyJhbGciOiJFUzI1NiIs.test-token"
ITEM_PATH = "vaults/abc-vault-uuid/items/xyz-item-uuid"

ITEM_PAYLOAD = {
    "id": "xyz-item-uuid",
    "title": "Slack bot",
    "fields": [
        {"id": "f1", "label": "username", "value": "bot@example.com", "type": "STRING"},
        {"id": "f2", "label": "password", "value": "s3cr3t", "type": "CONCEALED"},
        {"id": "f3", "label": "notes", "value": "", "type": "STRING"},
    ],
}


def _ref(path: str = ITEM_PATH, field: str | None = "password") -> SecretReference:
    return SecretReference(scheme="op", path=path, field=field)


@pytest.mark.asyncio
@respx.mock
async def test_reads_field_value_by_label() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=ITEM_PAYLOAD)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    assert await provider.get(_ref()) == "s3cr3t"


@pytest.mark.asyncio
@respx.mock
async def test_sends_bearer_authorization_header() -> None:
    route = respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=ITEM_PAYLOAD)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    await provider.get(_ref())
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
@respx.mock
async def test_strips_trailing_slash_from_connect_url() -> None:
    route = respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=ITEM_PAYLOAD)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL + "/", token=TOKEN)
    await provider.get(_ref())
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_field_label_is_case_sensitive() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=ITEM_PAYLOAD)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref(field="Password"))


@pytest.mark.asyncio
@respx.mock
async def test_404_raises_not_found() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(status_code=404)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(status_code=401)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(OnePasswordAuthError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_403_raises_auth_error() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(status_code=403)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(OnePasswordAuthError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_500_raises_provider_error() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(status_code=500)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_missing_field_raises_not_found() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=ITEM_PAYLOAD)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref(field="missing"))


@pytest.mark.asyncio
@respx.mock
async def test_field_without_value_raises_not_found() -> None:
    payload = {
        "fields": [
            {"id": "f1", "label": "secret", "type": "CONCEALED"},
        ],
    }
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=payload)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref(field="secret"))


@pytest.mark.asyncio
@respx.mock
async def test_reference_without_field_rejected() -> None:
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref(field=None))


@pytest.mark.asyncio
@respx.mock
async def test_payload_without_fields_array_raises_provider_error() -> None:
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json={"id": "x", "title": "y"})
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
@respx.mock
async def test_non_string_field_value_raises_provider_error() -> None:
    payload = {
        "fields": [{"id": "f1", "label": "password", "value": 123, "type": "STRING"}],
    }
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=payload)
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_rejects_wrong_scheme() -> None:
    provider = OnePasswordSecretProvider(connect_url=CONNECT_URL, token=TOKEN)
    with pytest.raises(SecretProviderError):
        await provider.get(SecretReference(scheme="vault", path="foo"))


@pytest.mark.asyncio
async def test_missing_connect_url_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="connect_url"):
        OnePasswordSecretProvider(connect_url="", token=TOKEN)


@pytest.mark.asyncio
async def test_missing_token_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="token"):
        OnePasswordSecretProvider(connect_url=CONNECT_URL, token="")


@pytest.mark.asyncio
@respx.mock
async def test_injected_client_is_not_closed() -> None:
    """A caller-supplied client must survive the context-manager exit."""
    respx.get(f"{CONNECT_URL}/v1/{ITEM_PATH}").respond(json=ITEM_PAYLOAD)
    async with httpx.AsyncClient() as client:
        provider = OnePasswordSecretProvider(
            connect_url=CONNECT_URL, token=TOKEN, http_client=client
        )
        await provider.get(_ref())
        assert not client.is_closed
