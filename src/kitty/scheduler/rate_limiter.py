"""Rate-limiting, concurrency gating, and retry utilities for LLM providers.

Provides a token-bucket rate limiter, an async context manager for
capping concurrency, and an exponential-backoff retry decorator that
handles transient API errors.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Token-bucket rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket rate limiter for controlling request rates.

    The bucket starts full and is refilled at *refill_rate* tokens per
    second, up to *max_tokens*.  Callers ``acquire`` a token before
    sending a request and ``release`` it when done.

    Attributes:
        max_tokens (int): Maximum number of tokens the bucket can hold.
        refill_rate (float): Tokens added per second.
    """

    def __init__(self, max_tokens: int = 4, refill_rate: float = 2.0) -> None:
        """Initialise the token bucket.

        Args:
            max_tokens: Burst capacity (default 4).
            refill_rate: Token replenishment rate per second (default 2.0).
        """
        self.max_tokens: int = max_tokens
        self.refill_rate: float = refill_rate
        self._tokens: float = float(max_tokens)
        self._last_refill: float = time.monotonic()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, blocking until one is available.

        This method is safe to call from multiple concurrent tasks.
        """
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # How long until at least one token is available?
                wait_time = (1.0 - self._tokens) / self.refill_rate
            await asyncio.sleep(wait_time)

    async def release(self) -> None:
        """Return a token to the bucket, capping at ``max_tokens``."""
        async with self._lock:
            self._refill()
            self._tokens = min(self._tokens + 1.0, float(self.max_tokens))

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        self._tokens = min(
            self._tokens + elapsed * self.refill_rate,
            float(self.max_tokens),
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"max_tokens={self.max_tokens}, "
            f"refill_rate={self.refill_rate}, "
            f"current={self._tokens:.1f})"
        )


# ---------------------------------------------------------------------------
# Concurrency gate
# ---------------------------------------------------------------------------


class ConcurrencyGate:
    """Async context manager that limits the number of concurrent operations.

    Wraps an :class:`asyncio.Semaphore` so it can be used as a context
    manager or decorated around a coroutine function.

    Usage::

        gate = ConcurrencyGate(max_concurrency=5)

        async with gate:
            await send_request(...)
    """

    def __init__(self, max_concurrency: int) -> None:
        """Initialise the gate.

        Args:
            max_concurrency: Maximum number of tasks allowed inside the
                critical section.  Must be >= 1.
        """
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> None:
        """Acquire the semaphore, blocking if at capacity."""
        await self._semaphore.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Release the semaphore."""
        self._semaphore.release()


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------


def _is_retryable(exc: BaseException) -> bool:
    """Determine whether *exc* represents a transient / retryable error.

    Checks the exception's class name and string representation for
    common transient-failure indicators such as HTTP 429 (rate limit),
    5xx status codes, connection resets, and timeouts.

    Args:
        exc: The exception to inspect.

    Returns:
        ``True`` if the error is likely transient.
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()

    indicators = [
        "429",
        "rate limit",
        "503",
        "502",
        "504",
        "connection",
        "timeout",
        "reset",
    ]
    return any(indicator in name or indicator in msg for indicator in indicators)


async def retry_with_backoff(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> T:
    """Execute a coroutine factory with exponential-backoff retry logic.

    Arguments are evaluated once per attempt via *coro_factory*.  On a
    transient failure the coroutine is retried after an exponentially
    increasing delay.  Non-retryable errors are raised immediately.

    Args:
        coro_factory: A zero-argument callable that returns an awaitable.
        max_retries: Maximum number of attempts (default 3).
        base_delay: Initial delay in seconds before the first retry
            (default 1.0).
        max_delay: Cap for the delay in seconds (default 30.0).
        jitter: When ``True`` (default), a random jitter of ±25% is
            added to each delay.

    Returns:
        The return value of the successful coroutine invocation.

    Raises:
        The last exception encountered if all retries are exhausted.
    """

    for attempt in range(1, max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            if not _is_retryable(exc):
                raise

            if attempt == max_retries:
                logger.error(
                    "All %d retries exhausted for %s: %s",
                    max_retries,
                    getattr(coro_factory, "__name__", coro_factory),
                    exc,
                )
                raise

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if jitter:
                jitter_amount = delay * 0.25
                delay = delay + random.uniform(-jitter_amount, jitter_amount)  # nosec B311
                delay = max(0.0, delay)

            logger.info(
                "Retry %d/%d for %s after %.2fs (error: %s)",
                attempt,
                max_retries,
                getattr(coro_factory, "__name__", coro_factory),
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    # Should not be reached, but keeps the type-checker happy.
    raise AssertionError("Unreachable")  # pragma: no cover
