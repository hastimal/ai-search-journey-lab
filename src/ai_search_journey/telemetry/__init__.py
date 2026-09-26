"""OpenTelemetry in-memory observability module for AI Search Journey Lab."""

from ai_search_journey.telemetry.exporter import (
    MetricsRegistry,
    OtlpHttpJsonMetricsExporter,
    OtlpHttpJsonSpanExporter,
)
from ai_search_journey.telemetry.redaction import (
    is_sensitive_key,
    sanitize_attribute_value,
    sanitize_error_message,
    sanitize_string,
    sanitize_url,
)
from ai_search_journey.telemetry.store import TelemetrySpanView, TelemetryStore
from ai_search_journey.telemetry.tracer import get_tracer, init_telemetry, trace_span

__all__ = [
    "init_telemetry",
    "get_tracer",
    "trace_span",
    "TelemetryStore",
    "TelemetrySpanView",
    "MetricsRegistry",
    "OtlpHttpJsonMetricsExporter",
    "OtlpHttpJsonSpanExporter",
    "sanitize_string",
    "sanitize_url",
    "sanitize_error_message",
    "sanitize_attribute_value",
    "is_sensitive_key",
]
