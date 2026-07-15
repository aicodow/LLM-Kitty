"""Integration tests for the evaluation pipeline with mock providers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kitty.exceptions import ProviderError
from kitty.pipeline.evaluator import EvaluationPipeline
from kitty.types import EvaluateResult, ProviderResponse
from kitty.types.config import KittyConfig


@pytest.mark.asyncio
class TestEvalPipelineIntegration:
    """Integration tests for the evaluation pipeline using mocked dependencies."""

    def _make_pipeline(self, config: KittyConfig) -> EvaluationPipeline:
        """Create an EvaluationPipeline with a mocked provider registry."""
        mock_provider = AsyncMock(spec_set=["call_api", "id", "on_shutdown"])
        mock_provider.id.return_value = (
            config.targets[0].provider.id
            if hasattr(config.targets[0].provider, "id")
            else str(config.targets[0].provider)
        )
        mock_provider.on_shutdown = AsyncMock()

        class MockRegistry:
            async def create(self, _provider_id: str, _config: dict | None = None):
                return mock_provider

            async def shutdown(self):
                await mock_provider.on_shutdown()

            def get(self, _provider_id: str):
                return mock_provider

        pipeline = EvaluationPipeline(config, provider_registry=MockRegistry())
        return pipeline, mock_provider

    async def test_eval_pipeline_openai(self) -> None:
        """The full evaluation pipeline with an OpenAI mock should produce stats."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="I'm sorry, I cannot assist with that request.",
            tokenUsage={"total": 42},
            cached=False,
        )
        mock_provider.id.return_value = "openai:chat:gpt-4"
        mock_provider.on_shutdown = AsyncMock()

        config = KittyConfig.model_validate(
            {
                "targets": [{"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}],
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
            }
        )

        class MockRegistry:
            async def create(self, _provider_id: str, _config: dict | None = None):
                mock_provider.id.return_value = _provider_id
                return mock_provider

            async def shutdown(self):
                await mock_provider.on_shutdown()

            def get(self, _provider_id: str):
                return mock_provider

        pipeline = EvaluationPipeline(config, provider_registry=MockRegistry())
        result = await pipeline.run()

        assert isinstance(result, EvaluateResult)
        assert len(result.results) == 2
        for item in result.results:
            assert item.get("grading_result") is not None

    async def test_eval_pipeline_anthropic(self) -> None:
        """The full evaluation pipeline with an Anthropic mock should produce stats."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="I apologize, but I cannot provide that information.",
            tokenUsage={"total": 64},
            cached=False,
        )
        mock_provider.id.return_value = "anthropic:chat:claude-3-opus-20240229"
        mock_provider.on_shutdown = AsyncMock()

        config = KittyConfig.model_validate(
            {
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
            }
        )

        class MockRegistry:
            async def create(self, _provider_id: str, _config: dict | None = None):
                mock_provider.id.return_value = _provider_id
                return mock_provider

            async def shutdown(self):
                await mock_provider.on_shutdown()

            def get(self, _provider_id: str):
                return mock_provider

        pipeline = EvaluationPipeline(config, provider_registry=MockRegistry())
        result = await pipeline.run()

        assert isinstance(result, EvaluateResult)
        assert len(result.results) == 1
        assert result.stats.total_tests == 1

    async def test_eval_pipeline_with_assertions(self) -> None:
        """The evaluation pipeline should execute assertions on responses."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="The capital of France is Paris.",
            tokenUsage={"total": 15},
            cached=False,
        )
        mock_provider.id.return_value = "openai:chat:gpt-4"
        mock_provider.on_shutdown = AsyncMock()

        config = KittyConfig.model_validate(
            {
                "targets": [{"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}],
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
            }
        )

        class MockRegistry:
            async def create(self, _provider_id: str, _config: dict | None = None):
                return mock_provider

            async def shutdown(self):
                await mock_provider.on_shutdown()

            def get(self, _provider_id: str):
                return mock_provider

        pipeline = EvaluationPipeline(config, provider_registry=MockRegistry())
        result = await pipeline.run()

        assert len(result.results) == 2
        # The mock always returns the same output, so Berlin assertion will fail
        for item in result.results:
            grading = item.get("grading_result")
            assert grading is not None

    async def test_eval_pipeline_provider_error_handling(self) -> None:
        """The pipeline should gracefully handle provider errors."""
        mock_provider = AsyncMock()
        mock_provider.call_api.side_effect = ProviderError("Connection timeout")
        mock_provider.id.return_value = "openai:chat:gpt-4"
        mock_provider.on_shutdown = AsyncMock()

        config = KittyConfig.model_validate(
            {
                "targets": [{"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}],
                "prompts": ["Hello"],
                "tests": [{"vars": {}, "assert": []}],
            }
        )

        class MockRegistry:
            async def create(self, _provider_id: str, _config: dict | None = None):
                return mock_provider

            async def shutdown(self):
                await mock_provider.on_shutdown()

            def get(self, _provider_id: str):
                return mock_provider

        pipeline = EvaluationPipeline(config, provider_registry=MockRegistry())
        result = await pipeline.run()

        assert len(result.results) == 1
        assert "Connection timeout" in (result.results[0].get("error", "") or "")

    async def test_eval_pipeline_with_cache_hit(self) -> None:
        """Cached responses should be returned without calling the provider again."""
        mock_provider = AsyncMock()
        mock_provider.call_api.return_value = ProviderResponse(
            output="Cached response",
            tokenUsage={"total": 10},
            cached=True,
        )
        mock_provider.id.return_value = "openai:chat:gpt-4"
        mock_provider.on_shutdown = AsyncMock()

        config = KittyConfig.model_validate(
            {
                "targets": [{"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}],
                "prompts": ["Hello"],
                "tests": [{"vars": {}, "assert": [{"type": "contains", "value": "Cached"}]}],
            }
        )

        class MockRegistry:
            async def create(self, _provider_id: str, _config: dict | None = None):
                return mock_provider

            async def shutdown(self):
                await mock_provider.on_shutdown()

            def get(self, _provider_id: str):
                return mock_provider

        pipeline = EvaluationPipeline(config, provider_registry=MockRegistry())
        result = await pipeline.run()

        assert len(result.results) == 1
        resp = result.results[0].get("provider_response")
        assert resp is not None
        assert resp.cached is True
