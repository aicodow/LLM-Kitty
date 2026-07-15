"""Tests for the assertion engine."""

from __future__ import annotations

import pytest

from kitty.assertions import run_assertions
from kitty.types.eval import ProviderResponse
from kitty.types import GradingResult


class TestAssertions:
    """Tests for the assertion evaluation engine."""

    _PROMPT = "test prompt"

    async def test_contains_passes(self) -> None:
        """A 'contains' assertion should pass when the value is found."""
        response = ProviderResponse(output="Hello, World!")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "contains", "value": "Hello"}],
            provider_registry=None,
        )
        assert isinstance(result, GradingResult)
        assert result.passed is True

    async def test_contains_fails(self) -> None:
        """A 'contains' assertion should fail when the value is not found."""
        response = ProviderResponse(output="Hello, World!")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "contains", "value": "Goodbye"}],
            provider_registry=None,
        )
        assert result.passed is False

    async def test_not_contains_passes(self) -> None:
        """A 'not-contains' assertion should pass when the value is absent."""
        response = ProviderResponse(output="Hello, World!")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "not-contains", "value": "Goodbye"}],
            provider_registry=None,
        )
        assert result.passed is True

    async def test_regex_matches(self) -> None:
        """A 'regex' assertion should pass when the pattern matches."""
        response = ProviderResponse(output="Call me at 555-123-4567")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "regex", "value": r"\d{3}-\d{3}-\d{4}"}],
            provider_registry=None,
        )
        assert result.passed is True

    async def test_equals_match(self) -> None:
        """An 'equals' assertion should pass on exact match."""
        response = ProviderResponse(output="Exact output")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "equals", "value": "Exact output"}],
            provider_registry=None,
        )
        assert result.passed is True

    async def test_equals_fail(self) -> None:
        """An 'equals' assertion should fail on mismatch."""
        response = ProviderResponse(output="Different output")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "equals", "value": "Exact output"}],
            provider_registry=None,
        )
        assert result.passed is False

    async def test_unknown_assertion_type_returns_error(self) -> None:
        """An unknown assertion type should return a failed result with an error."""
        response = ProviderResponse(output="Some output")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "unknown-type", "value": "anything"}],
            provider_registry=None,
        )
        assert result.passed is False

    async def test_assertion_handler_error_returns_failure(self) -> None:
        """A handler that raises an exception should return a failure gracefully."""
        response = ProviderResponse(output="Some output")
        result = await run_assertions(
            prompt=self._PROMPT,
            response=response,
            assertions=[{"type": "contains", "value": None}],  # type: ignore[arg-type]
            provider_registry=None,
        )
        assert result.passed is False
