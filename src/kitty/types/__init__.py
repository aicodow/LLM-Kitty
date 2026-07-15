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
    # Config models
    "KittyConfig",
    "TargetConfig",
    "EvaluateOptions",
    "RedteamConfig",
    "RedteamPluginRef",
    "TracingConfig",
    "OutputConfig",
    # Eval models
    "Severity",
    "ResultFailureReason",
    "TargetType",
    "ProviderConfig",
    "ProviderResponse",
    "Prompt",
    "TestCase",
    "CompletedPrompt",
    "GradingResult",
    "EvaluateResult",
    "EvaluateStats",
]
