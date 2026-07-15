"""Tests for the Kitty configuration models and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kitty.types.config import EvaluateOptions, KittyConfig


class TestKittyConfigValidation:
    """Tests for KittyConfig model validation."""

    def test_minimal_config_valid(self, minimal_config_dict: dict) -> None:
        """A minimal valid configuration should pass validation."""
        config = KittyConfig.model_validate(minimal_config_dict)
        assert len(config.targets) == 1
        assert config.targets[0].id == "test-target"
        assert len(config.prompts) == 1
        assert config.prompts[0] == "Hello {{name}}"
        assert len(config.tests or []) == 1

    def test_empty_config_raises_error(self) -> None:
        """An empty configuration should raise a validation error."""
        with pytest.raises(ValidationError):
            KittyConfig.model_validate({})

    def test_duplicate_target_ids_raises_error(self) -> None:
        """Configuration with duplicate target IDs should raise an error."""
        config_dict = {
            "targets": [
                {"id": "duplicate-id", "provider": {"id": "openai:chat:gpt-4"}},
                {"id": "duplicate-id", "provider": {"id": "anthropic:chat:claude-3"}},
            ],
            "prompts": ["Hello"],
            "tests": [{"vars": {"name": "World"}, "assert": []}],
        }
        with pytest.raises(ValidationError, match="duplicate"):
            KittyConfig.model_validate(config_dict)

    def test_missing_provider_field_raises_error(self) -> None:
        """A target without a provider field should raise a validation error."""
        config_dict = {
            "targets": [
                {
                    "id": "test-target",
                }
            ],
            "prompts": ["Hello"],
            "tests": [{"vars": {"name": "World"}, "assert": []}],
        }
        with pytest.raises(ValidationError):
            KittyConfig.model_validate(config_dict)

    def test_valid_provider_passes_validation(self) -> None:
        """A valid provider ID should pass validation."""
        config_dict = {
            "targets": [
                {
                    "id": "test-target",
                    "provider": {"id": "openai:chat:gpt-4"},
                }
            ],
            "prompts": ["Hello"],
            "tests": [{"vars": {"name": "World"}, "assert": []}],
        }
        config = KittyConfig.model_validate(config_dict)
        assert config.targets[0].provider.id == "openai:chat:gpt-4"

    def test_concurrency_out_of_range_raises_error(self) -> None:
        """Concurrency outside the valid range should raise an error."""
        config_dict = {
            "targets": [{"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}],
            "prompts": ["Hello"],
            "tests": [{"vars": {"name": "World"}, "assert": []}],
            "evaluateOptions": {"maxConcurrency": 0},
        }
        with pytest.raises(ValidationError):
            KittyConfig.model_validate(config_dict)

        config_dict["evaluateOptions"] = {"maxConcurrency": 101}
        with pytest.raises(ValidationError):
            KittyConfig.model_validate(config_dict)

    def test_at_least_one_source_required(self) -> None:
        """Config must have at least one of prompts, tests, or redteam."""
        config_dict = {
            "targets": [{"id": "test-target", "provider": {"id": "openai:chat:gpt-4"}}],
        }
        with pytest.raises(ValidationError, match=r"prompts|tests|redteam"):
            KittyConfig.model_validate(config_dict)

    def test_provider_config_accepted(self) -> None:
        """A provider config with an id should be accepted without env resolution."""
        config_dict = {
            "targets": [
                {
                    "id": "test-target",
                    "provider": {"id": "openai:chat:gpt-4"},
                }
            ],
            "prompts": ["Hello"],
            "tests": [{"vars": {"name": "World"}, "assert": []}],
        }
        config = KittyConfig.model_validate(config_dict)
        assert config.targets[0].provider.id == "openai:chat:gpt-4"


class TestEvaluateOptions:
    """Tests for EvaluateOptions model."""

    def test_default_values(self) -> None:
        """EvaluateOptions should have sensible defaults."""
        opts = EvaluateOptions()
        assert opts.max_concurrency == 4
        assert opts.cache is True

    def test_custom_values(self) -> None:
        """Custom values should be properly stored."""
        opts = EvaluateOptions(maxConcurrency=10, cache=False)
        assert opts.max_concurrency == 10
        assert opts.cache is False
