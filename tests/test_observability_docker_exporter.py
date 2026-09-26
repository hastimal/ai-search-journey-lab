from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, Status, StatusCode, TraceFlags

from ai_search_journey.telemetry.exporter import (
    MetricsRegistry,
    OtlpHttpJsonSpanExporter,
    _format_otlp_attribute_value,
    _sanitize_metric_label,
    _span_to_otlp_dict,
)
from ai_search_journey.telemetry.tracer import init_telemetry, trace_span


def test_sanitize_metric_label() -> None:
    assert _sanitize_metric_label(None) == "none"
    assert _sanitize_metric_label("v1_search") == "v1_search"
    assert _sanitize_metric_label("https://example.com/api?key=secret") == "url"
    assert _sanitize_metric_label("user_password") == "[REDACTED]"
    assert _sanitize_metric_label("api_key") == "[REDACTED]"


def test_format_otlp_attribute_value() -> None:
    assert _format_otlp_attribute_value(True) == {"boolValue": True}
    assert _format_otlp_attribute_value(42) == {"intValue": "42"}
    assert _format_otlp_attribute_value(3.14) == {"doubleValue": 3.14}
    assert _format_otlp_attribute_value("test") == {"stringValue": "test"}
    assert _format_otlp_attribute_value(["a", "b"]) == {
        "arrayValue": {"values": [{"stringValue": "a"}, {"stringValue": "b"}]}
    }


def test_span_to_otlp_dict_redaction() -> None:
    ctx = SpanContext(
        trace_id=12345678901234567890,
        span_id=12345678,
        is_remote=False,
        trace_flags=TraceFlags(0x01),
    )
    span = ReadableSpan(
        name="journey.search_to_decision",
        context=ctx,
        parent=None,
        attributes={
            "workflow.stage": "v1",
            "journey.query_type": "dentist",
            "prompt": "Find dentists in Houston",
            "api_key": "AIzaSySecret",
            "password": "secret_password",
        },
        events=[],
        status=Status(status_code=StatusCode.OK),
        start_time=1000000000,
        end_time=2000000000,
    )

    payload = _span_to_otlp_dict(span, service_name="test_service")
    assert payload["resource"]["attributes"][0]["value"]["stringValue"] == "test_service"
    spans = payload["scopeSpans"][0]["spans"]
    assert len(spans) == 1
    s0 = spans[0]
    assert s0["name"] == "journey.search_to_decision"

    # Verify sensitive attributes were excluded from export
    exported_keys = [attr["key"] for attr in s0["attributes"]]
    assert "workflow.stage" in exported_keys
    assert "journey.query_type" in exported_keys
    assert "prompt" not in exported_keys
    assert "api_key" not in exported_keys
    assert "password" not in exported_keys


