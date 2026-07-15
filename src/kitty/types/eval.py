"""Pydantic models for evaluation types in the Kitty red-teaming framework.

Defines the core data structures used throughout evaluation runs, including
test cases, provider responses, grading results, and aggregated statistics.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict, Field, model_validator


class BaseModel(_PydanticBaseModel):
    """Base model for all Kitty types with camelCase/JSON compatibility."""

    model_config = ConfigDict(populate_by_name=True)


# ── Enums ────────────────────────────────────────────────────────────────


class Severity(str, enum.Enum):
    """Severity levels for red-team findings and vulnerabilities."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResultFailureReason(str, enum.Enum):
    """Enumerates the possible reasons a test result may have failed."""

    NONE = "none"
    ASSERTION = "assertion"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


class TargetType(str, enum.Enum):
    """Categories of targets that can be evaluated."""

    BASE_MODEL = "base_model"
    RAG_SYSTEM = "rag_system"
    AI_AGENT = "ai_agent"


# ── Provider Models ──────────────────────────────────────────────────────


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider instance.

    Attributes:
        id: Unique identifier for this provider configuration.
        config: Arbitrary key-value configuration passed to the provider implementation.
        label: Optional human-readable label.
    """

    id: str
    config: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


class ProviderResponse(BaseModel):
    """The response returned by an LLM provider after a completion request.

    Attributes:
        output: The text output produced by the model.
        token_usage: Dictionary of token usage statistics (e.g. prompt, completion, total).
        cached: Whether the response was served from cache.
        cost: The monetary cost of this request, if calculable.
        metadata: Arbitrary metadata attached by the provider or framework.
    """

    output: str
    token_usage: dict[str, Any] = Field(default_factory=dict, alias="tokenUsage")
    cached: bool = False
    cost: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Prompt Models ────────────────────────────────────────────────────────


class Prompt(BaseModel):
    """A prompt template or literal sent to a provider.

    Attributes:
        raw: The raw prompt text, potentially containing template variables.
        display: Optional display-friendly version of the prompt.
        label: Optional short label for identification.
    """

    raw: str
    display: str | None = None
    label: str | None = None


class TestCase(BaseModel):
    """A single test case to run during evaluation.

    Attributes:
        id: Optional unique identifier for the test case.
        description: Optional human-readable description.
        prompt: The prompt string to send to the target.
        provider_id: Optional override of which provider to use.
        assertions: List of assertion specifications that define passing criteria.
        vars: Dictionary of template variables used to render the prompt.
        metadata: Arbitrary metadata attached to this test case.
    """

    id: str | None = None
    description: str | None = None
    prompt: str = Field(min_length=1)
    provider_id: str | None = Field(default=None, alias="providerId")
    assertions: list[dict[str, Any]] = Field(default_factory=list)
    vars: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletedPrompt(BaseModel):
    """The result of rendering and sending a single prompt to a provider.

    Attributes:
        prompt: The original Prompt that was sent.
        provider_response: The raw response from the provider, if successful.
        raw: The fully rendered prompt string that was sent.
        error: Error message if the prompt could not be completed.
    """

    prompt: Prompt
    provider_response: ProviderResponse | None = Field(default=None, alias="providerResponse")
    raw: str | None = None
    error: str | None = None


# ── Grading Models ───────────────────────────────────────────────────────


class GradingResult(BaseModel):
    """The result of grading a single test case output.

    Attributes:
        passed: Whether the test case passed grading.
        score: A float in [0, 1] representing the quality / pass level.
        reason: Free-text explanation of the grade.
        named_scores: Named sub-scores for multi-faceted grading.
        tokens_used: Token counts consumed during grading.
        assertion: The assertion dict that produced this result, if applicable.
        component_results: Sub-results for component / multi-step grading.
    """

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""
    named_scores: dict[str, float] = Field(default_factory=dict, alias="namedScores")
    tokens_used: dict[str, Any] = Field(default_factory=dict, alias="tokensUsed")
    assertion: dict[str, Any] | None = None
    component_results: list[Any] | None = Field(default=None, alias="componentResults")

    @model_validator(mode="after")
    def _enforce_passed_from_score(self) -> GradingResult:
        """If score is >= 1.0, automatically set passed to True."""
        if self.score >= 1.0:
            self.passed = True
        return self


# ── Statistics & Result Models ───────────────────────────────────────────


class EvaluateStats(BaseModel):
    """Aggregated statistics for a completed evaluation run.

    Attributes:
        total_tests: Total number of test cases executed.
        total_passed: Number of test cases that passed.
        total_failed: Number of test cases that failed.
        total_errors: Number of test cases that encountered errors.
        pass_rate: Fraction of tests that passed (0.0 - 1.0).
        total_tokens: Total tokens consumed across all provider calls.
        total_cost: Total monetary cost across all provider calls.
        duration_ms: Wall-clock duration of the evaluation run in milliseconds.
    """

    total_tests: int = Field(default=0, alias="totalTests")
    total_passed: int = Field(default=0, alias="totalPassed")
    total_failed: int = Field(default=0, alias="totalFailed")
    total_errors: int = Field(default=0, alias="totalErrors")
    pass_rate: float = Field(default=0.0, alias="passRate")
    total_tokens: int = Field(default=0, alias="totalTokens")
    total_cost: float = Field(default=0.0, alias="totalCost")
    duration_ms: int = Field(default=0, alias="durationMs")


class EvaluateResult(BaseModel):
    """Top-level result container for a complete evaluation run.

    Attributes:
        id: Unique identifier for this evaluation run.
        version: Schema version for the result payload.
        created_at: Timestamp when the evaluation was created.
        results: List of per-test-case result dictionaries.
        stats: Aggregated statistics for the run.
        vulnerabilities: List of vulnerability findings from red-team evaluation.
        risk_score: Optional aggregate risk score (0.0 - 1.0).
    """

    id: str
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow, alias="createdAt")
    results: list[dict[str, Any]] = Field(default_factory=list)
    stats: EvaluateStats = Field(default_factory=EvaluateStats)
    vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)
    risk_score: float | None = Field(default=None, alias="riskScore")


__all__ = [
    "CompletedPrompt",
    "EvaluateResult",
    "EvaluateStats",
    "GradingResult",
    "Prompt",
    "ProviderConfig",
    "ProviderResponse",
    "ResultFailureReason",
    "Severity",
    "TargetType",
    "TestCase",
]
