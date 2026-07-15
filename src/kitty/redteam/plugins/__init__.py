"""Plugin system for the Kitty red teaming framework.

Provides the base classes, manifests, and registry infrastructure
for discovering and loading red team test plugins.
"""

from __future__ import annotations

from kitty.redteam.plugins.base import PluginContext, RedteamPluginBase
from kitty.redteam.plugins.manifest import PluginManifest
from kitty.redteam.plugins.registry import PluginRegistry

__all__ = [
    "PluginContext",
    "PluginManifest",
    "PluginRegistry",
    "RedteamPluginBase",
]
