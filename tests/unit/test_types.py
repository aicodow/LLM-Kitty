"""Tests for Kitty type definitions and enumerations."""

from __future__ import annotations

from kitty.types import (
    EvaluateResult,
    EvaluateStats,
    GradingResult,
    ProviderResponse,
    ResultFailureReason,
    Severity,
    TargetType,
    TestCase,
)


class TestEnums:
    """Tests for enum types."""

    def test_severity_values(self) -> None:
        """Severity enum should have expected values."""
        assert Severity.LOW.value == "low"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"

    def test_result_failure_reason_values(self) -> None:
        """ResultFailureReason enum should have expected values."""
        reasons = ResultFailureReason
        assert reasons.ASSERTION.value == "assertion"
        assert reasons.PROVIDER_ERROR.value == "provider_error"
        assert reasons.TIMEOUT.value == "timeout"

    def test_target_type_values(self) -> None:
        """TargetType enum should have expected values."""
        assert TargetType.BASE_MODEL.value == "base_model"
        assert TargetType.RAG_SYSTEM.value == "rag_system"
        assert TargetType.AI_AGENT.value == "ai_agent"


class TestProviderResponse:
    """Tests for ProviderResponse data model."""

    def test_creation_with_minimal_fields(self) -> None:
        """A ProviderResponse should be creatable with just output."""
        response = ProviderResponse(output="Hello, world!")
        assert response.output == "Hello, world!"
        assert response.token_usage == {}
        assert response.cached is False

    def test_creation_with_all_fields(self) -> None:
        """A ProviderResponse should accept all fields."""
        response = ProviderResponse(
            output="Test output",
            tokenUsage={"total": 100, "prompt": 50, "completion": 50},
            cached=True,
            cost=0.002,
        )
        assert response.token_usage["total"] == 100
        assert response.cached is True
        assert response.cost == 0.002

    def test_serialization_to_dict(self) -> None:
        """ProviderResponse should serialize to a dictionary."""
        response = ProviderResponse(
            output="Test",
            tokenUsage={"total": 42},
            cached=False,
        )
        data = response.model_dump(by_alias=True)
        assert data["output"] == "Test"
        assert data["tokenUsage"] == {"total": 42}
        assert data["cached"] is False


class TestGradingResult:
    """Tests for GradingResult data model."""

    def test_auto_pass_on_full_score(self) -> None:
        """A score of 1.0 should result in passed=True."""
        result = GradingResult(
            passed=True,
            score=1.0,
            reason="Perfect match",
        )
        assert result.passed is True

    def test_custom_values(self) -> None:
        """GradingResult should accept and store custom values."""
        result = GradingResult(
            score=0.0,
            passed=False,
            reason="No match found",
        )
        assert result.passed is False

    def test_zero_score_defaults_false(self) -> None:
        """A score of 0.0 with passed=False explicitly."""
        result = GradingResult(
            score=0.0,
            passed=False,
            reason="Failure",
        )
        assert result.passed is False


class TestTestCase:
    """Tests for TestCase data model."""

    def test_default_fields(self) -> None:
        """TestCase should provide sensible defaults."""
        tc = TestCase(prompt="test prompt", vars={"input": "Hello"})
        assert tc.vars == {"input": "Hello"}
        assert tc.assertions == []
        assert tc.description is None
        assert tc.metadata == {}

    def test_with_assertions(self) -> None:
        """TestCase should store assertion configurations."""
        tc = TestCase(
            prompt="test prompt",
            vars={"input": "Hello"},
            assertions=[
                {"type": "contains", "value": "Hello"},
                {"type": "not-contains", "value": "Goodbye"},
            ],
        )
        assert len(tc.assertions) == 2
        assert tc.assertions[0]["type"] == "contains"


class TestEvaluateResult:
    """Tests for EvaluateResult data model."""

    def test_structure(self) -> None:
        """EvaluateResult should contain all expected fields."""
        stats = EvaluateStats(
            totalTests=10,
            totalPassed=7,
            totalFailed=2,
            totalErrors=1,
            passRate=0.7,
        )
        result = EvaluateResult(
            id="eval_test123",
            results=[
                {"prompt": "Hello", "provider_id": "openai:chat:gpt-4"},
            ],
            stats=stats,
        )
        assert result.id == "eval_test123"
        assert len(result.results) == 1
        assert result.stats.total_tests == 10
        assert result.stats.pass_rate == 0.7

    def test_defaults(self) -> None:
        """EvaluateResult should provide sensible defaults."""
        result = EvaluateResult(id="eval_default")
        assert result.results == []
        assert result.stats.total_tests == 0
        assert result.risk_score is None

    def test_vulnerabilities(self) -> None:
        """EvaluateResult should store vulnerability findings."""
        result = EvaluateResult(
            id="eval_redteam",
            vulnerabilities=[
                {"plugin": "foundation:pii", "severity": "high"},
            ],
        )
        assert len(result.vulnerabilities) == 1
        assert result.vulnerabilities[0]["plugin"] == "foundation:pii"
