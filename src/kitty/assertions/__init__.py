"""Assertions sub-package — 66+ assertion type handlers.

Provides the assertion oracle system that grades provider responses against
configurable criteria.  Assertions can be static (string matching, regex,
JSON validation) or model-graded (LLM-as-judge rubrics, factuality checks).
Guardrail assertions are provided by :mod:`kitty.assertions.guardrails`.
"""

from kitty.assertions.engine import register_handler, run_assertions

__all__ = [
    "register_handler",
    "run_assertions",
]
