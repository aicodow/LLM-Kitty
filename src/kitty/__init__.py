"""Kitty — LLM red-teaming framework.

Kitty provides tools for evaluating LLM-based systems against adversarial inputs,
configurable assertions, and automated red-team test generation.
"""

from __future__ import annotations

from typing import Any, Optional

from kitty.types import (
    EvaluateResult,
    EvaluateStats,
    GradingResult,
    KittyConfig,
    TestCase,
)

__version__ = "0.1.0"

# Re-exported names for the public API surface.  Users can write:
#     from kitty import evaluate, EvaluationPipeline, KittyConfig, ...
__all__ = [
    "evaluate",
    "EvaluationPipeline",
    "KittyConfig",
    "EvaluateResult",
    "EvaluateStats",
    "GradingResult",
    "TestCase",
    "__version__",
]


# ── Public API ───────────────────────────────────────────────────────────


def evaluate(config: KittyConfig) -> EvaluateResult:
    """Run a full evaluation from a configuration object.

    This is the top-level entry point for the framework.  It validates the
    configuration, instantiates providers, runs every test case against every
    target, and returns the aggregated result.

    Args:
        config: A fully resolved :class:`KittyConfig` instance.

    Returns:
        An :class:`EvaluateResult` containing per-test results, statistics,
        and (for red-team runs) vulnerability findings.

    Raises:
        EvalError: If the evaluation cannot complete.
    """
    pipeline = EvaluationPipeline(config)
    return pipeline.run()


class EvaluationPipeline:
    """Orchestrates a multi-step evaluation workflow.

    The pipeline handles provider setup, test execution, grading, and
    result aggregation.  Use :func:`evaluate` for the simplest path;
    instantiate this class directly when you need finer-grained control.
    """

    def __init__(self, config: KittyConfig) -> None:
        """Initialise the pipeline with a validated configuration.

        Args:
            config: A fully resolved :class:`KittyConfig` instance.
        """
        self.config = config
        self._result: Optional[EvaluateResult] = None

    def run(self) -> EvaluateResult:
        """Execute the evaluation and return the results.

        Returns:
            An :class:`EvaluateResult` with all test outcomes, stats, and metadata.
        """
        # TODO: Implement full provider dispatch, test execution, and grading.
        # This is a scaffold that returns an empty result for now.
        from datetime import datetime

        from kitty.types.eval import EvaluateResult, EvaluateStats

        stats = EvaluateStats()
        result = EvaluateResult(
            id=f"eval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            stats=stats,
        )
        self._result = result
        return result

    @property
    def result(self) -> Optional[EvaluateResult]:
        """The result of the last :meth:`run`, or ``None`` if not yet run."""
        return self._result
