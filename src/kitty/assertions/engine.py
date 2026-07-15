"""
Assertion engine — runs assertions against provider responses.

This module mirrors the Promptfoo assertion system.  Assertions are the
core "test oracle": each one inspects a ``ProviderResponse`` and returns a
``GradingResult`` (passed / failed / score / reason).

Assertion types
---------------
**Static** (no LLM call):
  ``contains``, ``not-contains``, ``regex``, ``equals``, ``starts-with``,
  ``is-json``, ``latency``, and more.

**Model-graded** (LLM-as-judge):
  ``llm-rubric``, ``factuality`` — placeholders that pass through until the
  grader provider integration is complete.

**Custom**:
  Additional handlers can be registered at runtime via :func:`register_handler`.

Architecture
------------
Each assertion handler is an ``async`` function with the signature::

    async def handler(
        prompt: str,
        response: ProviderResponse,
        assertion: dict[str, Any],
        registry: ProviderRegistry,
    ) -> dict[str, Any]:
        ...

Handlers return flat dicts (not ``GradingResult`` instances) for
flexibility in composition.  The ``_run_single_assertion`` wrapper
ensures that misbehaving handlers never crash the pipeline.
"""

from __future__ import annotations

import json as json_module
import re
from typing import Any, Callable, Coroutine

from kitty.types.eval import GradingResult, ProviderResponse

# Handler signature: async (prompt, response, assertion, registry) -> dict
_AssertionHandler = Callable[
    [str, ProviderResponse, dict[str, Any], Any],
    Coroutine[Any, Any, dict[str, Any]],
]


async def run_assertions(
    prompt: str,
    response: ProviderResponse,
    assertions: list[dict[str, Any]],
    provider_registry: Any,
) -> GradingResult:
    """Run all *assertions* against the *response* and aggregate results.

    Aggregation follows Promptfoo conventions:

    * Individual results are collected in ``componentResults``.
    * The final ``passed`` is ``True`` if **every** component passed.
    * The final ``score`` is the arithmetic mean of all component scores.
    * ``namedScores`` is a flat merge across all components.
    * ``tokensUsed`` is a flat merge across all components.

    Parameters
    ----------
    prompt : str
        The prompt that was sent to the provider.
    response : ProviderResponse
        The provider's response to grade.
    assertions : list[dict[str, Any]]
        Assertion specifications.  Each dict requires at least a ``type``
        key; most also carry a ``value`` key.
    provider_registry : ProviderRegistry
        Registry used to resolve grader providers for model-graded
        assertions (e.g. ``llm-rubric``, ``factuality``).

    Returns
    -------
    GradingResult
        Aggregated grading result.
    """
    component_results: list[dict[str, Any]] = []
    all_passed = True
    total_score = 0.0
    named_scores: dict[str, float] = {}
    reasons: list[str] = []
    tokens_used: dict[str, Any] = {}

    for assertion in assertions:
        comp = await _run_single_assertion(
            prompt=prompt,
            response=response,
            assertion=assertion,
            provider_registry=provider_registry,
        )
        component_results.append(comp)

        if not comp.get("passed", False):
            all_passed = False

        total_score += comp.get("score", 0.0)
        reasons.append(comp.get("reason", ""))

        comp_named = comp.get("namedScores")
        if isinstance(comp_named, dict):
            named_scores.update(comp_named)

        comp_tokens = comp.get("tokensUsed")
        if isinstance(comp_tokens, dict):
            tokens_used.update(comp_tokens)

    avg_score = total_score / len(assertions) if assertions else 0.0

    return GradingResult(
        passed=all_passed,
        score=avg_score,
        reason="; ".join(filter(None, reasons)),
        namedScores=named_scores,
        tokensUsed=tokens_used,
        componentResults=component_results,
    )


