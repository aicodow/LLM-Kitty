"""Tests for the ProviderRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kitty.exceptions import ProviderError
from kitty.providers.base import BaseProvider
from kitty.providers.registry import ProviderRegistry
from kitty.types.eval import ProviderResponse


class _DummyProvider(BaseProvider):
    """Minimal BaseProvider subclass for testing registry behavior."""

    provider_id: str = "dummy:test:provider"

    async def call_api(self, _prompt: str, **_kwargs) -> ProviderResponse:
        return ProviderResponse(output="dummy response")

    async def id(self) -> str:
        return "dummy:test:provider"


class AnotherDummyProvider(BaseProvider):
    """Another dummy provider for testing distinct configs."""

    provider_id: str = "dummy:other:provider"

    async def call_api(self, _prompt: str, **_kwargs) -> ProviderResponse:
        return ProviderResponse(output="other dummy response")

    async def id(self) -> str:
        return "dummy:other:provider"


class TestProviderRegistry:
    """Tests for the ProviderRegistry class."""

    async def test_register_and_create(self) -> None:
        """Registering a provider class and creating it should yield a valid instance."""
        registry = ProviderRegistry()
        registry.register("dummy:test:provider", _DummyProvider)
        provider = await registry.create("dummy:test:provider")
        assert isinstance(provider, _DummyProvider)
        pid = await provider.id()
        assert pid == "dummy:test:provider"
        await registry.shutdown()

    async def test_create_caches_instance(self) -> None:
        """Creating a provider with the same config should return the same instance."""
        registry = ProviderRegistry()
        registry.register("dummy:test:provider", _DummyProvider)
        provider_a = await registry.create("dummy:test:provider")
        provider_b = await registry.create("dummy:test:provider")
        assert provider_a is provider_b
        await registry.shutdown()

    async def test_different_config_different_instance(self) -> None:
        """Creating providers with different configs should return different instances."""
        registry = ProviderRegistry()
        registry.register("dummy:test:provider", _DummyProvider)
        registry.register("dummy:other:provider", AnotherDummyProvider)
        provider_a = await registry.create("dummy:test:provider", {"key": "a"})
        provider_b = await registry.create("dummy:other:provider", {"key": "b"})
        assert provider_a is not provider_b
        await registry.shutdown()

    async def test_unknown_provider_raises_error(self) -> None:
        """Requesting an unregistered provider ID should raise ProviderError."""
        registry = ProviderRegistry()
        with pytest.raises(ProviderError, match="Unknown provider"):
            await registry.create("nonexistent:provider")
        await registry.shutdown()

    async def test_list_registered(self) -> None:
        """list_registered should include all registered provider IDs."""
        registry = ProviderRegistry()
        registry.register("dummy:test:provider", _DummyProvider)
        registry.register("dummy:other:provider", AnotherDummyProvider)
        registered = registry.list_registered()
        assert "dummy:test:provider" in registered
        assert "dummy:other:provider" in registered
        await registry.shutdown()

    async def test_shutdown_calls_on_shutdown(self) -> None:
        """Shutdown should call on_shutdown on all registered providers."""
        registry = ProviderRegistry()
        registry.register("dummy:test:provider", _DummyProvider)
        provider = await registry.create("dummy:test:provider")
        provider.on_shutdown = AsyncMock()  # type: ignore[assignment]
        await registry.shutdown()
        provider.on_shutdown.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_cache_key_no_secrets(self) -> None:
        """Cache key should not contain the raw apiKey value."""
        config_with_secret = {"apiKey": "sk-secret-12345", "model": "gpt-4"}
        key = ProviderRegistry._cache_key("test", config_with_secret)
        assert "sk-secret-12345" not in key
        assert "gpt-4" in key

    async def test_cache_key_stable(self) -> None:
        """The same config should always produce the same cache key."""
        config_a = {"model": "gpt-4", "temperature": 0.7}
        config_b = {"model": "gpt-4", "temperature": 0.7}
        assert ProviderRegistry._cache_key("test", config_a) == ProviderRegistry._cache_key(
            "test", config_b
        )
