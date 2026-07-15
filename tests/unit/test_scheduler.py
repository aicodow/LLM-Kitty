"""Tests for the scheduler components: RateLimiter, ConcurrencyGate, RetryWithBackoff."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from kitty.core.exceptions import ProviderError, RateLimitError
from kitty.scheduler import ConcurrencyGate, RateLimiter, RetryWithBackoff


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    async def test_acquire_release(self) -> None:
        """Acquiring and releasing a token should work without blocking."""
        limiter = RateLimiter(max_per_second=100)
        async with limiter:
            pass  # Should not block

    async def test_concurrency_limit(self) -> None:
        """RateLimiter should enforce the max_per_second limit."""
        limiter = RateLimiter(max_per_second=10)
        start = asyncio.get_event_loop().time()
        for _ in range(10):
            async with limiter:
                pass
        elapsed = asyncio.get_event_loop().time() - start
        # 10 tokens at 10/s should take roughly 1 second
        assert elapsed >= 0.8


class TestConcurrencyGate:
    """Tests for the ConcurrencyGate class."""

    async def test_context_manager(self) -> None:
        """ConcurrencyGate should work as an async context manager."""
        gate = ConcurrencyGate(max_concurrency=5)
        async with gate:
            assert gate.current == 1
        assert gate.current == 0

    async def test_concurrency_limit(self) -> None:
        """ConcurrencyGate should enforce the max_concurrency limit."""
        gate = ConcurrencyGate(max_concurrency=2)
        entered = []

        async def worker(idx: int) -> None:
            async with gate:
                entered.append(idx)
                await asyncio.sleep(0.1)

        tasks = [asyncio.create_task(worker(i)) for i in range(4)]
        await asyncio.gather(*tasks)

        # At most 2 workers should have been inside simultaneously
        assert len(entered) == 4
        assert gate.current == 0


class TestRetryWithBackoff:
    """Tests for the RetryWithBackoff class."""

    async def test_successful_call(self) -> None:
        """A call that succeeds on first try should return the result."""
        retrier = RetryWithBackoff(max_retries=3, base_delay=0.01)

        async def success_func() -> str:
            return "ok"

        result = await retrier.execute(success_func)
        assert result == "ok"

    async def test_retry_on_failure(self) -> None:
        """A call that fails temporarily should be retried and eventually succeed."""
        retrier = RetryWithBackoff(max_retries=3, base_delay=0.01)
        attempt = 0

        async def flaky_func() -> str:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise RateLimitError("Rate limited")
            return "success"

        result = await retrier.execute(flaky_func)
        assert result == "success"
        assert attempt == 3

    async def test_non_retryable_error_raises_immediately(self) -> None:
        """A non-retryable error should raise immediately without retries."""
        retrier = RetryWithBackoff(max_retries=3, base_delay=0.01)

        async def failing_func() -> str:
            raise ProviderError("Non-retryable error")

        with pytest.raises(ProviderError, match="Non-retryable error"):
            await retrier.execute(failing_func)

    async def test_max_retries_exceeded_raises(self) -> None:
        """Exceeding max retries should raise the last exception."""
        retrier = RetryWithBackoff(max_retries=2, base_delay=0.01)
        attempt = 0

        async def always_fails() -> str:
            nonlocal attempt
            attempt += 1
            raise RateLimitError("Always rate limited")

        with pytest.raises(RateLimitError, match="Always rate limited"):
            await retrier.execute(always_fails)
        assert attempt == 3  # initial try + 2 retries
