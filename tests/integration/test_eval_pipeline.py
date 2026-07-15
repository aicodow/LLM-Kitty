"""Integration tests for the evaluation pipeline with mock providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kitty.config.models import KittyConfig
from kitty.evaluate import evaluate
from kitty.types import EvaluateResult, ProviderResponse


@pytest.mark.asyncio
class TestEvalPipelineIntegration:
    """Integration tests for the evaluation pipeline using mocked dependencies."""

    async def test_eval_pipeline_openai(self) -> None:
        """The full evaluation pipeline with an OpenAI mock should produce stats."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="I'm sorry, I cannot assist with that request.",
            tokenUsage={"total": 42},
            cached=False,
        )

        config = KittyConfig.model_validate({
            "targets": [
                {"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}
            ],
            "prompts": ["Tell me about {{topic}}"],
            "tests": [
                {
                    "vars": {"topic": "hacking"},
                    "assert": [{"type": "contains", "value": "sorry"}],
                },
                {
                    "vars": {"topic": "cooking"},
                    "assert": [{"type": "contains", "value": "sorry"}],
                },
            ],
        })

        with patch("kitty.evaluate.get_provider_for_target", return_value=mock_provider):
            results = await evaluate(config)

        assert len(results) == 2
        for result in results:
            assert result.success is True
            assert result.provider_id == "openai:chat:gpt-4"
            assert result.response is not None
            assert result.response.tokenUsage["total"] == 42

    async def test_eval_pipeline_anthropic(self) -> None:
        """The full evaluation pipeline with an Anthropic mock should produce stats."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="I apologize, but I cannot provide that information.",
            tokenUsage={"total": 64},
            cached=False,
        )

        config = KittyConfig.model_validate({
            "targets": [
                {
                    "id": "test-target",
                    "provider": {"id": "anthropic:chat:claude-3-opus-20240229"},
                }
            ],
            "prompts": ["Tell me about {{topic}}"],
            "tests": [
                {
                    "vars": {"topic": "weapons"},
                    "assert": [{"type": "contains", "value": "apologize"}],
                }
            ],
        })

        with patch("kitty.evaluate.get_provider_for_target", return_value=mock_provider):
            results = await evaluate(config)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].response.tokenUsage["total"] == 64
        assert results[0].response.output == (
            "I apologize, but I cannot provide that information."
        )

    async def test_eval_pipeline_with_assertions(self) -> None:
        """The evaluation pipeline should execute assertions on responses."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="The capital of France is Paris.",
            tokenUsage={"total": 15},
            cached=False,
        )

        config = KittyConfig.model_validate({
            "targets": [
                {"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}
            ],
            "prompts": ["What is the capital of {{country}}?"],
            "tests": [
                {
                    "vars": {"country": "France"},
                    "assert": [
                        {"type": "contains", "value": "Paris"},
                        {"type": "not-contains", "value": "London"},
                    ],
                },
                {
                    "vars": {"country": "Germany"},
                    "assert": [
                        {"type": "contains", "value": "Berlin"},
                    ],
                },
            ],
        })

        with patch("kitty.evaluate.get_provider_for_target", return_value=mock_provider):
            results = await evaluate(config)

        assert len(results) == 2
        for result in results:
            assert result.success is True
            # The mock always returns the same output, so Berlin assertion will fail
            if result.test_case.vars["country"] == "France":
                assert result.grading_result is not None
                assert result.grading_result.passed is True
            else:
                # The Germany test expects Berlin in the output
                assert result.grading_result is not None
                assert result.grading_result.passed is False

    async def test_eval_pipeline_provider_error_handling(self) -> None:
        """The pipeline should gracefully handle provider errors."""
        mock_provider = AsyncMock()
        mock_provider.call_api.side_effect = Exception("Connection timeout")

        config = KittyConfig.model_validate({
            "targets": [
                {"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}
            ],
            "prompts": ["Hello"],
            "tests": [{"vars": {}, "assert": []}],
        })

        with patch("kitty.evaluate.get_provider_for_target", return_value=mock_provider):
            results = await evaluate(config)

        assert len(results) == 1
        assert results[0].success is False
        assert "Connection timeout" in (results[0].error or "")
        assert results[0].response is None

    async def test_eval_pipeline_with_cache_hit(self) -> None:
        """Cached responses should be returned without calling the provider again."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="Cached response",
            tokenUsage={"total": 10},
            cached=True,
        )

        config = KittyConfig.model_validate({
            "targets": [
                {"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}
            ],
            "prompts": ["Hello"],
            "tests": [
                {"vars": {}, "assert": [{"type": "contains", "value": "Cached"}]}
            ],
        })

        with patch("kitty.evaluate.get_provider_for_target", return_value=mock_provider):
            results = await evaluate(config)

        assert len(results) == 1
        assert results[0].response is not None
        assert results[0].response.cached is True
