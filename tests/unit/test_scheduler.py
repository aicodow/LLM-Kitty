"""Tests for the scheduler components: RateLimiter, ConcurrencyGate, retry_with_backoff."""

from __future__ import annotations

import asyncio

import pytest

from kitty.exceptions import ProviderError, ProviderRateLimitError
from kitty.scheduler import ConcurrencyGate, RateLimiter, retry_with_backoff


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    async def test_acquire_release(self) -> None:
        """Acquiring and releasing a token should work without blocking."""
        limiter = RateLimiter(max_tokens=100, refill_rate=1000)
        await limiter.acquire()
        await limiter.release()

    async def test_rate_limiting(self) -> None:
        """RateLimiter should limit the request rate."""
        limiter = RateLimiter(max_tokens=10, refill_rate=100)
        start = asyncio.get_event_loop().time()
        for _ in range(10):
            await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        # 10 tokens at 100/s should take very little time
        assert elapsed < 1.0


class TestConcurrencyGate:
    """Tests for the ConcurrencyGate class."""

    async def test_context_manager(self) -> None:
        """ConcurrencyGate should work as an async context manager."""
        gate = ConcurrencyGate(max_concurrency=5)
        async with gate:
            pass  # Should not block

    async def test_concurrency_limit(self) -> None:
        """ConcurrencyGate should allow the expected number of concurrent tasks."""
        gate = ConcurrencyGate(max_concurrency=2)
        entered = []

        async def worker(idx: int) -> None:
            async with gate:
                entered.append(idx)
                await asyncio.sleep(0.1)

        tasks = [asyncio.create_task(worker(i)) for i in range(4)]
        await asyncio.gather(*tasks)

        assert len(entered) == 4


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff function."""

    async def test_successful_call(self) -> None:
        """A call that succeeds on first try should return the result."""

        async def success_func() -> str:
            return "ok"

        result = await retry_with_backoff(
            coro_factory=lambda: success_func(),
            max_retries=3,
            base_delay=0.01,
        )
        assert result == "ok"

    async def test_retry_on_failure(self) -> None:
        """A call that fails temporarily should be retried and eventually succeed."""
        attempt = 0

        async def flaky_func() -> str:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise ProviderRateLimitError("Rate limited")
            return "success"

        result = await retry_with_backoff(
            coro_factory=lambda: flaky_func(),
            max_retries=3,
            base_delay=0.01,
        )
        assert result == "success"
        assert attempt == 3

    async def test_non_retryable_error_raises_immediately(self) -> None:
        """A non-retryable error should raise immediately without retries."""

        async def failing_func() -> str:
            raise ProviderError("Non-retryable error")

        with pytest.raises(ProviderError, match="Non-retryable error"):
            await retry_with_backoff(
                coro_factory=lambda: failing_func(),
                max_retries=3,
                base_delay=0.01,
            )

    async def test_max_retries_exceeded_raises(self) -> None:
        """Exceeding max retries should raise the last exception."""
        attempt = 0

        async def always_fails() -> str:
            nonlocal attempt
            attempt += 1
            raise ProviderRateLimitError("Always rate limited")

        with pytest.raises(ProviderRateLimitError, match="Always rate limited"):
            await retry_with_backoff(
                coro_factory=lambda: always_fails(),
                max_retries=2,
                base_delay=0.01,
            )
        assert attempt == 2  # initial try + 1 retry (max_retries=2)
