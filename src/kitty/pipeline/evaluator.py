"""
Evaluation Pipeline — the heart of the Kitty testing framework.

This module orchestrates the five-rail LLM evaluation lifecycle:

    Input → Retrieval → Dialog → Execution → Output

It is a direct Python port of the Promptfoo evaluator, using ``asyncio``
for concurrency control, ``asyncio.Semaphore`` for rate limiting, and
Jinja2 for prompt template rendering.

Architecture
------------
The pipeline is event-driven and resilient: errors in a single test case
never abort the entire run.  Provider call timeouts, assertion failures,
and unexpected exceptions are all captured, classified, and aggregated
into the final ``EvaluateResult``.

Concurrency
-----------
``max_concurrency`` (from ``evaluateOptions``) controls the maximum number
of in-flight provider calls.  A ``Semaphore`` gates the provider call
section of :meth:`_execute_all`, while individual call timeouts use
``asyncio.wait_for`` with the per-call ``timeout_ms``.

Interrupt Handling
------------------
A ``SIGINT`` handler sets an internal flag so the current in-flight batch
can complete before the pipeline raises ``EvalInterruptedError``.  Provider
shutdown always runs in a ``try`` / ``finally`` block.
"""

from __future__ import annotations

import asyncio
import itertools
import signal
import time
from pathlib import Path
from typing import Any

import structlog
from jinja2 import BaseLoader, Environment

from kitty.exceptions import (
    EvalInterruptedError,
    EvalTimeoutError,
)
from kitty.types.config import KittyConfig
from kitty.types.eval import (
    EvaluateResult,
    EvaluateStats,
    GradingResult,
    Prompt,
    ProviderResponse,
    ResultFailureReason,
    TestCase,
)

logger = structlog.get_logger(__name__)


