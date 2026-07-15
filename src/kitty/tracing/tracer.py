"""OpenTelemetry tracing integration for the Kitty framework.

Provides a thin convenience layer over the OpenTelemetry SDK for
initialising a trace provider, creating spans, and marking sections
of code with the ``@traced`` context manager.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)


@dataclass
class TracingConfig:
    """Configuration for OpenTelemetry tracing.

    Attributes:
        enabled: Master switch.  When ``False`` all tracing operations
            are no-ops (default ``False``).
        exporter: The exporter type — ``"otlp"`` or ``"console"``
            (default ``"otlp"``).
        endpoint: OTLP gRPC or HTTP endpoint (e.g.
            ``"http://localhost:4317"``).
        service_name: Service name reported in spans (default
            ``"kitty"``).
        attributes: Global attributes attached to every span
            (default empty).
    """

    enabled: bool = False
    exporter: str = "otlp"
    endpoint: Optional[str] = None
    service_name: str = "kitty"
    attributes: Dict[str, Any] = field(default_factory=dict)


_tracer = None  # module-level tracer singleton
_provider = None  # module-level TracerProvider singleton


def init_tracing(config: TracingConfig) -> None:
    """Initialise the global OpenTelemetry trace provider.

    Call this once at application startup.  When *config* is not enabled
    the function returns immediately.

    Args:
        config: A :class:`TracingConfig` instance describing the desired
            trace export behaviour.

    Raises:
        ImportError: When the required OpenTelemetry packages are not
            installed and the config requires them (enabled exporters).
    """
    global _tracer, _provider  # noqa: PLW0603

    if not config.enabled:
        logger.debug("Tracing is disabled, skipping initialisation")
        return

    try:
        from opentelemetry import trace  # type: ignore[import-untyped]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-untyped]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-untyped]
    except ImportError as exc:
        msg = (
            "OpenTelemetry packages are not installed. "
            "Install them with: pip install opentelemetry-api opentelemetry-sdk"
        )
        raise ImportError(msg) from exc

    resource = Resource.create(
        attributes={
            "service.name": config.service_name,
            **config.attributes,
        }
    )

    _provider = TracerProvider(resource=resource)

    if config.exporter == "otlp" and config.endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-untyped] # noqa: E501
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-untyped] # noqa: E501
        except ImportError as exc:
            msg = (
                "OTLP exporter requested but opentelemetry-exporter-otlp-proto-grpc "
                "is not installed."
            )
            raise ImportError(msg) from exc

        otlp_exporter = OTLPSpanExporter(endpoint=config.endpoint)
        _provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info("Tracing initialised: OTLP exporter -> %s", config.endpoint)

    elif config.exporter == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor  # type: ignore[import-untyped] # noqa: E501

        _provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info("Tracing initialised: console exporter")

    else:
        logger.warning(
            "Unknown exporter %r or missing endpoint; spans will not be exported",
            config.exporter,
        )

    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer(config.service_name)


def start_span(
    name: str, attributes: Optional[Dict[str, Any]] = None
) -> Any:
    """Start and return a new span.

    When tracing is not initialised a no-op span is returned.

    Args:
        name: The span name.
        attributes: Optional key-value pairs attached to the span.

    Returns:
        An OpenTelemetry ``Span`` object.
    """
    tracer = _get_tracer()
    span = tracer.start_span(name)
    if attributes:
        span.set_attributes(attributes)
    return span


def end_span(span: Any) -> None:
    """End a previously started span.

    Args:
        span: The span to close.
    """
    try:
        span.end()
    except Exception as exc:
        logger.debug("Error ending span: %s", exc)


@contextmanager
def traced(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Context manager that wraps a block in a single span.

    Usage::

        with traced("llm_call", provider="openai", model="gpt-4"):
            response = await client.chat(...)

    Args:
        name: The span name.
        **attributes: Key-value pairs attached to the span.

    Yields:
        The active span.
    """
    span = start_span(name, attributes)
    try:
        yield span
    except Exception:
        span.record_exception()
        span.set_status(
            _get_status_error()
        )
        raise
    finally:
        end_span(span)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _get_tracer() -> Any:
    """Return the module-level tracer or a no-op tracer."""
    if _tracer is not None:
        return _tracer
    try:
        from opentelemetry import trace  # type: ignore[import-untyped]

        return trace.get_tracer("kitty")
    except ImportError:
        return _NoOpTracer()


def _get_status_error() -> Any:
    """Return the OpenTelemetry StatusCode.ERROR constant."""
    try:
        from opentelemetry.trace.status import StatusCode  # type: ignore[import-untyped]

        return StatusCode.ERROR
    except ImportError:
        return None


# ------------------------------------------------------------------
# No-op tracer for when OpenTelemetry is not installed
# ------------------------------------------------------------------


class _NoOpSpan:
    """Span that does nothing, used when OpenTelemetry is unavailable."""

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exception: BaseException | None = None) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """Tracer that returns no-op spans."""

    def start_span(self, name: str, *args: Any, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()
