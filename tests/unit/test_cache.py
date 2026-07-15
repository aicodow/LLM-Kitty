"""Tests for the cache manager."""

from __future__ import annotations

import pytest

from kitty.cache import CacheManager


@pytest.fixture
def cache() -> CacheManager:
    """Return a CacheManager instance for testing."""
    return CacheManager(cache_dir=None)  # Will use default ~/.kitty/cache


class TestCacheManager:
    """Tests for the CacheManager class."""

    async def test_set_and_get(self) -> None:
        """A value stored in the cache should be retrievable."""
        cache = CacheManager(cache_dir=None)
        await cache.set("openai:chat:gpt-4", "Hello", {"result": "hello"})
        value = await cache.get("openai:chat:gpt-4", "Hello")
        assert value == {"result": "hello"}

    async def test_cache_miss_returns_none(self) -> None:
        """Requesting a non-existent key should return None."""
        cache = CacheManager(cache_dir=None)
        value = await cache.get("unknown:provider", "nonexistent prompt")
        assert value is None

    async def test_overwrite_existing_key(self) -> None:
        """Overwriting an existing key should update its value."""
        cache = CacheManager(cache_dir=None)
        await cache.set("test:provider", "key", {"value": "old-value"})
        await cache.set("test:provider", "key", {"value": "new-value"})
        value = await cache.get("test:provider", "key")
        assert value == {"value": "new-value"}

    async def test_clear_all(self) -> None:
        """Clearing all entries should empty the cache."""
        cache = CacheManager(cache_dir=None)
        await cache.set("provider-a", "prompt1", {"data": "value-a"})
        await cache.set("provider-b", "prompt2", {"data": "value-b"})
        await cache.clear()
        assert await cache.get("provider-a", "prompt1") is None
        assert await cache.get("provider-b", "prompt2") is None

    async def test_clear_by_provider(self) -> None:
        """Clearing by provider prefix should only remove matching entries."""
        cache = CacheManager(cache_dir=None)
        await cache.set("openai:chat:gpt-4", "prompt1", {"response": "response1"})
        await cache.set("openai:chat:gpt-4", "prompt2", {"response": "response2"})
        await cache.set("anthropic:claude", "prompt3", {"response": "response3"})

        await cache.clear(provider_id="openai:chat:gpt-4")

        assert await cache.get("openai:chat:gpt-4", "prompt1") is None
        assert await cache.get("openai:chat:gpt-4", "prompt2") is None
        assert await cache.get("anthropic:claude", "prompt3") is not None
