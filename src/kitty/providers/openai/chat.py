"""OpenAI Chat Completions provider.

Supports all OpenAI-compatible APIs via the ``/v1/chat/completions`` endpoint,
including Azure OpenAI Service and local LLM servers.

Provider ID format: ``openai:chat:<model>`` (e.g. ``openai:chat:gpt-4``).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from kitty.exceptions import ProviderAuthError, ProviderError, ProviderRateLimitError
from kitty.providers.base import BaseProvider
from kitty.types.eval import ProviderResponse

logger = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60.0


class OpenAiChatProvider(BaseProvider):
    """Provider for OpenAI-compatible chat completion APIs.

    Attributes:
        provider_id: Identifier including the model, e.g. ``"openai:chat:gpt-4"``.
    """

    provider_id: str

    def __init__(
        self,
        provider_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the HTTP client and authentication.

        Config keys:
            api_key: OpenAI API key (defaults to ``OPENAI_API_KEY`` env var).
            base_url: Base URL for the API (default ``https://api.openai.com/v1``).
        """
        super().__init__(provider_id, config)

        api_key = self.config.get("api_key") or self.config.get("apiKey") or ""
        base_url = self.config.get("base_url") or self.config.get("apiBaseUrl") or DEFAULT_BASE_URL

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(DEFAULT_TIMEOUT),
        )

    async def call_api(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Send a chat completion request to the OpenAI-compatible API.

        Args:
            prompt: The user message to send.
            context: Ignored by this provider.
            options: Optional overrides (e.g. ``{"temperature": 0.5}``,
                ``{"max_tokens": 2048}``).

        Returns:
            ProviderResponse with the generated text and token usage.

        Raises:
            ProviderRateLimitError: On HTTP 429.
            ProviderAuthError: On HTTP 401 or 403.
            ProviderError: On other HTTP or transport errors.
        """
        model = self._resolve_model()
        merged_options = {**(options or {}), **(self.config or {})}

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }

        # Merge optional parameters (per-call options take precedence)
        for param in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
        ):
            value = merged_options.get(param)
            if value is not None:
                payload[param] = value

        # Default temperature (OpenAI default is 1.0, but we provide a
        # sensible default when none is explicitly set).
        payload.setdefault("temperature", 1.0)

        logger.debug(
            "openai_request",
            model=model,
            prompt_length=len(prompt),
        )

        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"OpenAI request timed out: {exc}", status_code=None) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"OpenAI request failed: {exc}", status_code=None) from exc

        return self._handle_response(response)

    def _resolve_model(self) -> str:
        """Extract the model name from the provider ID or config.

        The provider ID format is ``openai:chat:<model>``.  If no model
        segment is present, falls back to the ``model`` config key.
        """
        parts = self.provider_id.split(":", 2)
        if len(parts) >= 3 and parts[2]:
            return parts[2]
        return self.config.get("model", "gpt-4")

    def _handle_response(self, response: httpx.Response) -> ProviderResponse:
        """Convert an HTTP response to a ProviderResponse."""
        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"OpenAI rate limit exceeded: {response.text}",
                status_code=429,
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"OpenAI authentication error ({response.status_code})",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"OpenAI API error ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()

        # Extract text from response
        try:
            output = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            output = ""

        # Extract token usage
        usage = data.get("usage", {})
        token_usage: dict[str, int] = {}
        if "prompt_tokens" in usage:
            token_usage["prompt"] = usage["prompt_tokens"]
        if "completion_tokens" in usage:
            token_usage["completion"] = usage["completion_tokens"]
        if "total_tokens" in usage:
            token_usage["total"] = usage["total_tokens"]

        return ProviderResponse(
            output=output,
            token_usage=token_usage,
            cached=False,
            metadata={
                "model": data.get("model"),
                "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
            },
        )

    async def on_shutdown(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


__all__ = ["OpenAiChatProvider"]
