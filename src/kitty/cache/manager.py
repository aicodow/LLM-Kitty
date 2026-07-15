"""Two-tier cache manager for LLM provider responses.

Provides a CacheManager that uses diskcache as the primary store with
an optional Redis tier for faster lookups in distributed deployments.
Cache keys are built using SHA-256 hashing to match Promptfoo's scheme.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """Two-tier cache (diskcache primary + Redis optional).

    Stores LLM provider responses keyed by ``provider_id|prompt`` using
    a SHA-256 hash.  The disk tier uses :mod:`diskcache`; the optional
    Redis tier uses ``redis.asyncio``.

    Attributes:
        disabled (bool): When ``True`` all ``get`` / ``set`` / ``clear``
            operations are no-ops.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        redis_url: str | None = None,
        ttl: int = 86400,
    ) -> None:
        """Initialize the cache manager.

        The cache directory is resolved from (in order of precedence):

        1. The ``KITTY_CACHE_PATH`` environment variable.
        2. The *cache_dir* argument.
        3. ``~/.kitty/cache/``.

        The entire cache is disabled when the environment variable
        ``KITTY_DISABLE_CACHE`` is set to any non-empty value.

        Args:
            cache_dir: Explicit path to the disk cache directory.
            redis_url: Redis connection URL (e.g. ``redis://localhost:6379/0``).
                When ``None`` the Redis tier is skipped.
            ttl: Default TTL in seconds for cached entries (default 86400).
        """
        self.ttl: int = ttl
        self.disabled: bool = bool(os.environ.get("KITTY_DISABLE_CACHE"))
        self._redis = None
        self._redis_available: bool = False
        self._cache_dir: Path = self._resolve_cache_dir(cache_dir)
        self._disk = None

        if self.disabled:
            logger.info("Cache is disabled via KITTY_DISABLE_CACHE")
            return

        self._init_disk()
        self._init_redis(redis_url)

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_cache_dir(cache_dir: Path | None) -> Path:
        """Resolve the disk cache directory path."""
        env_path = os.environ.get("KITTY_CACHE_PATH")
        if env_path:
            return Path(env_path).expanduser().resolve()
        if cache_dir:
            return cache_dir.expanduser().resolve()
        return Path.home() / ".kitty" / "cache"

    def _init_disk(self) -> None:
        """Initialise the diskcache store."""
        try:
            import diskcache
        except ImportError as exc:
            logger.warning("diskcache not available, falling back to no-op cache: %s", exc)
            self.disabled = True
            return

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._disk = diskcache.Cache(str(self._cache_dir), disk=diskcache.JSONDisk)
        logger.debug("Disk cache initialised at %s", self._cache_dir)

    def _init_redis(self, redis_url: str | None) -> None:
        """Attempt to connect to the optional Redis backend."""
        if not redis_url:
            return
        try:
            import redis.asyncio  # type: ignore[import-untyped]
        except ImportError:
            logger.info("redis package not installed; Redis tier disabled")
            return

        try:
            self._redis = redis.asyncio.from_url(redis_url)
            self._redis_available = True
            logger.debug("Redis cache configured at %s", redis_url)
        except Exception as exc:
            logger.warning("Failed to connect to Redis at %s: %s", redis_url, exc)
            self._redis_available = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, provider_id: str, prompt: str) -> dict[str, Any] | None:
        """Retrieve a cached response.

        Args:
            provider_id: The LLM provider identifier.
            prompt: The raw prompt text.

        Returns:
            The cached response dict, or ``None`` on cache miss.
        """
        if self.disabled:
            return None

        key = self._build_key(provider_id, prompt)

        # Redis tier (faster, checked first).
        if self._redis_available and self._redis is not None:
            try:
                import redis.asyncio

                value = await self._redis.get(key)
                if value is not None:
                    logger.debug("cache_hit_redis  provider=%s key=%s", provider_id, key)
                    import json

                    return json.loads(value)
            except redis.asyncio.RedisError as exc:
                logger.debug("Redis get failed, falling back to disk: %s", exc)

        # Disk tier.
        if self._disk is not None:
            try:
                value = self._disk.get(key)
                if value is not None:
                    logger.debug("cache_hit_disk  provider=%s key=%s", provider_id, key)
                    return value
            except Exception as exc:
                logger.debug("Disk cache get failed: %s", exc)

        return None

    async def set(self, provider_id: str, prompt: str, response: dict[str, Any]) -> None:
        """Store a response in the cache.

        Args:
            provider_id: The LLM provider identifier.
            prompt: The raw prompt text.
            response: The response dict to cache.
        """
        if self.disabled:
            return

        key = self._build_key(provider_id, prompt)

        # Disk tier.
        if self._disk is not None:
            try:
                self._disk.set(key, response, expire=self.ttl)
            except Exception as exc:
                logger.debug("Disk cache set failed: %s", exc)

        # Redis tier.
        if self._redis_available and self._redis is not None:
            try:
                import json

                await self._redis.set(key, json.dumps(response), ex=self.ttl)
            except Exception as exc:
                logger.debug("Redis cache set failed: %s", exc)

    async def clear(self, provider_id: str | None = None) -> int:
        """Clear cached entries, optionally scoped to a provider.

        Args:
            provider_id: When provided, only keys with this prefix are
                removed.  When ``None`` all cached entries are cleared.

        Returns:
            The number of deleted entries.
        """
        if self.disabled:
            return 0

        count = 0

        # Disk tier.
        if self._disk is not None:
            try:
                if provider_id is None:
                    self._disk.clear()
                    count = -1  # unknown count
                else:
                    prefix = f"{provider_id}:"
                    keys = [k for k in self._disk]
                    to_del = [k for k in keys if k.startswith(prefix)]
                    for key in to_del:
                        del self._disk[key]
                    count = len(to_del)
            except Exception as exc:
                logger.debug("Disk cache clear failed: %s", exc)

        # Redis tier.
        if self._redis_available and self._redis is not None:
            try:
                import redis.asyncio

                pattern = f"{provider_id}:*" if provider_id else "*"
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=500)
                    if keys:
                        await self._redis.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
            except redis.asyncio.RedisError as exc:
                logger.debug("Redis cache clear failed: %s", exc)

        logger.info("Cleared %d cache entries (provider=%s)", count, provider_id)
        return count

    def stats(self) -> dict[str, Any]:
        """Return cache statistics.

        Returns:
            A dict with keys ``disk_size``, ``disk_path``,
            ``redis_available``, and ``disabled``.
        """
        disk_size = 0
        if not self.disabled and self._disk is not None:
            with contextlib.suppress(Exception):
                disk_size = self._disk.volume() if hasattr(self._disk, "volume") else 0

        return {
            "disk_size": disk_size,
            "disk_path": str(self._cache_dir),
            "redis_available": self._redis_available,
            "disabled": self.disabled,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_key(provider_id: str, prompt: str) -> str:
        """Build a cache key from a provider ID and prompt.

        Uses SHA-256 hashing of ``"provider_id|prompt"`` and returns
        ``"provider_id:hexdigest"`` — matching Promptfoo's cache key
        scheme exactly.

        Args:
            provider_id: The LLM provider identifier.
            prompt: The raw prompt text.

        Returns:
            A string key suitable for storage in both diskcache and Redis.
        """
        raw = f"{provider_id}|{prompt}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{provider_id}:{digest}"
