"""Optional OpenTelemetry tracing for the stream-processor QA gate."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("argus.stream_processor.otel")

_tracer: Any = None


def init_tracer(service_name: str = "stream-processor") -> Any:
    """Configure OTLP HTTP exporter when OTEL_EXPORTER_OTLP_ENDPOINT is set."""
    global _tracer
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.info("otel_disabled", extra={"reason": "OTEL_EXPORTER_OTLP_ENDPOINT unset"})
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover
        logger.warning("otel_import_failed", extra={"error": str(exc)})
        return None

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "argus",
        }
    )
    provider = TracerProvider(resource=resource)
    # Prefer traces path; collector accepts http://otel-collector:4318
    base = endpoint.rstrip("/")
    traces_url = base if base.endswith("/v1/traces") else f"{base}/v1/traces"
    exporter = OTLPSpanExporter(endpoint=traces_url)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    logger.info("otel_enabled", extra={"endpoint": traces_url})
    return _tracer


def tracer() -> Any:
    return _tracer


def start_span(name: str, **attrs: Any) -> Any:
    """Return a context manager span, or a no-op context if tracing is off."""
    tr = _tracer
    if tr is None:
        from contextlib import nullcontext

        return nullcontext()
    span_cm = tr.start_as_current_span(name)
    # Attach attributes after enter via wrapper
    class _Span:
        def __enter__(self):
            self._span = span_cm.__enter__()
            for k, v in attrs.items():
                if v is not None:
                    self._span.set_attribute(k, v)
            return self._span

        def __exit__(self, *args):
            return span_cm.__exit__(*args)

    return _Span()
