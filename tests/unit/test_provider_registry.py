"""Tests for the ProviderRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kitty.core.exceptions import ProviderError
from kitty.core.provider import BaseProvider, ProviderResponse
from kitty.providers.registry import ProviderRegistry


class _DummyProvider(BaseProvider):
    """Minimal BaseProvider subclass for testing registry behavior."""

    provider_id: str = "dummy:test:provider"

    async def call_api(self, prompt: str, **kwargs) -> ProviderResponse:
        return ProviderResponse(output="dummy response")

    async def id(self) -> str:
        return "dummy:test:provider"


class AnotherDummyProvider(BaseProvider):
    """Another dummy provider for testing distinct configs."""

    provider_id: str = "dummy:other:provider"

    async def call_api(self, prompt: str, **kwargs) -> ProviderResponse:
        return ProviderResponse(output="other dummy response")

    async def id(self) -> str:
        return "dummy:other:provider"


class TestProviderRegistry:
    """Tests for the ProviderRegistry class."""

    async def test_register_and_create(self) -> None:
        """Registering a provider class and creating it should yield a valid instance."""
        registry = ProviderRegistry()
        provider = registry.create("dummy:test:provider", _DummyProvider)
        assert isinstance(provider, _DummyProvider)
        pid = await provider.id()
        assert pid == "dummy:test:provider"
        await registry.shutdown()

    async def test_create_caches_instance(self) -> None:
        """Creating a provider with the same config should return the same instance."""
        registry = ProviderRegistry()
        provider_a = registry.create("dummy:test:provider", _DummyProvider)
        provider_b = registry.create("dummy:test:provider", _DummyProvider)
        assert provider_a is provider_b
        await registry.shutdown()

    async def test_different_config_different_instance(self) -> None:
        """Creating providers with different configs should return different instances."""
        registry = ProviderRegistry()
        provider_a = registry.create("dummy:test:provider", _DummyProvider)
        provider_b = registry.create("dummy:other:provider", AnotherDummyProvider)
        assert provider_a is not provider_b
        await registry.shutdown()

    async def test_unknown_provider_raises_error(self) -> None:
        """Requesting an unregistered provider ID should raise ProviderError."""
        registry = ProviderRegistry()
        with pytest.raises(ProviderError, match="No provider registered"):
            registry.get("nonexistent:provider")
        await registry.shutdown()

    async def test_list_registered(self) -> None:
        """list_registered should include all registered provider IDs."""
        registry = ProviderRegistry()
        registry.create("dummy:test:provider", _DummyProvider)
        registry.create("dummy:other:provider", AnotherDummyProvider)
        registered = registry.list_registered()
        assert "dummy:test:provider" in registered
        assert "dummy:other:provider" in registered
        await registry.shutdown()

    async def test_shutdown_calls_on_shutdown(self) -> None:
        """Shutdown should call on_shutdown on all registered providers."""
        registry = ProviderRegistry()
        provider = registry.create("dummy:test:provider", _DummyProvider)
        provider.on_shutdown = AsyncMock()  # type: ignore[assignment]
        await registry.shutdown()
        provider.on_shutdown.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_cache_key_no_secrets(self) -> None:
        """Cache key should not contain the raw apiKey value."""
        from kitty.providers.registry import _make_cache_key

        config_with_secret = {"apiKey": "sk-secret-12345", "model": "gpt-4"}
        key = _make_cache_key(config_with_secret)
        assert "sk-secret-12345" not in key
        assert "gpt-4" in key

    async def test_cache_key_stable(self) -> None:
        """The same config should always produce the same cache key."""
        from kitty.providers.registry import _make_cache_key

        config_a = {"model": "gpt-4", "temperature": 0.7}
        config_b = {"model": "gpt-4", "temperature": 0.7}
        assert _make_cache_key(config_a) == _make_cache_key(config_b)
