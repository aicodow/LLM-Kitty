"""Tracing package for Kitty framework.

OpenTelemetry integration for distributed tracing across LLM provider
calls, evaluations, and red-team runs.
"""

from .tracer import TracingConfig, end_span, init_tracing, start_span, traced

__all__ = [
    "TracingConfig",
    "end_span",
    "init_tracing",
    "start_span",
    "traced",
]
