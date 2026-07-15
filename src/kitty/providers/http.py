"""Generic HTTP provider with template-based request construction.

Sends prompts to arbitrary HTTP endpoints using a configurable request
template.  Provider ID: ``http``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from kitty.exceptions import ProviderError
from kitty.providers.base import BaseProvider
from kitty.types.eval import ProviderResponse

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT = 60.0


class HttpProvider(BaseProvider):
    """Generic provider that sends prompts to arbitrary HTTP endpoints.

    Configuration (``config`` dict):
        url (str, required):
            Target URL.
        method (str):
            HTTP method, default ``"POST"``.
        headers (dict):
            HTTP headers to include.
        body (str):
            Request body template.  ``{{prompt}}`` is replaced with the
            prompt text, ``{{context}}`` with the JSON-serialised context.
            Defaults to ``'{"prompt": "{{prompt}}"}'``.
        output_path (str, optional):
            Dot-separated JSON path to extract the output text from the
            response body (e.g. ``"choices.0.message.content"``).  If
            omitted, the full response text is used.
        timeout (float):
            Request timeout in seconds, default ``60.0``.

    Provider ID: ``http``.
    """

    provider_id = "http"

    def __init__(
        self,
        provider_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the HTTP client.

        Config keys:
            url: Target URL (required).
            timeout: Request timeout in seconds.
        """
        super().__init__(provider_id, config)
        timeout = self.config.get("timeout", DEFAULT_TIMEOUT)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def call_api(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Send a templated HTTP request with the given prompt.

        Args:
            prompt: The prompt text to substitute into the body template.
            context: Optional data; ``{{context}}`` in the body template
                is replaced with the JSON-serialised context dict.
            options: Ignored.

        Returns:
            ProviderResponse with the response text or extracted value.

        Raises:
            ValueError: If no ``url`` is configured.
            ProviderError: If the HTTP request fails.
        """
        url = self.config.get("url")
        if not url:
            raise ValueError("HttpProvider requires a 'url' in config")

        method = self.config.get("method", "POST").upper()
        headers = dict(self.config.get("headers", {}))
        body_template = self.config.get("body", '{"prompt": "{{prompt}}"}')

        # Render template variables
        body = body_template.replace("{{prompt}}", prompt)
        if context is not None:
            body = body.replace("{{context}}", json.dumps(context, default=str))

        logger.debug(
            "http_request",
            url=url,
            method=method,
            prompt_length=len(prompt),
        )

        try:
            response = await self._client.request(
                method,
                url,
                content=body,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderError(f"HTTP request timed out: {exc}", status_code=None) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"HTTP error ({exc.response.status_code}): {exc.response.text}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"HTTP request failed: {exc}", status_code=None) from exc

        # Extract output
        data: dict[str, Any] | None = None
        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            data = response.json()
            output = self._extract_json_path(data, self.config.get("output_path"))
            if output is None:
                output = response.text
        else:
            output = response.text

        return ProviderResponse(
            output=output,
            token_usage={},
            cached=False,
            metadata=data,
        )

    @staticmethod
    def _extract_json_path(
        data: Any,
        path: str | None,
    ) -> str | None:
        """Extract a value from nested JSON using a dot-separated path.

        Args:
            data: Parsed JSON data (dict or list).
            path: Dot-separated path, e.g. ``"choices.0.message.content"``.

        Returns:
            The string value at the path, or ``None`` if *path* is
            ``None`` or cannot be traversed.
        """
        if path is None:
            return None

        current: Any = data
        for key in path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    current = current[int(key)]
                except (ValueError, IndexError, TypeError):
                    return None
            else:
                return None

        if current is None:
            return None
        if isinstance(current, str):
            return current
        return json.dumps(current, default=str)

    async def on_shutdown(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


__all__ = ["HttpProvider"]
