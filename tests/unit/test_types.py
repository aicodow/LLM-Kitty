"""Tests for Kitty type definitions and enumerations."""

from __future__ import annotations

import pytest

from kitty.types import (
    EvaluateResult,
    GradingResult,
    ProviderResponse,
    Severity,
    TestCase,
    TestResultFailureReason,
    TestTargetType,
)


class TestEnums:
    """Tests for enum types."""

    def test_severity_values(self) -> None:
        """Severity enum should have expected values."""
        assert Severity.INFO.value == "info"
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"

    def test_severity_ordering(self) -> None:
        """Severity levels should be comparable."""
        assert Severity.LOW > Severity.INFO
        assert Severity.MEDIUM > Severity.LOW
        assert Severity.HIGH > Severity.MEDIUM
        assert Severity.CRITICAL > Severity.HIGH

    def test_test_result_failure_reason_values(self) -> None:
        """TestResultFailureReason enum should have expected values."""
        reasons = TestResultFailureReason
        assert reasons.ASSERTION.value == "assertion"
        assert reasons.PROVIDER_ERROR.value == "provider_error"
        assert reasons.TIMEOUT.value == "timeout"
        assert reasons.TARGET_ERROR.value == "target_error"

    def test_test_target_type_values(self) -> None:
        """TestTargetType enum should have expected values."""
        assert TestTargetType.LLM.value == "llm"
        assert TestTargetType.TOOL.value == "tool"
        assert TestTargetType.AGENT.value == "agent"


class TestProviderResponse:
    """Tests for ProviderResponse data model."""

    def test_creation_with_minimal_fields(self) -> None:
        """A ProviderResponse should be creatable with just output."""
        response = ProviderResponse(output="Hello, world!")
        assert response.output == "Hello, world!"
        assert response.tokenUsage == {}
        assert response.cached is False

    def test_creation_with_all_fields(self) -> None:
        """A ProviderResponse should accept all fields."""
        response = ProviderResponse(
            output="Test output",
            tokenUsage={"total": 100, "prompt": 50, "completion": 50},
            cached=True,
            cost=0.002,
        )
        assert response.tokenUsage["total"] == 100
        assert response.cached is True
        assert response.cost == 0.002

    def test_serialization_to_dict(self) -> None:
        """ProviderResponse should serialize to a dictionary."""
        response = ProviderResponse(
            output="Test",
            tokenUsage={"total": 42},
            cached=False,
        )
        data = response.model_dump()
        assert data["output"] == "Test"
        assert data["tokenUsage"] == {"total": 42}
        assert data["cached"] is False


class TestGradingResult:
    """Tests for GradingResult data model."""

    def test_auto_pass_on_full_score(self) -> None:
        """A score of 1.0 should result in passed=True."""
        result = GradingResult(
            score=1.0,
            message="Perfect match",
            name="test-assertion",
            assertion_type="contains",
        )
        assert result.passed is True
        assert result.score == 1.0

    def test_custom_values(self) -> None:
        """GradingResult should accept and store custom values."""
        result = GradingResult(
            score=0.0,
            passed=False,
            message="No match found",
            name="fail-assertion",
            assertion_type="contains",
            details={"expected": "Hello", "actual": "Goodbye"},
        )
        assert result.passed is False
        assert result.details == {"expected": "Hello", "actual": "Goodbye"}

    def test_zero_score_implies_not_passed(self) -> None:
        """A score of 0.0 should default passed to False."""
        result = GradingResult(
            score=0.0,
            message="Failure",
            name="test",
            assertion_type="equals",
        )
        assert result.passed is False


class TestTestCase:
    """Tests for TestCase data model."""

    def test_default_fields(self) -> None:
        """TestCase should provide sensible defaults."""
        tc = TestCase(vars={"input": "Hello"})
        assert tc.vars == {"input": "Hello"}
        assert tc.assert_ == []
        assert tc.description is None
        assert tc.metadata == {}

    def test_with_assertions(self) -> None:
        """TestCase should store assertion configurations."""
        tc = TestCase(
            vars={"input": "Hello"},
            assert_=[
                {"type": "contains", "value": "Hello"},
                {"type": "not-contains", "value": "Goodbye"},
            ],
        )
        assert len(tc.assert_) == 2
        assert tc.assert_[0]["type"] == "contains"


class TestEvaluateResult:
    """Tests for EvaluateResult data model."""

    def test_structure(self) -> None:
        """EvaluateResult should contain all expected fields."""
        result = EvaluateResult(
            prompt="Hello {{name}}",
            rendered_prompt="Hello World",
            provider_id="openai:chat:gpt-4",
            target_id="test-target",
            response=ProviderResponse(output="Hello back!"),
            success=True,
            grading_result=None,
            error=None,
            latency_ms=150,
        )
        assert result.success is True
        assert result.provider_id == "openai:chat:gpt-4"
        assert result.response.output == "Hello back!"
        assert result.grading_result is None
        assert result.error is None
        assert result.latency_ms == 150

    def test_with_grading_result(self) -> None:
        """EvaluateResult should store grading results."""
        grading = GradingResult(
            score=1.0,
            passed=True,
            message="Match",
            name="contains-check",
            assertion_type="contains",
        )
        result = EvaluateResult(
            prompt="Hello",
            rendered_prompt="Hello World",
            provider_id="openai:chat:gpt-4",
            target_id="test-target",
            response=ProviderResponse(output="Hello back!"),
            success=True,
            grading_result=grading,
        )
        assert result.grading_result is not None
        assert result.grading_result.passed is True
        assert result.grading_result.score == 1.0

    def test_error_case(self) -> None:
        """EvaluateResult should store error information."""
        result = EvaluateResult(
            prompt="Hello",
            rendered_prompt="Hello World",
            provider_id="openai:chat:gpt-4",
            target_id="test-target",
            response=None,
            success=False,
            error="Provider returned 500 Internal Server Error",
        )
        assert result.success is False
        assert result.error is not None
        assert "500" in result.error