class EvaluationPipeline:
    """Orchestrates a full evaluation run across five rails.

    Parameters
    ----------
    config : KittyConfig
        Fully-validated configuration describing targets, prompts, tests,
        evaluate options, and optional red-team configuration.
    provider_registry : ProviderRegistry | None
        An optional pre-built provider registry (useful in tests or when
        sharing providers across multiple pipelines).  If ``None`` a fresh
        :class:`~kitty.providers.registry.ProviderRegistry` is created.
    """

    def __init__(
        self,
        config: KittyConfig,
        provider_registry: Any = None,
    ) -> None:
        self.config = config
        self._interrupted = False
        self._semaphore: asyncio.Semaphore | None = None

        # Lazy-import the provider registry to keep the top-level imports light.
        if provider_registry is not None:
            self._registry = provider_registry
        else:
            from kitty.providers.registry import ProviderRegistry

            self._registry = ProviderRegistry()

        # Register the SIGINT handler for graceful shutdown.
        self._original_sigint: Any = None

    # ── Public API ─────────────────────────────────────────────────────────

    async def run(self) -> EvaluateResult:
        """Execute the full five-rail pipeline.

        Returns
        -------
        EvaluateResult
            Aggregated results, statistics, and (for red-team runs)
            vulnerability findings.
        """
        started_at = time.monotonic()
        eval_opts = self.config.evaluate_options

        logger.info(
            "evaluation_started",
            targets=len(self.config.targets),
            max_concurrency=eval_opts.max_concurrency,
        )

        # ── 1. Input Rail: concurrency gate ────────────────────────────
        self._semaphore = asyncio.Semaphore(eval_opts.max_concurrency)
        self._install_signal_handler()

        try:
            # ── 2. Retrieval Rail: resolve providers ───────────────────
            providers = await self._resolve_providers()

            # ── 3. Dialog Rail: build & expand test cases ──────────────
            test_cases = self._build_test_cases()

            # Apply optional filtering (first-n / random sample).
            test_cases = self._apply_filters(test_cases)

            logger.info(
                "test_cases_prepared",
                count=len(test_cases),
                provider_count=len(providers),
            )

            # ── 4. Execution Rail: run all test cases ──────────────────
            results = await self._execute_all(test_cases, providers)

        except EvalInterruptedError:
            logger.warning("evaluation_interrupted")
            # Partial results may have been accumulated; re-raise after
            # the finally block shuts down providers.
            raise
        finally:
            # ── 5. Output Rail: aggregate & shutdown ───────────────────
            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            # `results` is defined in the try block; if an interrupt
            # happened before assignment, use an empty list.
            final_results: list[dict[str, Any]] = (
                locals().get("results", [])  # type: ignore[assignment]
            )
            stats = self._compute_stats(final_results, elapsed_ms)
            await self._shutdown_providers()
            self._restore_signal_handler()

        eval_id = (
            f"eval_{time.strftime('%Y%m%d_%H%M%S', time.gmtime(started_at))}"
        )
        logger.info(
            "evaluation_completed",
            eval_id=eval_id,
            total_tests=stats.total_tests,
            total_passed=stats.total_passed,
            total_failed=stats.total_failed,
            pass_rate=stats.pass_rate,
            duration_ms=stats.duration_ms,
        )

        return EvaluateResult(
            id=eval_id,
            results=final_results,
            stats=stats,
        )

    # ── Retrieval Rail ─────────────────────────────────────────────────────

    async def _resolve_providers(self) -> list[Any]:
        """Instantiate one provider per configured target.

        Each target's ``provider`` field can be either a plain string
        (provider ID) or a ``ProviderConfig`` object with ``id`` and
        ``config`` attributes.
        """
        from kitty.providers.base import BaseProvider
        from kitty.types.eval import ProviderConfig as ProviderConfigModel

        providers: list[BaseProvider] = []
        for target in self.config.targets:
            provider_spec = target.provider
            if isinstance(provider_spec, ProviderConfigModel):
                provider_id = provider_spec.id
                provider_config = provider_spec.config
            elif isinstance(provider_spec, str):
                provider_id = provider_spec
                provider_config = target.config
            else:
                provider_id = str(provider_spec)
                provider_config = target.config

            provider = await self._registry.create(provider_id, provider_config)
            providers.append(provider)
            logger.debug(
                "provider_resolved",
                target_id=target.id,
                provider_id=provider_id,
            )

        return providers

    # ── Dialog Rail: Test Case Construction ────────────────────────────────

    def _build_test_cases(self) -> list[TestCase]:
        """Expand ``prompts × tests × vars`` into a flat list of ``TestCase``.

        The expansion logic mirrors Promptfoo's test-case builder:

        * Tests that are bare strings become a single ``TestCase`` with no
          assertions and no variable interpolation.
        * Tests that are dicts may carry ``prompt``, ``vars``, ``assert`` /
          ``assertions``, and ``metadata`` keys.  When ``vars`` is present,
          the **Cartesian product** of all var values is computed so that
          every combination becomes its own ``TestCase``.
        * If a prompt string contains Jinja2 delimiters (``{{ }}`` or
          ``{% %}``) it is rendered through Jinja2 before being stored.
        * If a ``redteam`` section is configured, red-team plugins generate
          additional adversarial test cases.
        """
        cases: list[TestCase] = []

        # -- Phase 1: explicit tests from config -------------------------
        for test in self.config.tests:
            if isinstance(test, str):
                cases.append(
                    TestCase(
                        prompt=test,
                        assertions=[],
                        vars={},
                        metadata={},
                    )
                )
                continue

            if not isinstance(test, dict):
                logger.warning("skipping non-dict test entry", entry=test)
                continue

            raw_prompt = test.get("prompt", "")
            assertions_raw = test.get("assert", test.get("assertions", []))
            if isinstance(assertions_raw, str):
                assertions_raw = [assertions_raw]
            metadata = test.get("metadata", {})

            vars_data = test.get("vars", {})
            if isinstance(vars_data, dict) and vars_data:
                # Cartesian product of all var values
                keys = list(vars_data.keys())
                value_lists = list(vars_data.values())
                for combo in _cartesian_product(value_lists):
                    vars_dict = dict(zip(keys, combo))
                    rendered = self._render_prompt(raw_prompt, vars_dict)
                    cases.append(
                        TestCase(
                            prompt=rendered,
                            assertions=list(assertions_raw),
                            vars=vars_dict,
                            metadata=dict(metadata),
                        )
                    )
            else:
                rendered = self._render_prompt(raw_prompt, {})
                cases.append(
                    TestCase(
                        prompt=rendered,
                        assertions=list(assertions_raw),
                        vars={},
                        metadata=dict(metadata),
                    )
                )

        # -- Phase 2: red-team generated tests ---------------------------
        if self.config.redteam:
            redteam_cases = self._generate_redteam_tests()
            cases.extend(redteam_cases)
            logger.info(
                "redteam_tests_generated",
                count=len(redteam_cases),
                redteam_config=str(self.config.redteam.plugins),
            )

        return cases

    def _generate_redteam_tests(self) -> list[TestCase]:
        """Generate adversarial test cases via the red-team plugin engine.

        Uses the ``PluginRegistry`` and the configured ``redteam`` section
        to produce ``TestCase`` objects for each enabled plugin.
        """
        from kitty.redteam.plugins import PluginContext, PluginRegistry

        redteam = self.config.redteam
        if redteam is None:
            return []

        registry = PluginRegistry()
        plugin_ctx = PluginContext(
            target_purpose=redteam.purpose or "",
            language=redteam.language,
            provider_id="",
        )

        cases: list[TestCase] = []
        # Resolve each plugin reference to a plugin instance and generate tests.
        for plugin_ref in redteam.plugins:
            if isinstance(plugin_ref, str):
                plugin_id = plugin_ref
                num_tests: int | None = None
            else:
                plugin_id = plugin_ref.id
                num_tests = plugin_ref.num_tests

            plugin = registry.get(plugin_id)
            if plugin is None:
                logger.warning("redteam_plugin_not_found", plugin_id=plugin_id)
                continue

            # Run plugin test generation synchronously.  PluginEngine
            # calls are async in the general case; but for YAML-defined
            # plugins the default implementation is synchronous.
            plugin_cases = plugin.generate_tests(
                context=plugin_ctx,
                num_tests=num_tests or redteam.num_tests,
            )
            cases.extend(plugin_cases)
            logger.debug(
                "redteam_plugin_tests",
                plugin_id=plugin_id,
                count=len(plugin_cases),
            )

        return cases

    # ── Execution Rail ─────────────────────────────────────────────────────

    async def _execute_all(
        self,
        test_cases: list[TestCase],
        providers: list[Any],
    ) -> list[dict[str, Any]]:
        """Run every test case through every provider with concurrency gating.

        Each test-case × provider pair is wrapped in a per-call timeout.
        Provider call errors are captured and classified rather than
        aborting the batch.  The overall evaluation also has a
        ``max_eval_time_ms`` ceiling.
        """
        results: list[dict[str, Any]] = []

        async def _run_one(tc: TestCase, provider: Any) -> dict[str, Any]:
            # Check for interruption before acquiring the semaphore.
            if self._interrupted:
                raise EvalInterruptedError("Evaluation interrupted by user")
            async with self._semaphore:  # type: ignore[union-attr]
                return await self._execute_single(tc, provider)

        # Flatten test_cases × providers into a list of tasks.
        tasks = [
            _run_one(tc, provider)
            for tc in test_cases
            for provider in providers
        ]

        if not tasks:
            return results

        timeout_sec = self.config.evaluate_options.max_eval_time_ms / 1000.0

        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            self._interrupted = True
            raise EvalTimeoutError(
                f"Evaluation timed out after {timeout_sec:.0f}s"
            )

        for item in gathered:
            if isinstance(item, BaseException):
                results.append(
                    {
                        "error": str(item),
                        "grading_result": GradingResult(
                            passed=False,
                            score=0.0,
                            reason=str(item),
                        ),
                        "failure_reason": ResultFailureReason.PROVIDER_ERROR,
                    }
                )
            else:
                results.append(item)

        return results

    async def _execute_single(
        self,
        test_case: TestCase,
        provider: Any,
    ) -> dict[str, Any]:
        """Run one test case against one provider.

        1. Call the provider with the per-call ``timeout_ms``.
        2. Handle ``TimeoutError`` → ``GradingResult`` failed with
           ``ResultFailureReason.TIMEOUT``.
        3. Handle generic ``Exception`` → ``GradingResult`` failed with
           ``ResultFailureReason.PROVIDER_ERROR``.
        4. Run assertions via the assertion engine.
        5. Return a result dict matching the ``EvaluateResult.results``
           schema.

        Parameters
        ----------
        test_case : TestCase
            The test case to execute.
        provider : BaseProvider
            The resolved provider instance.

        Returns
        -------
        dict[str, Any]
            Result dict with keys: ``prompt``, ``provider_id``, ``vars``,
            ``metadata``, ``provider_response``, ``raw``, ``grading_result``,
            ``failure_reason``, and optionally ``error``.
        """
        call_timeout_sec = self.config.evaluate_options.timeout_ms / 1000.0

        result: dict[str, Any] = {
            "prompt": Prompt(raw=test_case.prompt),
            "provider_id": provider.id(),
            "vars": dict(test_case.vars),
            "metadata": dict(test_case.metadata),
        }

        # Apply an artificial delay between requests if configured.
        delay_ms = self.config.evaluate_options.delay
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        # -- Provider call with per-call timeout -------------------------
        try:
            response: ProviderResponse = await asyncio.wait_for(
                provider.call_api(
                    prompt=test_case.prompt,
                    context={"vars": test_case.vars},
                ),
                timeout=call_timeout_sec,
            )
            result["provider_response"] = response
            result["raw"] = response.output
        except asyncio.TimeoutError:
            result["error"] = "Provider call timed out"
            result["grading_result"] = GradingResult(
                passed=False,
                score=0.0,
                reason="Provider call timed out",
            )
            result["failure_reason"] = ResultFailureReason.TIMEOUT
            return result
        except Exception as exc:
            result["error"] = str(exc)
            result["grading_result"] = GradingResult(
                passed=False,
                score=0.0,
                reason=f"Provider error: {exc}",
            )
            result["failure_reason"] = ResultFailureReason.PROVIDER_ERROR
            return result

        # -- Run assertions against the response -------------------------
        grading = await self._run_assertions(
            prompt=test_case.prompt,
            response=response,
            assertions=test_case.assertions,
        )
        result["grading_result"] = grading

        if not grading.passed:
            result["failure_reason"] = ResultFailureReason.ASSERTION
        else:
            result["failure_reason"] = ResultFailureReason.NONE

        return result

    # ── Assertions ─────────────────────────────────────────────────────────

    async def _run_assertions(
        self,
        prompt: str,
        response: ProviderResponse,
        assertions: list[dict[str, Any]],
    ) -> GradingResult:
        """Run all assertions and aggregate results.

        Delegates to the assertion engine.  When no assertions are
        defined the test is considered passing with a perfect score.

        Parameters
        ----------
        prompt : str
            The prompt that was sent to the provider.
        response : ProviderResponse
            The provider's response.
        assertions : list[dict[str, Any]]
            List of assertion specification dicts.

        Returns
        -------
        GradingResult
            Aggregate grading result.
        """
        if not assertions:
            return GradingResult(
                passed=True,
                score=1.0,
                reason="No assertions defined",
            )

        from kitty.assertions.engine import run_assertions

        return await run_assertions(
            prompt=prompt,
            response=response,
            assertions=assertions,
            provider_registry=self._registry,
        )

    # ── Output Rail: Aggregation ───────────────────────────────────────────

    @staticmethod
    def _compute_stats(
        results: list[dict[str, Any]],
        elapsed_ms: int,
    ) -> EvaluateStats:
        """Aggregate per-test results into summary statistics.

        Parameters
        ----------
        results : list[dict[str, Any]]
            List of per-test result dicts.
        elapsed_ms : int
            Wall-clock duration in milliseconds.

        Returns
        -------
        EvaluateStats
            Aggregated statistics.
        """
        total = len(results)
        passed = 0
        errors = 0
        total_tokens = 0
        total_cost = 0.0

        for r in results:
            grading = r.get("grading_result")
            if grading is not None and grading.passed:
                passed += 1

            if r.get("error"):
                errors += 1

            provider_resp = r.get("provider_response")
            if provider_resp is not None and isinstance(
                provider_resp, ProviderResponse
            ):
                total_tokens += provider_resp.token_usage.get("total", 0)
                if provider_resp.cost is not None:
                    total_cost += provider_resp.cost

        failed = total - passed - errors

        return EvaluateStats(
            totalTests=total,
            totalPassed=passed,
            totalFailed=failed,
            totalErrors=errors,
            passRate=passed / total if total > 0 else 0.0,
            totalTokens=total_tokens,
            totalCost=total_cost,
            durationMs=elapsed_ms,
        )

    # ── Prompt Template Rendering ──────────────────────────────────────────

    @staticmethod
    def _render_prompt(template: str, vars_: dict[str, Any]) -> str:
        """Render a Jinja2 prompt template with the given variables.

        Only invokes the Jinja2 engine if the template contains ``{{ }}``
        or ``{% %}`` delimiters; plain strings are returned as-is.

        Parameters
        ----------
        template : str
            The prompt template, potentially with Jinja2 syntax.
        vars_ : dict[str, Any]
            Variables to bind during rendering.

        Returns
        -------
        str
            The fully rendered prompt string.
        """
        if "{{" not in template and "{%" not in template:
            return template

        env = Environment(loader=BaseLoader())
        rendered = env.from_string(template).render(**vars_)
        return rendered

    # ── Filtering ──────────────────────────────────────────────────────────

    def _apply_filters(self, test_cases: list[TestCase]) -> list[TestCase]:
        """Apply optional ``filterFirstN`` and ``filterSample`` filters.

        These match Promptfoo's filtering behaviour for limiting the
        number of test cases executed during a run.
        """
        opts = self.config.evaluate_options

        if opts.filter_first_n is not None and opts.filter_first_n > 0:
            test_cases = test_cases[: opts.filter_first_n]
            logger.debug("filter_first_n_applied", n=opts.filter_first_n)

        if opts.filter_sample is not None and opts.filter_sample > 0:
            import random

            rng = random.Random(opts.filter_sample_seed)
            sample_size = min(opts.filter_sample, len(test_cases))
            test_cases = rng.sample(test_cases, sample_size)
            logger.debug(
                "filter_sample_applied",
                n=sample_size,
                seed=opts.filter_sample_seed,
            )

        return test_cases

    # ── Signal Handling ────────────────────────────────────────────────────

    def _install_signal_handler(self) -> None:
        """Install a SIGINT handler that sets the interrupt flag.

        On Windows, ``signal.SIGINT`` is the only signal reliably
        supported; on Unix we also handle ``SIGTERM``.
        """
        try:

            def _handler(signum: int, _frame: Any) -> None:
                if self._interrupted:
                    logger.warning("interrupt_signal_ignored", signum=signum)
                    return
                logger.warning("interrupt_signal_received", signum=signum)
                self._interrupted = True

            self._original_sigint = signal.signal(signal.SIGINT, _handler)

            if hasattr(signal, "SIGTERM"):

                def _term_handler(signum: int, _frame: Any) -> None:
                    self._interrupted = True
                    logger.warning("signal_sigterm_received")

                signal.signal(signal.SIGTERM, _term_handler)  # type: ignore[attr-defined]
        except (ValueError, OSError):
            # Not running in the main thread — signals not available.
            pass

    def _restore_signal_handler(self) -> None:
        """Restore the original SIGINT handler if we replaced it."""
        if self._original_sigint is not None:
            try:
                signal.signal(signal.SIGINT, self._original_sigint)
            except (ValueError, OSError):
                pass
            self._original_sigint = None

    # ── Provider Shutdown ──────────────────────────────────────────────────

    async def _shutdown_providers(self) -> None:
        """Gracefully shut down all provider instances.

        Calls ``on_shutdown()`` on every cached provider and clears the
        instance cache.  Errors during shutdown are logged but do not
        propagate, ensuring the pipeline can always return partial results.
        """
        try:
            await self._registry.shutdown()
            logger.debug("providers_shutdown")
        except Exception as exc:
            logger.error("provider_shutdown_error", error=str(exc))


