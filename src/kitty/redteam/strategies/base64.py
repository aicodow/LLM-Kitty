"""Base64 encoding strategy for red team testing.

Encodes each test prompt to base64 to test how providers handle
encoded content.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from kitty.redteam.plugins.base import TestCase
from kitty.redteam.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class Base64Strategy(BaseStrategy):
    """Strategy that base64-encodes each test prompt.

    This tests whether a provider can be bypassed by encoding
    adversarial input in base64.

    Attributes:
        strategy_id: ``"base64"``
        strategy_label: ``"Base64 Encoding"``
    """

    strategy_id: str = "base64"
    strategy_label: str = "Base64 Encoding"

    async def transform(
        self,
        test_cases: list[TestCase],
        config: dict[str, Any] | None = None,
    ) -> list[TestCase]:
        """Base64-encode the prompt of each test case.

        The original prompt is stored in ``metadata["original_prompt"]``
        and the strategy identifier is stored in
        ``metadata["strategy"]``.

        Args:
            test_cases: The test cases to transform.
            config: Optional configuration (unused).

        Returns:
            A new list of test cases with base64-encoded prompts.
        """
        transformed: list[TestCase] = []
        for case in test_cases:
            raw_bytes = case.prompt.encode("utf-8")
            encoded = base64.b64encode(raw_bytes).decode("ascii")

            new_metadata = dict(case.metadata)
            new_metadata["original_prompt"] = case.prompt
            new_metadata["strategy"] = "base64"

            transformed.append(
                TestCase(
                    prompt=encoded,
                    plugin_id=case.plugin_id,
                    strategy_id=self.strategy_id,
                    assertions=list(case.assertions),
                    metadata=new_metadata,
                    severity=case.severity,
                    vars=dict(case.vars),
                )
            )

        logger.debug(
            "Base64Strategy: encoded %d test case(s)",
            len(transformed),
        )
        return transformed