def test_otlp_exporter_export_success() -> None:
    exporter = OtlpHttpJsonSpanExporter(
        endpoint="http://localhost:4318",
        service_name="ai_search_journey",
    )
    ctx = SpanContext(trace_id=1, span_id=2, is_remote=False)
    span = ReadableSpan(
        name="test_span",
        context=ctx,
        parent=None,
        attributes={"workflow.stage": "v1"},
        status=Status(status_code=StatusCode.OK),
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = exporter.export([span])
        assert result == SpanExportResult.SUCCESS
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:4318/v1/traces"
        body = json.loads(req.data.decode("utf-8"))
        assert "resourceSpans" in body


def test_otlp_exporter_export_failure_fails_safely() -> None:
    exporter = OtlpHttpJsonSpanExporter(endpoint="http://localhost:4318")
    ctx = SpanContext(trace_id=1, span_id=2, is_remote=False)
    span = ReadableSpan(
        name="test_span",
        context=ctx,
        parent=None,
        attributes={},
        status=Status(status_code=StatusCode.OK),
    )

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        # Must not raise an unhandled exception, must return SpanExportResult.FAILURE
        result = exporter.export([span])
        assert result == SpanExportResult.FAILURE


def test_metrics_registry_records_and_sanitizes() -> None:
    registry = MetricsRegistry()
    registry.clear()

    registry.inc_counter(
        "ai_search_journey_requests_total",
        value=1.0,
        labels={"workflow": "v1_search", "status": "success", "api_key": "secret"},
    )
    registry.record_duration(
        "ai_search_journey_duration",
        duration_seconds=1.25,
        labels={"workflow": "v1_search", "status": "success"},
    )

    prom_text = registry.generate_prometheus_text()
    expected_metric = 'ai_search_journey_requests_total{status="success",workflow="v1_search"} 1.0'
    assert expected_metric in prom_text
    assert "api_key" not in prom_text
    assert "ai_search_journey_duration_count" in prom_text
    assert "ai_search_journey_duration_sum" in prom_text


def test_init_telemetry_disabled_by_default() -> None:
    # When no endpoint is configured, init_telemetry completes without error
    with patch("ai_search_journey.telemetry.tracer.settings.otel_exporter_otlp_endpoint", None):
        store = init_telemetry(max_runs=50)
        assert store is not None


def test_init_telemetry_with_otlp_endpoint() -> None:
    # When endpoint is configured, init_telemetry attaches exporter safely
    with patch(
        "ai_search_journey.telemetry.tracer.settings.otel_exporter_otlp_endpoint",
        "http://localhost:4318",
    ):
        store = init_telemetry(max_runs=50)
        assert store is not None


def test_trace_span_records_metrics_safely() -> None:
    registry = MetricsRegistry.get_instance()
    registry.clear()

    with trace_span("journey.search_to_decision", attributes={"workflow.stage": "v1"}):
        pass

    prom_text = registry.generate_prometheus_text()
    assert "ai_search_journey_requests_total" in prom_text
    assert 'stage="v1"' in prom_text
    assert 'status="ok"' in prom_text


def test_otlp_metrics_exporter_export() -> None:
    from ai_search_journey.telemetry.exporter import OtlpHttpJsonMetricsExporter

    registry = MetricsRegistry()
    registry.clear()
    registry.inc_counter(
        "ai_search_journey_requests_total",
        value=2.0,
        labels={"stage": "v4", "status": "ok"},
    )
    registry.record_duration(
        "ai_search_journey_duration_seconds",
        duration_seconds=1.5,
        labels={"stage": "v4", "status": "ok"},
    )

    exporter = OtlpHttpJsonMetricsExporter(
        endpoint="http://localhost:4318",
        service_name="ai_search_journey",
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        success = exporter.export_metrics(registry)
        assert success is True
        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:4318/v1/metrics"
        body = json.loads(req.data.decode("utf-8"))
        assert "resourceMetrics" in body


def test_grafana_dashboard_tempo_configuration() -> None:
    """Verify Grafana dashboard JSON contains valid Tempo datasource and TraceQL filters."""
    import pathlib

    dashboard_path = (
        pathlib.Path(__file__).parent.parent
        / "observability"
        / "grafana"
        / "provisioning"
        / "dashboards"
        / "ai_search_journey_dashboard.json"
    )
    assert dashboard_path.exists(), "Dashboard JSON must exist"

    content = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panels = content.get("panels", [])

    tempo_panels = [
        p
        for p in panels
        if isinstance(p.get("datasource"), dict) and p["datasource"].get("uid") == "tempo"
    ]
    assert len(tempo_panels) >= 1, "Dashboard must have at least one panel with Tempo datasource"

    tempo_panel = tempo_panels[0]
    targets = tempo_panel.get("targets", [])
    assert len(targets) >= 1, "Tempo panel must have targets"

    query = targets[0].get("query", "")
    assert query != "{}", "TraceQL query must not be an empty matcher '{}'"
    assert 'span.workflow.stage = "v4"' in query or "span.workflow.stage = 'v4'" in query
    assert 'resource.service.name = "ai_search_journey"' in query