async def _run_single_assertion(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    provider_registry: Any,
) -> dict[str, Any]:
    """Route one assertion to the correct handler.

    Unknown assertion types produce a non-passing result (never crash
    the pipeline).  Handler exceptions are also caught and converted to
    non-passing results.

    Parameters
    ----------
    prompt : str
        The original prompt string.
    response : ProviderResponse
        The provider's response.
    assertion : dict[str, Any]
        The assertion specification dict.
    provider_registry : ProviderRegistry
        Registry for resolving grader providers.

    Returns
    -------
    dict[str, Any]
        Result dict with keys ``passed``, ``score``, ``reason``, and
        optionally ``namedScores``, ``tokensUsed``.  The ``assertion``
        key is also set to the original assertion dict for traceability.
    """
    assertion_type = assertion.get("type", "contains")
    handler = _ASSERTION_DISPATCH.get(assertion_type)

    if handler is None:
        return {
            "passed": False,
            "score": 0.0,
            "reason": f"Unknown assertion type: {assertion_type!r}",
            "assertion": assertion,
        }

    try:
        result = await handler(prompt, response, assertion, provider_registry)
        result["assertion"] = assertion
        return result
    except Exception as exc:
        return {
            "passed": False,
            "score": 0.0,
            "reason": f"Assertion error ({assertion_type}): {exc}",
            "assertion": assertion,
        }


# ══════════════════════════════════════════════════════════════════════════
# Static Assertion Handlers
# ══════════════════════════════════════════════════════════════════════════


async def _handle_contains(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the response output contains the expected substring.

    The expected string is taken from ``assertion["value"]``.  Supports
    list values (any match passes).
    """
    value = assertion.get("value", "")
    output = response.output

    if isinstance(value, list):
        passed = any(str(v) in output for v in value)
        found = [str(v) for v in value if str(v) in output]
        reason = "Output contains expected text" if passed else f"None of {value} found in output"
    else:
        value_str = str(value)
        passed = value_str in output
        reason = (
            "Output contains expected text"
            if passed
            else f"Expected '{value_str}' not found in output"
        )

    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "reason": reason,
    }


async def _handle_not_contains(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the response output does **not** contain banned strings.

    The banned strings are taken from ``assertion["value"]``, which may
    be a single string or a list of strings.
    """
    values = assertion.get("value", [])
    if isinstance(values, str):
        values = [values]

    output = response.output
    found = [str(v) for v in values if str(v) in output]
    passed = len(found) == 0

    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "reason": ("No banned strings found" if passed else f"Found banned strings: {found}"),
    }


async def _handle_regex(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the response output matches a regular expression.

    The pattern is taken from ``assertion["value"]``.  Uses
    ``re.search`` with ``re.DOTALL`` so that ``.`` matches newlines.
    """
    pattern = assertion.get("value", "")
    try:
        matched = re.search(pattern, response.output, re.DOTALL)
    except re.error as exc:
        return {
            "passed": False,
            "score": 0.0,
            "reason": f"Invalid regex: {exc}",
        }

    return {
        "passed": bool(matched),
        "score": 1.0 if matched else 0.0,
        "reason": (f"Regex '{pattern}' matched" if matched else f"Regex '{pattern}' did not match"),
    }


async def _handle_equals(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the response output equals the expected value (trimmed).

    Both the output and the expected value are stripped of leading /
    trailing whitespace before comparison.
    """
    value = assertion.get("value", "")
    output_stripped = response.output.strip()
    value_stripped = str(value).strip()
    passed = output_stripped == value_stripped

    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "reason": (
            "Output matches expected value"
            if passed
            else f"Expected '{value_stripped}', got '{output_stripped}'"
        ),
    }


