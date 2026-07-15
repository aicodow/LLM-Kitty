"""
Provider Registry -- discovery, instantiation, and caching.

The registry is the single source of truth for resolving a provider ID
string (e.g. ``"openai:chat:gpt-4.1"``) to a concrete :class:`BaseProvider`
instance.  It supports:

* **Built-in providers** registered via ``importlib.metadata`` entry points
  (``kitty.providers`` group).
* **Dynamic registration** for custom providers injected at runtime.
* **Lazy instantiation** -- providers are only created on first use.
* **Caching** -- the same (provider_id, config_hash) pair reuses the instance.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from importlib.metadata import entry_points
from typing import Any

import structlog

from kitty.exceptions import ProviderError
from kitty.providers.base import BaseProvider

logger = structlog.get_logger(__name__)

# Keywords whose values are stripped before cache-key computation.
_SECRET_KEYWORDS = frozenset({"apikey", "api_key", "secret", "token", "password"})


def _is_secret_key(key: str) -> bool:
    """Check whether *key* looks like a credential field (case-insensitive)."""
    return key.lower() in _SECRET_KEYWORDS


def _lazy_import(module_path: str, class_name: str) -> type[BaseProvider]:
    """Return a factory class that lazily imports *class_name* from *module_path*.

    The returned class can be registered with the registry and will only
    import the target module when first instantiated.  The imported class
    is cached so subsequent instantiations skip the import overhead.
    """

    class _LazyFactory:
        _resolved: type[BaseProvider] | None = None

        def __new__(cls, *args: Any, **kwargs: Any) -> BaseProvider:
            if cls._resolved is None:
                mod = importlib.import_module(module_path)
                cls._resolved = getattr(mod, class_name)
            return cls._resolved(*args, **kwargs)

    _LazyFactory.__name__ = class_name
    _LazyFactory.__qualname__ = class_name
    return _LazyFactory  # type: ignore[return-value]


class ProviderRegistry:
    """Central registry for LLM provider discovery and instantiation."""

    def __init__(self) -> None:
        self._factories: dict[str, type[BaseProvider]] = {}
        self._instances: dict[str, BaseProvider] = {}
        self._discovered = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider_id: str, factory: type[BaseProvider]) -> None:
        """Register a provider factory under *provider_id*.

        Args:
            provider_id: Unique identifier (e.g. ``"openai:chat"``).
            factory: A class that accepts ``(provider_id, config)`` and
                returns a :class:`BaseProvider` instance.
        """
        self._factories[provider_id] = factory
        logger.debug("provider_registered", provider_id=provider_id)

    async def discover_builtins(self) -> None:
        """Register all built-in provider factories as lazy imports.

        Also discovers third-party providers registered via the
        ``kitty.providers`` entry-point group.
        """
        if self._discovered:
            return
        self.register(
            "openai:chat",
            _lazy_import("kitty.providers.openai.chat", "OpenAiChatProvider"),
        )
        self.register(
            "anthropic:messages",
            _lazy_import("kitty.providers.anthropic.messages", "AnthropicMessagesProvider"),
        )
        self.register(
            "google:gemini",
            _lazy_import("kitty.providers.google.gemini", "GeminiProvider"),
        )
        self.register(
            "bedrock:invoke",
            _lazy_import("kitty.providers.bedrock.invoke", "BedrockProvider"),
        )
        self.register(
            "http",
            _lazy_import("kitty.providers.http", "HttpProvider"),
        )
        self.register(
            "echo",
            _lazy_import("kitty.providers.echo", "EchoProvider"),
        )
        try:
            for ep in entry_points(group="kitty.providers"):
                self.register(ep.name, ep.load())
        except TypeError:
            pass
        self._discovered = True

    # ------------------------------------------------------------------
    # Factory resolution
    # ------------------------------------------------------------------

    def _resolve_factory(self, provider_id: str) -> type[BaseProvider]:
        """Resolve a provider ID to its factory.

        Tries exact match first, then falls back to the longest matching
        family prefix (e.g. ``"openai:chat:gpt-4"`` -> ``"openai:chat"``).

        Raises:
            ProviderError: If no factory matches *provider_id*.
        """
        if provider_id in self._factories:
            return self._factories[provider_id]
        parts = provider_id.split(":")
        for n in range(len(parts) - 1, 0, -1):
            prefix = ":".join(parts[:n])
            if prefix in self._factories:
                return self._factories[prefix]
        raise ProviderError(f"Unknown provider: {provider_id!r}")

    # ------------------------------------------------------------------
    # Instance lifecycle
    # ------------------------------------------------------------------

    async def create(
        self,
        provider_id: str,
        config: dict[str, Any] | None = None,
    ) -> BaseProvider:
        """Create (or retrieve from cache) a provider instance.

        Caching uses a key of ``provider_id:SHA256(config_minus_secrets)[:16]``
        so that two instances sharing the same configuration (apart from
        credential values) reuse the same cached object.

        Args:
            provider_id: Provider identifier (e.g. ``"openai:chat:gpt-4"``).
            config: Provider-specific configuration dictionary.

        Returns:
            A :class:`BaseProvider` instance.
        """
        await self.discover_builtins()
        factory = self._resolve_factory(provider_id)
        cache_key = self._cache_key(provider_id, config)
        if cache_key in self._instances:
            logger.debug("provider_cache_hit", provider_id=provider_id)
            return self._instances[cache_key]
        config = config or {}
        instance = factory(provider_id=provider_id, config=config)
        await instance.on_init()
        self._instances[cache_key] = instance
        logger.info("provider_created", provider_id=provider_id)
        return instance

    async def shutdown(self) -> None:
        """Shut down all cached provider instances gracefully.

        Calls :meth:`BaseProvider.on_shutdown` on every instance.
        Exceptions from individual providers are collected and reported
        together so that all providers get a chance to clean up.
        """
        errors: list[tuple[str, Exception]] = []
        for key, instance in self._instances.items():
            try:
                await instance.on_shutdown()
            except Exception as exc:
                errors.append((key, exc))
                logger.warning(
                    "provider_shutdown_error",
                    provider_key=key,
                    error=str(exc),
                )

        self._instances.clear()

        if errors:
            messages = "; ".join(f"{key}: {exc}" for key, exc in errors)
            raise RuntimeError(f"Errors during provider shutdown: {messages}")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(provider_id: str, config: dict[str, Any] | None) -> str:
        """Compute a deterministic cache key.

        Secret keys are stripped before hashing so that two instances
        with different credential values but otherwise identical
        configuration share the same cache slot (callers are responsible
        for isolating credentials at a higher layer).
        """
        safe = {k: v for k, v in (config or {}).items() if not _is_secret_key(k)}
        canonical = json.dumps(safe, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        return f"{provider_id}:{digest}"

    def list_registered(self) -> list[str]:
        """Return a sorted list of registered provider identifiers."""
        return sorted(self._factories.keys())
