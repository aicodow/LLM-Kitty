"""Echo provider -- echoes the prompt back as the response (for testing).

Useful for testing and debugging pipeline flows without calling an external
API.  Provider ID: ``echo``.
"""

from __future__ import annotations

from typing import Any

from kitty.providers.base import BaseProvider
from kitty.types.eval import ProviderResponse


class EchoProvider(BaseProvider):
    """Provider that echoes the input prompt as the output.

    Provider ID: ``echo``.
    """

    provider_id = "echo"

    async def call_api(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        """Return the prompt verbatim as the provider output.

        Args:
            prompt: The text to echo back.
            context: Ignored.
            options: Ignored.

        Returns:
            ProviderResponse with ``output`` set to *prompt* and zero
            token usage.
        """
        return ProviderResponse(
            output=prompt,
            token_usage={"total": 0},
            cached=False,
        )


__all__ = ["EchoProvider"]
