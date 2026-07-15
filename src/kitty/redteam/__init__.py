"""Kitty red teaming framework - top-level exports.

Red teaming utilities for testing LLM safety and security
through automated adversarial test generation and execution.
"""

from __future__ import annotations

from kitty.redteam.plugins.base import PluginContext, RedteamPluginBase
from kitty.redteam.plugins.manifest import PluginManifest
from kitty.redteam.plugins.registry import PluginRegistry
from kitty.redteam.strategies.base import BaseStrategy, StrategyPipeline

__all__ = [
    "BaseStrategy",
    "PluginContext",
    "PluginManifest",
    "PluginRegistry",
    "RedteamPluginBase",
    "StrategyPipeline",
]
