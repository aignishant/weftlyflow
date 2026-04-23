"""Unit tests for :class:`SecretProviderRegistry`."""

from __future__ import annotations

import pytest

from weftlyflow.credentials.external.env_provider import EnvSecretProvider
from weftlyflow.credentials.external.registry import (
    SecretProviderRegistry,
    UnknownSecretSchemeError,
)


@pytest.mark.asyncio
async def test_registry_dispatches_by_scheme() -> None:
    registry = SecretProviderRegistry()
    registry.register(EnvSecretProvider(env={"TOKEN": "abc"}))
    assert await registry.resolve("env:TOKEN") == "abc"


@pytest.mark.asyncio
async def test_registry_raises_for_unknown_scheme() -> None:
    registry = SecretProviderRegistry()
    registry.register(EnvSecretProvider(env={}))
    with pytest.raises(UnknownSecretSchemeError):
        await registry.resolve("vault:path")


def test_registry_rejects_duplicate_scheme() -> None:
    registry = SecretProviderRegistry()
    registry.register(EnvSecretProvider(env={}))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EnvSecretProvider(env={}))


def test_registry_lists_schemes_sorted() -> None:
    registry = SecretProviderRegistry()
    registry.register(EnvSecretProvider(env={}))
    assert registry.schemes() == ["env"]
