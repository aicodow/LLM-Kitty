"""Strategy system for the Kitty red teaming framework.

Strategies transform test prompts (e.g., encoding, jailbreaking)
before they are sent to a target provider.
"""

from __future__ import annotations

from kitty.redteam.strategies.base import BaseStrategy, StrategyPipeline

__all__ = [
    "BaseStrategy",
    "StrategyPipeline",
]
