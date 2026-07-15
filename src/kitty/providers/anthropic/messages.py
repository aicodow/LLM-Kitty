"""Anthropic Messages provider with Extended Thinking and Tool Use support.

Provider ID format: ``anthropic:messages:<model>``
(e.g. ``anthropic:messages:claude-sonnet-4-20250514``).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from kitty.exceptions import ProviderAuthError, ProviderError, ProviderRateLimitError
from kitty.providers.base import BaseProvider
from kitty.types.eval import ProviderResponse

logger = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 120.0


class AnthropicMessagesProvider(BaseProvider):
    """Provider for the Anthropic Messages API.

    Supports the ``/v1/messages`` endpoint with Extended Thinking
    (``thinking``) and Tool Use (``tools`` / ``tool_choice``).

    Attributes:
        provider_id: Identifier including the model, e.g.
            ``"anthropic:messages:claude-sonnet-4-20250514"``.
    """

    provider_id: str

    def __init__(
        self,
        provider_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the HTTP client and authentication.

        Config keys:
            api_key: Anthropic API key (defaults to ``ANTHROPIC_API_KEY`` env var).
            base_url: Base URL (default ``https://api.anthropic.com``).
        """
        super().__init__(provider_id, config)

        api_key = self.config.get("api_key") or self.config.get("apiKey") or ""
        base_url = self.config.get("base_url") or self.config.get("apiBaseUrl") or DEFAULT_BASE_URL

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
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
        """Send a message to the Anthropic Messages API.

        Args:
            prompt: The user message text.
            context: Ignored by this provider.
            options: Optional overrides.  Supports ``max_tokens``,
                ``temperature``, ``top_p``, ``top_k``, ``stop_sequences``,
                ``thinking`` (Extended Thinking config),
                ``tools`` (Tool Use definitions), and ``tool_choice``.

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
            "max_tokens": merged_options.get("max_tokens", 4096),
            "messages": [{"role": "user", "content": prompt}],
        }

        # Extended Thinking
        thinking = merged_options.get("thinking")
        if thinking is not None:
            payload["thinking"] = thinking

        # Tool Use
        tools = merged_options.get("tools")
        if tools is not None:
            payload["tools"] = tools

        tool_choice = merged_options.get("tool_choice")
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        # Optional parameters
        for param in ("temperature", "top_p", "top_k", "stop_sequences", "metadata"):
            value = merged_options.get(param)
            if value is not None:
                payload[param] = value

        logger.debug(
            "anthropic_request",
            model=model,
            prompt_length=len(prompt),
        )

        try:
            response = await self._client.post("/v1/messages", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Anthropic request timed out: {exc}", status_code=None) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Anthropic request failed: {exc}", status_code=None) from exc

        return self._handle_response(response)

    def _resolve_model(self) -> str:
        """Extract the model name from the provider ID or config.

        The provider ID format is ``anthropic:messages:<model>``.  If no
        model segment is present, falls back to the ``model`` config key.
        """
        parts = self.provider_id.split(":", 2)
        if len(parts) >= 3 and parts[2]:
            return parts[2]
        return self.config.get("model", "claude-sonnet-4-20250514")

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """Extract readable text from Anthropic response content blocks.

        Handles ``type: text`` and ``type: thinking`` blocks, joining
        them with newlines.

        Args:
            data: The parsed JSON response body.

        Returns:
            Concatenated text from all content blocks.
        """
        parts: list[str] = []
        for block in data.get("content", []):
            block_type = block.get("type")
            if block_type == "text":
                parts.append(block.get("text", ""))
            elif block_type == "thinking":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else ""

    def _handle_response(self, response: httpx.Response) -> ProviderResponse:
        """Convert an HTTP response to a ProviderResponse."""
        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"Anthropic rate limit exceeded: {response.text}",
                status_code=429,
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"Anthropic authentication error ({response.status_code})",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Anthropic API error ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        output = self._extract_text(data)

        # Extract token usage
        usage = data.get("usage", {})
        token_usage: dict[str, int] = {}
        if "input_tokens" in usage:
            token_usage["input"] = usage["input_tokens"]
        if "output_tokens" in usage:
            token_usage["output"] = usage["output_tokens"]

        return ProviderResponse(
            output=output,
            token_usage=token_usage,
            cached=False,
            metadata={
                "model": data.get("model"),
                "stop_reason": data.get("stop_reason"),
                "stop_sequence": data.get("stop_sequence"),
            },
        )

    async def on_shutdown(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


__all__ = ["AnthropicMessagesProvider"]