# ══════════════════════════════════════════════════════════════════════════
# Public Convenience Function
# ══════════════════════════════════════════════════════════════════════════


async def evaluate(  # type: ignore[no-redef]
    config: str | Path | KittyConfig | dict[str, Any],
) -> EvaluateResult:
    """Run a complete evaluation from a config path, dict, or object.

    This is the primary public API entry point for the framework::

        import asyncio
        from kitty.pipeline import evaluate

        result = asyncio.run(evaluate("kittyconfig.yaml"))

    Parameters
    ----------
    config : str | Path | KittyConfig | dict
        One of:

        - ``str`` / ``Path`` — path to a ``kittyconfig.yaml`` file.
        - ``dict`` — raw configuration dictionary (validated via Pydantic).
        - ``KittyConfig`` — pre-validated configuration object.

    Returns
    -------
    EvaluateResult
        Aggregated evaluation results, statistics, and vulnerability
        findings.

    Raises
    ------
    TypeError
        If *config* is an unsupported type.
    ConfigValidationError
        If the configuration fails Pydantic validation.
    ConfigNotFoundError
        If a file path does not exist.
    """
    if isinstance(config, (str, Path)):
        validated = KittyConfig.from_yaml(config)
    elif isinstance(config, dict):
        validated = KittyConfig.model_validate(config)
    elif isinstance(config, KittyConfig):
        validated = config
    else:
        raise TypeError(
            f"Unsupported config type: {type(config).__name__}. "
            f"Expected str, Path, dict, or KittyConfig."
        )

    pipeline = EvaluationPipeline(validated)
    return await pipeline.run()


# ── Internal Helpers ────────────────────────────────────────────────────────


def _cartesian_product(values: list[list[Any]]) -> list[tuple[Any, ...]]:
    """Compute the Cartesian product of the given value lists.

    Uses ``itertools.product`` internally.  Returns a list of tuples
    where each tuple has one element drawn from each input list.

    Parameters
    ----------
    values : list[list[Any]]
        A list of lists; each inner list provides possible values for one
        variable position.  May be empty (yields a single empty tuple).

    Returns
    -------
    list[tuple[Any, ...]]
        All combinations in product order.
    """
    if not values:
        return [()]
    return list(itertools.product(*values))
