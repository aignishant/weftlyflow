"""Unit tests for :class:`AWSSecretsManagerProvider`.

Exercises the provider against :class:`botocore.stub.Stubber`, which
intercepts boto3 at the HTTP-client layer without making network calls
or needing moto / AWS creds.
"""

from __future__ import annotations

import boto3
import pytest
from botocore.stub import Stubber

from weftlyflow.credentials.external.aws_provider import (
    AWSSecretsManagerAuthError,
    AWSSecretsManagerProvider,
)
from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)

SECRET_ID = "prod/slack"


def _stubbed_provider() -> tuple[AWSSecretsManagerProvider, Stubber]:
    """Build a provider whose client is pre-wired to a fresh ``Stubber``."""
    client = boto3.client("secretsmanager", region_name="us-east-1")
    stubber = Stubber(client)
    stubber.activate()
    return AWSSecretsManagerProvider(client=client), stubber


def _ref(path: str = SECRET_ID, field: str | None = None) -> SecretReference:
    return SecretReference(scheme="aws", path=path, field=field)


@pytest.mark.asyncio
async def test_returns_raw_secret_string_when_no_field() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {"Name": SECRET_ID, "SecretString": "xoxb-999"},
        expected_params={"SecretId": SECRET_ID},
    )
    assert await provider.get(_ref()) == "xoxb-999"
    stubber.assert_no_pending_responses()


@pytest.mark.asyncio
async def test_extracts_json_field_when_field_set() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {
            "Name": SECRET_ID,
            "SecretString": '{"bot_token": "xoxb-1", "app_token": "xapp-1"}',
        },
        expected_params={"SecretId": SECRET_ID},
    )
    assert await provider.get(_ref(field="bot_token")) == "xoxb-1"


@pytest.mark.asyncio
async def test_field_missing_raises_not_found() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {"Name": SECRET_ID, "SecretString": '{"bot_token": "x"}'},
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref(field="missing"))


@pytest.mark.asyncio
async def test_non_json_payload_with_field_raises_provider_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {"Name": SECRET_ID, "SecretString": "not-json"},
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretProviderError):
        await provider.get(_ref(field="bot_token"))


@pytest.mark.asyncio
async def test_json_array_root_with_field_raises_provider_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {"Name": SECRET_ID, "SecretString": "[1, 2, 3]"},
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretProviderError):
        await provider.get(_ref(field="foo"))


@pytest.mark.asyncio
async def test_non_string_field_value_raises_provider_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {"Name": SECRET_ID, "SecretString": '{"x": 123}'},
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretProviderError):
        await provider.get(_ref(field="x"))


@pytest.mark.asyncio
async def test_binary_only_secret_raises_provider_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_response(
        "get_secret_value",
        {"Name": SECRET_ID, "SecretBinary": b"\x00\x01\x02"},
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_resource_not_found_maps_to_not_found_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_client_error(
        "get_secret_value",
        service_error_code="ResourceNotFoundException",
        service_message="no such secret",
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretNotFoundError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_access_denied_maps_to_auth_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_client_error(
        "get_secret_value",
        service_error_code="AccessDeniedException",
        service_message="not authorized",
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(AWSSecretsManagerAuthError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_invalid_client_token_maps_to_auth_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_client_error(
        "get_secret_value",
        service_error_code="InvalidClientTokenId",
        service_message="invalid creds",
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(AWSSecretsManagerAuthError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_unknown_error_code_maps_to_provider_error() -> None:
    provider, stubber = _stubbed_provider()
    stubber.add_client_error(
        "get_secret_value",
        service_error_code="InternalServiceError",
        service_message="try again",
        expected_params={"SecretId": SECRET_ID},
    )
    with pytest.raises(SecretProviderError):
        await provider.get(_ref())


@pytest.mark.asyncio
async def test_arn_as_path_is_passed_through() -> None:
    provider, stubber = _stubbed_provider()
    arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/slack-AbCdEf"
    stubber.add_response(
        "get_secret_value",
        {"Name": arn, "SecretString": "x"},
        expected_params={"SecretId": arn},
    )
    assert await provider.get(_ref(path=arn)) == "x"


@pytest.mark.asyncio
async def test_rejects_wrong_scheme() -> None:
    provider, _ = _stubbed_provider()
    with pytest.raises(SecretProviderError):
        await provider.get(SecretReference(scheme="env", path="FOO"))
