"""Pytest fixtures for the Kitty test suite."""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from kitty.config.models import KittyConfig, RedTeamConfig
from kitty.core.provider import BaseProvider, ProviderResponse
from kitty.providers.registry import ProviderRegistry


class _MockOpenAIProvider(BaseProvider):
    """Mock OpenAI provider for testing."""

    provider_id: str = "openai:chat:gpt-4.1"

    async def call_api(self, prompt: str, **kwargs) -> ProviderResponse:
        return ProviderResponse(
            output="I'm sorry, I cannot assist with that request.",
            tokenUsage={"total": 42},
            cached=False,
        )

    async def id(self) -> str:
        return "openai:chat:gpt-4.1"


class _MockAnthropicProvider(BaseProvider):
    """Mock Anthropic provider for testing."""

    provider_id: str = "anthropic:chat:claude-3-opus-20240229"

    async def call_api(self, prompt: str, **kwargs) -> ProviderResponse:
        return ProviderResponse(
            output="I apologize, but I cannot provide that information.",
            tokenUsage={"total": 64},
            cached=False,
        )

    async def id(self) -> str:
        return "anthropic:chat:claude-3-opus-20240229"


@pytest_asyncio.fixture
async def mock_openai_provider() -> _MockOpenAIProvider:
    """Fixture that returns a mock OpenAI provider instance."""
    return _MockOpenAIProvider()


@pytest_asyncio.fixture
async def mock_anthropic_provider() -> _MockAnthropicProvider:
    """Fixture that returns a mock Anthropic provider instance."""
    return _MockAnthropicProvider()


@pytest_asyncio.fixture(params=["openai", "anthropic"])
async def any_mock_provider(
    request: pytest.FixtureRequest,
) -> _MockOpenAIProvider | _MockAnthropicProvider:
    """Fixture parameterized over openai and anthropic mock providers."""
    if request.param == "openai":
        return _MockOpenAIProvider()
    return _MockAnthropicProvider()


@pytest.fixture
def minimal_config_dict() -> dict:
    """Fixture returning a minimal valid Kitty configuration dictionary."""
    return {
        "targets": [
            {
                "id": "test-target",
                "provider": {"id": "openai:chat:gpt-4.1"},
            }
        ],
        "prompts": ["Hello {{name}}"],
        "tests": [
            {
                "vars": {"name": "World"},
                "assert": [{"type": "contains", "value": "Hello"}],
            }
        ],
    }


@pytest.fixture
def redteam_config_dict() -> dict:
    """Fixture returning a red-team configuration dictionary."""
    return {
        "targets": [
            {
                "id": "test-target",
                "provider": {"id": "openai:chat:gpt-4.1"},
            }
        ],
        "prompts": ["Hello {{name}}"],
        "tests": [
            {
                "vars": {"name": "World"},
                "assert": [{"type": "contains", "value": "Hello"}],
            }
        ],
        "redteam": {
            "purpose": "A helpful customer service assistant",
            "plugins": ["foundation:pii"],
            "strategies": ["jailbreak"],
            "numTests": 2,
        },
    }


@pytest.fixture
def kitty_config(minimal_config_dict: dict) -> KittyConfig:
    """Fixture returning a validated KittyConfig instance."""
    return KittyConfig.model_validate(minimal_config_dict)


@pytest_asyncio.fixture
async def registry() -> AsyncGenerator[ProviderRegistry, None]:
    """Fixture returning a ProviderRegistry with mock providers registered."""
    reg = ProviderRegistry()
    reg.create("openai:chat:gpt-4.1", _MockOpenAIProvider)
    reg.create("anthropic:chat:claude-3-opus-20240229", _MockAnthropicProvider)
    yield reg
    await reg.shutdown()


@pytest_asyncio.fixture(autouse=True)
async def tmp_db(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[None, None]:
    """Autouse fixture that sets up a temporary SQLite database for tests."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("KITTY_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    from kitty.db import init_db

    await init_db()
    yield
