"""Tests for the evaluation pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kitty.config.models import KittyConfig
from kitty.core.exceptions import ProviderError
from kitty.evaluate import evaluate
from kitty.types import EvaluateResult, ProviderResponse


class TestEvaluationPipeline:
    """Tests for the evaluation pipeline."""

    async def test_evaluate_with_mock(self, kitty_config: KittyConfig) -> None:
        """Running evaluate with a mock provider should return structured results."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="Hello World",
            tokenUsage={"total": 42},
            cached=False,
        )

        with patch(
            "kitty.evaluate.get_provider_for_target",
            return_value=mock_provider,
        ):
            results = await evaluate(kitty_config)

        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], EvaluateResult)
        assert results[0].success is True
        assert results[0].response is not None

    async def test_pipeline_handles_provider_error(
        self, kitty_config: KittyConfig
    ) -> None:
        """When a provider raises, the pipeline should produce a result with error."""
        mock_provider = AsyncMock()
        mock_provider.call_api.side_effect = ProviderError("API failure")

        with patch(
            "kitty.evaluate.get_provider_for_target",
            return_value=mock_provider,
        ):
            results = await evaluate(kitty_config)

        assert len(results) > 0
        assert results[0].success is False
        assert results[0].error is not None
        assert "API failure" in results[0].error

    async def test_build_test_cases_expands_vars(
        self, minimal_config_dict: dict
    ) -> None:
        """Test case generation should produce a cartesian product of variables."""
        from kitty.evaluate import build_test_cases

        config = KittyConfig.model_validate({
            **minimal_config_dict,
            "tests": [
                {
                    "vars": {"name": "World", "greeting": "Hello"},
                    "assert": [],
                },
                {
                    "vars": {"name": "Kitty", "greeting": "Hi"},
                    "assert": [],
                },
            ],
        })
        cases = build_test_cases(config)
        assert len(cases) == 2
        assert cases[0].vars["name"] == "World"
        assert cases[1].vars["name"] == "Kitty"

    async def test_render_prompt_with_jinja2(self) -> None:
        """Prompt templates with Jinja2 variables should be rendered correctly."""
        from kitty.evaluate import render_prompt

        rendered = render_prompt("Hello {{name}}!", {"name": "World"})
        assert rendered == "Hello World!"

        rendered = render_prompt(
            "{{greeting}}, {{name}}.",
            {"greeting": "Hi", "name": "Alice"},
        )
        assert rendered == "Hi, Alice."

    async def test_missing_var_renders_empty(self) -> None:
        """A missing variable in the template should render as empty string."""
        from kitty.evaluate import render_prompt

        rendered = render_prompt("Hello {{name}}!", {})
        assert rendered == "Hello !"

    async def test_multiple_targets_evaluated(
        self, minimal_config_dict: dict
    ) -> None:
        """Multiple targets should each produce a separate result row."""
        from kitty.evaluate import build_test_cases

        config = KittyConfig.model_validate({
            **minimal_config_dict,
            "targets": [
                {"id": "target-a", "provider": {"id": "openai:chat:gpt-4"}},
                {"id": "target-b", "provider": {"id": "anthropic:chat:claude-3"}},
            ],
        })
        cases = build_test_cases(config)
        # Each target x each test case
        assert len(cases) == 2

    async def test_empty_assert_list_ignored(self) -> None:
        """A test case with no assertions should not cause a crash."""
        from kitty.assertions import run_assertions
        from kitty.core.provider import ProviderResponse

        response = ProviderResponse(output="Some output")
        results = await run_assertions(response, [])
        assert results == []
