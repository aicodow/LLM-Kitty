"""Kitty types package — re-exports all Pydantic models for clean imports.

Usage:
    from kitty.types import (
        KittyConfig, TargetConfig, EvaluateOptions, TestCase,
        GradingResult, EvaluateResult, EvaluateStats, ...
    )
"""

from kitty.types.config import (
    EvaluateOptions,
    KittyConfig,
    OutputConfig,
    RedteamConfig,
    RedteamPluginRef,
    TargetConfig,
    TracingConfig,
)
from kitty.types.eval import (
    CompletedPrompt,
    EvaluateResult,
    EvaluateStats,
    GradingResult,
    Prompt,
    ProviderConfig,
    ProviderResponse,
    ResultFailureReason,
    Severity,
    TargetType,
    TestCase,
)

__all__ = [
    "CompletedPrompt",
    "EvaluateOptions",
    "EvaluateResult",
    "EvaluateStats",
    "GradingResult",
    # Config models
    "KittyConfig",
    "OutputConfig",
    "Prompt",
    "ProviderConfig",
    "ProviderResponse",
    "RedteamConfig",
    "RedteamPluginRef",
    "ResultFailureReason",
    # Eval models
    "Severity",
    "TargetConfig",
    "TargetType",
    "TestCase",
    "TracingConfig",
]
