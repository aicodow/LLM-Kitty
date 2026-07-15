"""Abstract base class for red team strategies and the pipeline runner.

A strategy is a transformation applied to generated test cases before
they are dispatched to a provider. Strategies are composed sequentially
in a :class:`StrategyPipeline`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from kitty.redteam.plugins.base import TestCase

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Abstract base class for all red team strategies.

    A strategy transforms a list of test cases -- typically by
    modifying the prompt text -- and returns the modified list.
    Strategies are chained together via :class:`StrategyPipeline`.

    Attributes:
        strategy_id: Unique identifier for this strategy.
        strategy_label: Human-readable label (defaults to ``strategy_id``).
    """

    strategy_id: str = ""
    strategy_label: str = ""

    def __init__(self) -> None:
        """Initialize the strategy and set the default label."""
        if not self.strategy_label:
            self.strategy_label = self.strategy_id

    @abstractmethod
    async def transform(
        self,
        test_cases: list[TestCase],
        config: dict[str, Any] | None = None,
    ) -> list[TestCase]:
        """Transform a list of test cases.

        Subclasses must override this method to apply the strategy's
        transformation logic (e.g., encoding prompts, wrapping them
        in jailbreak prefixes).

        Args:
            test_cases: The list of test cases to transform.
            config: Optional configuration dictionary for the strategy.

        Returns:
            The transformed list of test cases (may be a new list).
        """
        ...


class StrategyPipeline:
    """A sequential pipeline of strategies applied to test cases.

    Each strategy's output is fed as input to the next strategy.

    Attributes:
        strategies: The ordered list of strategies in this pipeline.
    """

    def __init__(self, strategies: list[BaseStrategy]) -> None:
        """Initialize the pipeline with an ordered list of strategies.

        Args:
            strategies: The strategies to apply, in order.
        """
        self.strategies = list(strategies)

    async def run(
        self,
        test_cases: list[TestCase],
        config: dict[str, Any] | None = None,
    ) -> list[TestCase]:
        """Run all strategies sequentially over the test cases.

        Args:
            test_cases: The input test cases.
            config: Optional configuration passed to each strategy.

        Returns:
            The fully transformed test cases after all strategies.
        """
        current = list(test_cases)
        for strategy in self.strategies:
            logger.debug(
                "Applying strategy %s to %d test case(s)",
                strategy.strategy_id,
                len(current),
            )
            current = await strategy.transform(current, config=config)
        return current

    def __repr__(self) -> str:
        """Return a human-readable representation of the pipeline."""
        names = [s.strategy_id for s in self.strategies]
        return f"StrategyPipeline({', '.join(names)})"
