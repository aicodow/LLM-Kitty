"""Tests for the assertion engine."""

from __future__ import annotations

import pytest

from kitty.assertions import run_assertions
from kitty.core.provider import ProviderResponse
from kitty.types import GradingResult


class TestAssertions:
    """Tests for the assertion evaluation engine."""

    async def test_contains_passes(self) -> None:
        """A 'contains' assertion should pass when the value is found."""
        response = ProviderResponse(output="Hello, World!")
        results = await run_assertions(
            response,
            [{"type": "contains", "value": "Hello"}],
        )
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].assertion_type == "contains"

    async def test_contains_fails(self) -> None:
        """A 'contains' assertion should fail when the value is not found."""
        response = ProviderResponse(output="Hello, World!")
        results = await run_assertions(
            response,
            [{"type": "contains", "value": "Goodbye"}],
        )
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].score == 0.0

    async def test_not_contains_passes(self) -> None:
        """A 'not-contains' assertion should pass when the value is absent."""
        response = ProviderResponse(output="Hello, World!")
        results = await run_assertions(
            response,
            [{"type": "not-contains", "value": "Goodbye"}],
        )
        assert len(results) == 1
        assert results[0].passed is True

    async def test_regex_matches(self) -> None:
        """A 'regex' assertion should pass when the pattern matches."""
        response = ProviderResponse(output="Call me at 555-123-4567")
        results = await run_assertions(
            response,
            [{"type": "regex", "value": r"\d{3}-\d{3}-\d{4}"}],
        )
        assert len(results) == 1
        assert results[0].passed is True

    async def test_equals_match(self) -> None:
        """An 'equals' assertion should pass on exact match."""
        response = ProviderResponse(output="Exact output")
        results = await run_assertions(
            response,
            [{"type": "equals", "value": "Exact output"}],
        )
        assert len(results) == 1
        assert results[0].passed is True

    async def test_equals_fail(self) -> None:
        """An 'equals' assertion should fail on mismatch."""
        response = ProviderResponse(output="Different output")
        results = await run_assertions(
            response,
            [{"type": "equals", "value": "Exact output"}],
        )
        assert len(results) == 1
        assert results[0].passed is False

    async def test_unknown_assertion_type_returns_error(self) -> None:
        """An unknown assertion type should return a failed result with an error."""
        response = ProviderResponse(output="Some output")
        results = await run_assertions(
            response,
            [{"type": "unknown-type", "value": "anything"}],
        )
        assert len(results) == 1
        assert results[0].passed is False
        assert "Unknown assertion type" in results[0].message

    async def test_assertion_handler_error_returns_failure(self) -> None:
        """A handler that raises an exception should return a failure gracefully."""
        response = ProviderResponse(output="Some output")
        results = await run_assertions(
            response,
            [{"type": "contains", "value": None}],  # type: ignore[arg-type]
        )
        assert len(results) == 1
        assert results[0].passed is False
