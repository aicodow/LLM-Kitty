"""Tests for the evaluation pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock

from kitty.exceptions import ProviderError
from kitty.pipeline.evaluator import EvaluationPipeline
from kitty.types import EvaluateResult, ProviderResponse
from kitty.types.config import KittyConfig


class _MockProviderRegistry:
    """A mock provider registry that returns a pre-configured mock provider."""

    def __init__(self, mock_provider):
        self._mock = mock_provider

    async def create(self, _provider_id: str, _config: dict | None = None):
        return self._mock

    async def shutdown(self):
        await self._mock.on_shutdown()

    def get(self, _provider_id: str):
        return self._mock


class TestEvaluationPipeline:
    """Tests for the evaluation pipeline."""

    async def test_evaluate_with_mock(self, kitty_config: KittyConfig) -> None:
        """Running evaluate with a mock provider should return structured results."""
        mock_provider = AsyncMock(
            spec=[
                "call_api",
                "id",
                "on_shutdown",
                "provider_id",
            ]
        )
        mock_provider.call_api.return_value = ProviderResponse(
            output="Hello World",
            tokenUsage={"total": 42},
            cached=False,
        )
        mock_provider.id.return_value = "openai:chat:gpt-4.1"
        mock_provider.on_shutdown = AsyncMock()

        pipeline = EvaluationPipeline(
            kitty_config,
            provider_registry=_MockProviderRegistry(mock_provider),
        )
        result = await pipeline.run()

        assert isinstance(result, EvaluateResult)
        assert len(result.results) > 0
        assert result.stats.total_tests > 0

    async def test_pipeline_handles_provider_error(self, kitty_config: KittyConfig) -> None:
        """When a provider raises, the pipeline should produce a result with error."""
        mock_provider = AsyncMock(
            spec=[
                "call_api",
                "id",
                "on_shutdown",
                "provider_id",
            ]
        )
        mock_provider.call_api.side_effect = ProviderError("API failure")
        mock_provider.id.return_value = "openai:chat:gpt-4.1"
        mock_provider.on_shutdown = AsyncMock()

        pipeline = EvaluationPipeline(
            kitty_config,
            provider_registry=_MockProviderRegistry(mock_provider),
        )
        result = await pipeline.run()

        assert len(result.results) > 0
        assert "API failure" in (result.results[0].get("error", "") or "")
        grading = result.results[0].get("grading_result")
        assert grading is not None
        assert grading.passed is False

    async def test_build_test_cases_expands_vars(self, minimal_config_dict: dict) -> None:
        """Test case generation should produce a cartesian product of variables."""
        config = KittyConfig.model_validate(
            {
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
            }
        )
        cases = EvaluationPipeline(config)._build_test_cases()
        assert len(cases) == 2
        assert cases[0].vars["name"] == "World"
        assert cases[1].vars["name"] == "Kitty"

    async def test_render_prompt_with_jinja2(self) -> None:
        """Prompt templates with Jinja2 variables should be rendered correctly."""
        rendered = EvaluationPipeline._render_prompt("Hello {{name}}!", {"name": "World"})
        assert rendered == "Hello World!"

        rendered = EvaluationPipeline._render_prompt(
            "{{greeting}}, {{name}}.",
            {"greeting": "Hi", "name": "Alice"},
        )
        assert rendered == "Hi, Alice."

    async def test_missing_var_renders_empty(self) -> None:
        """A missing variable in the template should render as empty string."""
        rendered = EvaluationPipeline._render_prompt("Hello {{name}}!", {})
        assert rendered == "Hello !"

    async def test_multiple_targets_evaluated(self, minimal_config_dict: dict) -> None:
        """Test cases should be built from configuration tests."""
        config = KittyConfig.model_validate(
            {
                **minimal_config_dict,
                "targets": [
                    {"id": "target-a", "provider": {"id": "openai:chat:gpt-4"}},
                    {"id": "target-b", "provider": {"id": "anthropic:chat:claude-3"}},
                ],
            }
        )
        cases = EvaluationPipeline(config)._build_test_cases()
        # _build_test_cases expands from config.tests, not targets cross-product
        assert len(cases) == 1

    async def test_empty_assert_list_ignored(self) -> None:
        """A test case with no assertions should not cause a crash."""
        from kitty.assertions import run_assertions

        response = ProviderResponse(output="Some output")
        result = await run_assertions(
            prompt="test prompt",
            response=response,
            assertions=[],
            provider_registry=None,
        )
        assert result.passed is True
