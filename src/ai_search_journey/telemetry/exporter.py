"""OTLP JSON Exporter and Metric Collection for OpenTelemetry."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

from ai_search_journey.telemetry.redaction import (
    is_sensitive_key,
    sanitize_attribute_value,
    sanitize_error_message,
)

logger = logging.getLogger(__name__)


def _sanitize_metric_label(val: Any) -> str:
    """Ensure metric label values are safe strings without sensitive content."""
    if val is None:
        return "none"
    s = str(val).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return "url"
    if is_sensitive_key(s):
        return "[REDACTED]"
    return s[:100]


def _format_otlp_attribute_value(val: Any) -> dict[str, Any]:
    """Convert a Python value into an OTLP AnyValue object."""
    if isinstance(val, bool):
        return {"boolValue": val}
    if isinstance(val, int):
        return {"intValue": str(val)}
    if isinstance(val, float):
        return {"doubleValue": val}
    if isinstance(val, (list, tuple)):
        return {
            "arrayValue": {
                "values": [_format_otlp_attribute_value(item) for item in val]
            }
        }
    return {"stringValue": str(val)}


def _span_to_otlp_dict(
    span: ReadableSpan,
    service_name: str = "ai_search_journey",
) -> dict[str, Any]:
    """Convert an OpenTelemetry ReadableSpan to an OTLP HTTP/JSON resourceSpans payload."""
    trace_id_hex = f"{span.context.trace_id:032x}"
    span_id_hex = f"{span.context.span_id:016x}"
    parent_id_hex = f"{span.parent.span_id:016x}" if span.parent else ""

    start_nano = str(span.start_time or 0)
    end_nano = str(span.end_time or span.start_time or 0)

    # Convert status
    status_code = span.status.status_code
    if status_code == StatusCode.OK:
        otlp_status_code = 1
    elif status_code == StatusCode.ERROR:
        otlp_status_code = 2
    else:
        otlp_status_code = 0

    status_desc = span.status.description or ""
    if status_desc:
        status_desc = sanitize_error_message(status_desc)

    # Sanitize attributes
    attributes_list: list[dict[str, Any]] = []
    if span.attributes:
        for k, v in span.attributes.items():
            if is_sensitive_key(str(k)):
                continue
            clean_v = sanitize_attribute_value(v)
            attributes_list.append({
                "key": str(k),
                "value": _format_otlp_attribute_value(clean_v),
            })

    # Events / Exceptions
    events_list: list[dict[str, Any]] = []
    if span.events:
        for ev in span.events:
            ev_attrs: list[dict[str, Any]] = []
            if ev.attributes:
                for ek, ev_val in ev.attributes.items():
                    if is_sensitive_key(str(ek)):
                        continue
                    clean_ev_val = sanitize_attribute_value(ev_val)
                    ev_attrs.append({
                        "key": str(ek),
                        "value": _format_otlp_attribute_value(clean_ev_val),
                    })
            events_list.append({
                "timeUnixNano": str(ev.timestamp),
                "name": ev.name,
                "attributes": ev_attrs,
            })

    span_dict: dict[str, Any] = {
        "traceId": trace_id_hex,
        "spanId": span_id_hex,
        "name": span.name,
        "kind": span.kind.value if hasattr(span.kind, "value") else 1,
        "startTimeUnixNano": start_nano,
        "endTimeUnixNano": end_nano,
        "attributes": attributes_list,
        "events": events_list,
        "status": {
            "code": otlp_status_code,
            "message": status_desc,
        },
    }
    if parent_id_hex:
        span_dict["parentSpanId"] = parent_id_hex

    return {
        "resource": {
            "attributes": [
                {
                    "key": "service.name",
                    "value": {"stringValue": service_name},
                }
            ]
        },
        "scopeSpans": [
            {
                "scope": {
                    "name": "ai_search_journey",
                    "version": "2.0.0",
                },
                "spans": [span_dict],
            }
        ],
    }


class OtlpHttpJsonSpanExporter(SpanExporter):
    """Standard HTTP/JSON SpanExporter sending OTLP protobuf-mapped JSON to a collector."""

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: float = 3.0,
        service_name: str = "ai_search_journey",
    ) -> None:
        clean_ep = endpoint.rstrip("/")
        if not clean_ep.endswith("/v1/traces"):
            self._endpoint = f"{clean_ep}/v1/traces"
        else:
            self._endpoint = clean_ep
        self._timeout = timeout_seconds
        self._service_name = service_name
        self._is_shutdown = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._is_shutdown or not spans:
            return SpanExportResult.SUCCESS

        try:
            resource_spans = [
                _span_to_otlp_dict(s, service_name=self._service_name)
                for s in spans
            ]
            payload = {"resourceSpans": resource_spans}
            data = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                self._endpoint,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ai-search-journey-lab-otlp-exporter/2.0.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if 200 <= resp.status < 300:
                    return SpanExportResult.SUCCESS
                return SpanExportResult.FAILURE
        except Exception as exc:
            logger.debug("OTLP export to %s failed safely: %s", self._endpoint, exc)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._is_shutdown = True

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class OtlpHttpJsonMetricsExporter:
    """Standard HTTP/JSON Metrics Exporter sending OTLP JSON to /v1/metrics."""

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: float = 3.0,
        service_name: str = "ai_search_journey",
    ) -> None:
        clean_ep = endpoint.rstrip("/")
        if not clean_ep.endswith("/v1/metrics"):
            self._endpoint = f"{clean_ep}/v1/metrics"
        else:
            self._endpoint = clean_ep
        self._timeout = timeout_seconds
        self._service_name = service_name

    def export_metrics(self, registry: MetricsRegistry) -> bool:
        """Serialize registered metrics to OTLP JSON and send to the collector."""
        try:
            import time

            now_nano = str(int(time.time() * 1e9))
            metrics_payloads: list[dict[str, Any]] = []

            counters: dict[str, dict[tuple[tuple[str, str], ...], float]]
            durations: dict[str, dict[tuple[tuple[str, str], ...], list[float]]]
            counters, durations = registry.get_snapshot()

            # Process counters
            for name, entries in counters.items():
                data_points: list[dict[str, Any]] = []
                for label_tuples, val in entries.items():
                    attrs = [
                        {"key": k, "value": {"stringValue": str(v)}}
                        for k, v in label_tuples
                    ]
                    data_points.append({
                        "attributes": attrs,
                        "startTimeUnixNano": now_nano,
                        "timeUnixNano": now_nano,
                        "asInt": str(int(val)),
                    })
                if data_points:
                    metrics_payloads.append({
                        "name": name,
                        "description": "Workflow execution counter",
                        "unit": "1",
                        "sum": {
                            "aggregationTemporality": 2,  # CUMULATIVE
                            "isMonotonic": True,
                            "dataPoints": data_points,
                        },
                    })

            # Process duration summaries as histograms/sums
            for name, dur_entries in durations.items():
                data_points = []
                for label_tuples, values in dur_entries.items():
                    if not values:
                        continue
                    attrs = [
                        {"key": k, "value": {"stringValue": str(v)}}
                        for k, v in label_tuples
                    ]
                    data_points.append({
                        "attributes": attrs,
                        "startTimeUnixNano": now_nano,
                        "timeUnixNano": now_nano,
                        "count": str(len(values)),
                        "sum": float(sum(values)),
                        "bucketCounts": [str(len(values))],
                        "explicitBounds": [],
                    })
                if data_points:
                    metrics_payloads.append({
                        "name": name,
                        "description": "Workflow duration in seconds",
                        "unit": "s",
                        "histogram": {
                            "aggregationTemporality": 2,  # CUMULATIVE
                            "dataPoints": data_points,
                        },
                    })

            if not metrics_payloads:
                return True

            payload = {
                "resourceMetrics": [
                    {
                        "resource": {
                            "attributes": [
                                {
                                    "key": "service.name",
                                    "value": {"stringValue": self._service_name},
                                }
                            ]
                        },
                        "scopeMetrics": [
                            {
                                "scope": {
                                    "name": "ai_search_journey",
                                    "version": "2.0.0",
                                },
                                "metrics": metrics_payloads,
                            }
                        ],
                    }
                ]
            }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self._endpoint,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ai-search-journey-lab-metrics-exporter/2.0.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return bool(200 <= resp.status < 300)
        except Exception as exc:
            logger.debug("OTLP metrics export to %s failed safely: %s", self._endpoint, exc)
            return False


class MetricsRegistry:
    """Thread-safe in-memory metrics registry supporting Prometheus scraping and OTLP export."""

    _instance: MetricsRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._access_lock = threading.RLock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}
        self._durations: dict[str, dict[tuple[tuple[str, str], ...], list[float]]] = {}
        self._exporter: OtlpHttpJsonMetricsExporter | None = None

    @classmethod
    def get_instance(cls) -> MetricsRegistry:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def set_exporter(self, exporter: OtlpHttpJsonMetricsExporter | None) -> None:
        with self._access_lock:
            self._exporter = exporter

    def clear(self) -> None:
        with self._access_lock:
            self._counters.clear()
            self._durations.clear()

    def get_snapshot(
        self,
    ) -> tuple[
        dict[str, dict[tuple[tuple[str, str], ...], float]],
        dict[str, dict[tuple[tuple[str, str], ...], list[float]]],
    ]:
        with self._access_lock:
            counters_copy = {k: dict(v) for k, v in self._counters.items()}
            durations_copy = {
                k: {lk: list(lv) for lk, lv in v.items()}
                for k, v in self._durations.items()
            }
            return counters_copy, durations_copy

    def inc_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric safely."""
        with self._access_lock:
            safe_labels = self._sanitize_labels(labels)
            label_key = tuple(sorted(safe_labels.items()))
            if name not in self._counters:
                self._counters[name] = {}
            self._counters[name][label_key] = self._counters[name].get(label_key, 0.0) + value

    def record_duration(
        self, name: str, duration_seconds: float, labels: dict[str, str] | None = None
    ) -> None:
        """Record a latency/duration observation safely."""
        with self._access_lock:
            safe_labels = self._sanitize_labels(labels)
            label_key = tuple(sorted(safe_labels.items()))
            if name not in self._durations:
                self._durations[name] = {}
            if label_key not in self._durations[name]:
                self._durations[name][label_key] = []
            self._durations[name][label_key].append(max(0.0, float(duration_seconds)))

    def flush(self) -> None:
        """Flush metrics to configured OTLP metrics exporter if available."""
        with self._access_lock:
            if self._exporter:
                self._exporter.export_metrics(self)

    def _sanitize_labels(self, labels: dict[str, str] | None) -> dict[str, str]:
        if not labels:
            return {}
        safe: dict[str, str] = {}
        for k, v in labels.items():
            if not is_sensitive_key(str(k)):
                safe[str(k)] = _sanitize_metric_label(v)
        return safe

    def generate_prometheus_text(self) -> str:
        """Generate Prometheus exposition text format."""
        with self._access_lock:
            lines: list[str] = []
            lines.append(
                "# HELP ai_search_journey_requests_total Total count of workflow executions"
            )
            lines.append("# TYPE ai_search_journey_requests_total counter")

            for name, entries in sorted(self._counters.items()):
                for label_tuples, val in sorted(entries.items()):
                    if label_tuples:
                        label_str = ",".join(f'{k}="{v}"' for k, v in label_tuples)
                        lines.append(f"{name}{{{label_str}}} {val}")
                    else:
                        lines.append(f"{name} {val}")

            for name, duration_entries in sorted(self._durations.items()):
                lines.append(f"# HELP {name}_seconds Latency summary in seconds")
                lines.append(f"# TYPE {name}_seconds summary")
                for label_tuples, values in sorted(duration_entries.items()):
                    count = len(values)
                    total_sum = sum(values)
                    label_pairs = list(label_tuples)
                    label_str = ",".join(f'{k}="{v}"' for k, v in label_pairs)
                    prefix = f"{{{label_str}}}" if label_str else ""
                    lines.append(f"{name}_count{prefix} {count}")
                    lines.append(f"{name}_sum{prefix} {total_sum:.6f}")

            return "\n".join(lines) + "\n"
