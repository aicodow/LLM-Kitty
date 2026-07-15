"""
Abstract base class for all LLM providers.

Every provider — whether a cloud API (OpenAI, Anthropic), a local model
(Ollama), or a custom HTTP endpoint — implements this interface.  The
evaluation engine calls :meth:`call_api` for each prompt and expects a
normalised :class:`~kitty.types.eval.ProviderResponse` back.

Convenience re-exports:
    ProviderError, ProviderAuthError, ProviderRateLimitError
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from kitty.exceptions import ProviderAuthError, ProviderError, ProviderRateLimitError
from kitty.types.eval import ProviderResponse


class BaseProvider(ABC):
    """Abstract base for every LLM provider adapter.

    Attributes:
        provider_id: Unique identifier for this provider instance
            (e.g. ``"openai:chat:gpt-4"``).
        label: Optional human-readable label.
        config: Provider-specific configuration dictionary.
    """

    provider_id: str
    label: str | None = None
    config: dict[str, Any]

    def __init__(self, provider_id: str, config: dict[str, Any] | None = None) -> None:
        self.provider_id = provider_id
        self.config = config or {}

    @abstractmethod
    async def call_api(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Call the provider's API with the given prompt.

        Args:
            prompt: The input prompt text.
            context: Optional contextual data for the request.
            options: Optional overrides for provider-specific settings
                (e.g. temperature, max_tokens).

        Returns:
            A :class:`ProviderResponse` containing the generated output.

        Raises:
            ProviderRateLimitError: If the API rate-limits the request.
            ProviderAuthError: If authentication fails.
            ProviderError: For other API errors.
        """
        ...

    async def on_init(self) -> None:
        """Lifecycle hook: called once after instantiation.

        Override to perform async initialisation (connection pooling,
        authentication handshakes, etc.).
        """
        return

    async def on_shutdown(self) -> None:
        """Lifecycle hook: close connections, release resources.

        Override to close HTTP clients, database connections, etc.
        """
        return

    def id(self) -> str:
        """Return the provider identifier."""
        return self.provider_id

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.provider_id!r})>"


__all__ = [
    "BaseProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderResponse",
]
