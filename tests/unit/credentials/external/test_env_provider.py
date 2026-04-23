"""Unit tests for :class:`EnvSecretProvider`."""

from __future__ import annotations

import pytest

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)
from weftlyflow.credentials.external.env_provider import EnvSecretProvider


@pytest.mark.asyncio
async def test_env_provider_returns_variable_value() -> None:
    provider = EnvSecretProvider(env={"SLACK_TOKEN": "xoxb-123"})
    value = await provider.get(SecretReference(scheme="env", path="SLACK_TOKEN"))
    assert value == "xoxb-123"


@pytest.mark.asyncio
async def test_env_provider_raises_when_variable_missing() -> None:
    provider = EnvSecretProvider(env={})
    with pytest.raises(SecretNotFoundError):
        await provider.get(SecretReference(scheme="env", path="SLACK_TOKEN"))


@pytest.mark.asyncio
async def test_env_provider_rejects_wrong_scheme() -> None:
    provider = EnvSecretProvider(env={"X": "y"})
    with pytest.raises(SecretProviderError):
        await provider.get(SecretReference(scheme="vault", path="X"))


@pytest.mark.asyncio
async def test_env_provider_rejects_field_fragment() -> None:
    provider = EnvSecretProvider(env={"X": "y"})
    with pytest.raises(SecretProviderError):
        await provider.get(SecretReference(scheme="env", path="X", field="k"))


@pytest.mark.asyncio
async def test_env_provider_falls_back_to_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEFTLYFLOW_EXT_TEST_VAR", "hello")
    provider = EnvSecretProvider()
    value = await provider.get(
        SecretReference(scheme="env", path="WEFTLYFLOW_EXT_TEST_VAR")
    )
    assert value == "hello"
