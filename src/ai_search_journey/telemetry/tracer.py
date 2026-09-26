"""Tracer initialization and context manager for in-memory OpenTelemetry tracing."""

from __future__ import annotations

import contextlib
import threading
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.trace import Span, StatusCode, Tracer

from ai_search_journey.config import settings
from ai_search_journey.telemetry.exporter import (
    MetricsRegistry,
    OtlpHttpJsonMetricsExporter,
    OtlpHttpJsonSpanExporter,
)
from ai_search_journey.telemetry.redaction import (
    is_sensitive_key,
    sanitize_attribute_value,
    sanitize_error_message,
)
from ai_search_journey.telemetry.store import TelemetryStore

_TRACER_NAME = "ai_search_journey"
_init_lock = threading.Lock()
_is_initialized = False


class InMemoryStoreSpanProcessor(SpanProcessor):
    """Custom SpanProcessor forwarding ended ReadableSpans directly into TelemetryStore."""

    def __init__(self, store: TelemetryStore) -> None:
        self._store = store

    def on_start(self, span: Span, parent_context: Any = None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        self._store.add_span(span)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def init_telemetry(max_runs: int = 50) -> TelemetryStore:
    """Initialize TracerProvider with in-memory processor and optional OTLP exporter."""
    global _is_initialized
    store = TelemetryStore.get_instance(max_runs=max_runs)
    with _init_lock:
        if not _is_initialized:
            provider = TracerProvider()
            processor = InMemoryStoreSpanProcessor(store)
            provider.add_span_processor(processor)

            # Optional OTLP Exporters (e.g. for local Docker Compose Grafana/Tempo stack)
            otlp_endpoint = settings.otel_exporter_otlp_endpoint
            if otlp_endpoint:
                try:
                    from opentelemetry.sdk.trace.export import BatchSpanProcessor

                    exporter = OtlpHttpJsonSpanExporter(
                        endpoint=otlp_endpoint,
                        service_name=settings.otel_service_name,
                    )
                    otlp_processor = BatchSpanProcessor(
                        exporter,
                        max_queue_size=2048,
                        schedule_delay_millis=500,
                        export_timeout_millis=3000,
                    )
                    provider.add_span_processor(otlp_processor)

                    # Also hook up OTLP metrics exporter
                    metrics_exporter = OtlpHttpJsonMetricsExporter(
                        endpoint=otlp_endpoint,
                        service_name=settings.otel_service_name,
                    )
                    MetricsRegistry.get_instance().set_exporter(metrics_exporter)
                except Exception:
                    pass  # Fail safely without breaking core application

            trace.set_tracer_provider(provider)
            _is_initialized = True
    return store


def get_tracer(name: str = _TRACER_NAME) -> Tracer:
    """Return an OpenTelemetry Tracer instance."""
    init_telemetry()
    return trace.get_tracer(name)


@contextlib.contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> Generator[Span, None, None]:
    """Context manager for tracing an execution boundary with sanitized attributes.

    Ensures proper status (OK / ERROR), exception recording without secret leaks,
    metric counters/durations updates, and automatic nesting when called within active parent spans.
    """
    tracer = get_tracer()
    safe_attrs: dict[str, Any] = {}
    if run_id:
        safe_attrs["journey.run_id"] = str(run_id)

    if attributes:
        for k, v in attributes.items():
            if not is_sensitive_key(str(k)):
                safe_attrs[str(k)] = sanitize_attribute_value(v)

    import time
    start_time = time.perf_counter()
    metrics = MetricsRegistry.get_instance()
    status_label = "ok"

    with tracer.start_as_current_span(name, attributes=safe_attrs) as span:
        try:
            yield span
            # Set OK status if not explicitly overridden
            if span.is_recording():
                span.set_status(StatusCode.OK)
        except Exception as exc:
            status_label = "error"
            if span.is_recording():
                sanitized_msg = sanitize_error_message(exc)
                span.set_status(StatusCode.ERROR, description=sanitized_msg)
                span.record_exception(
                    exc,
                    attributes={"exception.message": sanitized_msg},
                )
            raise
        finally:
            elapsed_s = max(0.0, time.perf_counter() - start_time)
            # Record workflow metrics safely
            stage_name = "custom"
            if name.startswith("journey."):
                stage_name = "v1"
            elif name.startswith("visibility."):
                stage_name = "v3"
            elif name.startswith("v4."):
                stage_name = "v4"

            metrics.inc_counter(
                "ai_search_journey_requests_total",
                value=1.0,
                labels={"stage": stage_name, "status": status_label},
            )
            metrics.record_duration(
                "ai_search_journey_duration_seconds",
                duration_seconds=elapsed_s,
                labels={"stage": stage_name, "status": status_label},
            )
            if status_label == "error":
                metrics.inc_counter(
                    "ai_search_journey_failures_total",
                    value=1.0,
                    labels={"stage": stage_name},
                )
            # Flush metrics to OTLP collector
            metrics.flush()