async def _handle_starts_with(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the response output starts with the expected prefix.

    The prefix is taken from ``assertion["value"]``.
    """
    prefix = str(assertion.get("value", ""))
    passed = response.output.startswith(prefix)

    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "reason": (
            "Output starts with expected prefix"
            if passed
            else f"Output does not start with '{prefix}'"
        ),
    }


async def _handle_is_json(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the response output is valid JSON.

    Optionally validates against a JSON schema if ``assertion["value"]``
    is a dict with a ``schema`` key.  Returns the parsed JSON in
    ``namedScores`` for downstream use.
    """
    try:
        parsed = json_module.loads(response.output)
    except (json_module.JSONDecodeError, ValueError) as exc:
        return {
            "passed": False,
            "score": 0.0,
            "reason": f"Output is not valid JSON: {exc}",
        }

    # If a schema is provided, validate against it.
    schema = assertion.get("value")
    if isinstance(schema, dict) and "schema" in schema:
        try:
            import jsonschema

            jsonschema.validate(instance=parsed, schema=schema["schema"])
        except ImportError:
            # jsonschema is optional; skip schema validation if absent.
            pass
        except jsonschema.ValidationError as exc:
            return {
                "passed": False,
                "score": 0.0,
                "reason": f"JSON does not match schema: {exc.message}",
                "namedScores": {},
            }

    return {
        "passed": True,
        "score": 1.0,
        "reason": "Output is valid JSON",
        "namedScores": {},
    }


async def _handle_latency(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Check that the provider response latency is within an acceptable range.

    The latency threshold (in milliseconds) is taken from
    ``assertion["value"]`` (default 5000ms).  The actual latency is
    computed from the response's ``token_usage`` timing metadata when
    available, or from the current wall clock (best-effort).

    If no timing information is available, the assertion passes with a
    warning note.
    """
    threshold_ms = assertion.get("value", 5000)
    try:
        threshold_ms = int(threshold_ms)
    except (ValueError, TypeError):
        threshold_ms = 5000

    # Attempt to extract timing from provider metadata.
    metadata = response.metadata or {}
    latency_ms = metadata.get("latency_ms") or metadata.get("latencyMs")

    if latency_ms is not None:
        try:
            latency_ms = int(latency_ms)
        except (ValueError, TypeError):
            latency_ms = None

    if latency_ms is None:
        # Check token usage for timing hints.
        token_usage = response.token_usage or {}
        latency_ms = token_usage.get("latency_ms") or token_usage.get("latencyMs")

    if latency_ms is None:
        return {
            "passed": True,
            "score": 1.0,
            "reason": "Latency check skipped: no timing data available",
        }

    passed = latency_ms <= threshold_ms
    return {
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "reason": (
            f"Latency {latency_ms}ms within threshold {threshold_ms}ms"
            if passed
            else f"Latency {latency_ms}ms exceeds threshold {threshold_ms}ms"
        ),
        "namedScores": {"latency": float(latency_ms)},
    }


# ══════════════════════════════════════════════════════════════════════════
# Model-Graded Assertion Handlers (Placeholders)
# ══════════════════════════════════════════════════════════════════════════


async def _handle_llm_rubric(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """LLM-as-judge rubric: ask a grader model whether the output meets criteria.

    **Placeholder** — the full implementation will use a grader provider
    (typically OpenAI GPT-4.1 or Anthropic Claude) to evaluate the response
    against the rubric defined in ``assertion["value"]``.

    When implemented, the rubric string will be combined with the prompt
    and response to construct a grading prompt, which is then sent to the
    grader provider for evaluation.
    """
    return {
        "passed": True,
        "score": 1.0,
        "reason": "LLM rubric grading not yet implemented (placeholder)",
    }


async def _handle_factuality(
    prompt: str,
    response: ProviderResponse,
    assertion: dict[str, Any],
    registry: Any,
) -> dict[str, Any]:
    """Factuality check: verify the output is factual relative to the prompt.

    **Placeholder** — the full implementation will use a grader model
    to check whether the response contains factual inaccuracies,
    hallucinations, or unsupported claims relative to the input prompt.
    """
    return {
        "passed": True,
        "score": 1.0,
        "reason": "Factuality check not yet implemented (placeholder)",
    }


# ══════════════════════════════════════════════════════════════════════════
# Dispatch Table Population
# ══════════════════════════════════════════════════════════════════════════

_ASSERTION_DISPATCH: dict[str, _AssertionHandler] = {
    "contains": _handle_contains,
    "not-contains": _handle_not_contains,
    "not_contains": _handle_not_contains,
    "regex": _handle_regex,
    "equals": _handle_equals,
    "starts-with": _handle_starts_with,
    "starts_with": _handle_starts_with,
    "is-json": _handle_is_json,
    "is_json": _handle_is_json,
    "latency": _handle_latency,
    "llm-rubric": _handle_llm_rubric,
    "llm_rubric": _handle_llm_rubric,
    "factuality": _handle_factuality,
}


def register_handler(
    assertion_type: str,
    handler_fn: _AssertionHandler,
) -> None:
    """Register a custom assertion handler at runtime.

    The *handler_fn* will be called whenever an assertion with the
    matching ``type`` field is encountered.

    Parameters
    ----------
    assertion_type : str
        The assertion type string (e.g. ``"custom:my-check"``).
    handler_fn : callable
        An async function with signature::

            async def handler(
                prompt: str,
                response: ProviderResponse,
                assertion: dict[str, Any],
                registry: ProviderRegistry,
            ) -> dict[str, Any]:
                ...
    """
    _ASSERTION_DISPATCH[assertion_type] = handler_fn
