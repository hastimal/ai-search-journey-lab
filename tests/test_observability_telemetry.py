"""Unit tests for OpenTelemetry in-memory observability (V5).

Tests span nesting, duration/status capture, bounded retention,
failure capture, and redaction.
"""

from __future__ import annotations

import pytest

from ai_search_journey.telemetry import (
    TelemetryStore,
    init_telemetry,
    is_sensitive_key,
    sanitize_error_message,
    sanitize_string,
    sanitize_url,
    trace_span,
)


@pytest.fixture(autouse=True)
def clean_telemetry_store():
    store = init_telemetry(max_runs=5)
    store.clear()
    yield store
    store.clear()


def test_redaction_secrets_and_api_keys():
    """Verify that Google API keys, OAuth tokens, and auth headers are masked."""
    secret_key = "AIzaSyDummySecretKey123456789012345678"
    raw_text = f"Calling Google Places with key={secret_key} and Bearer ya29.a0AfH6SMDUMMYTOKEN"
    clean_text = sanitize_string(raw_text)

    assert secret_key not in clean_text
    assert "ya29." not in clean_text
    assert "[REDACTED]" in clean_text


def test_redaction_sensitive_keys():
    """Verify sensitive attribute keys are detected."""
    assert is_sensitive_key("gemini_api_key")
    assert is_sensitive_key("API_KEY")
    assert is_sensitive_key("authorization")
    assert is_sensitive_key("client_secret")
    assert not is_sensitive_key("category")
    assert not is_sensitive_key("duration_seconds")


def test_sanitize_url_removes_query_params():
    """Verify URL sanitization strips API keys and query parameters."""
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=29.4,-98.4&key=AIzaSySecret"
    clean = sanitize_url(url)
    assert clean == "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    assert "key=" not in clean
    assert "AIza" not in clean


def test_sanitize_error_message():
    """Verify error messages with sensitive tokens are sanitized."""
    err = ValueError("Failed connecting with key AIzaSyFakeApiKey12345678901234567890")
    sanitized = sanitize_error_message(err)
    assert "AIza" not in sanitized
    assert "[REDACTED]" in sanitized


def test_span_lifecycle_and_duration(clean_telemetry_store: TelemetryStore):
    """Verify span starts, captures duration > 0, records safe attributes, and completes with OK."""
    with trace_span(
        "test.step",
        attributes={"test.metric": 42, "api_key": "AIzaSyShouldBeOmitted"},
        run_id="run_test_123",
    ) as span:
        assert span.is_recording()

    spans = clean_telemetry_store.get_spans_for_run("run_test_123")
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "test.step"
    assert s.status == "OK"
    assert s.duration_ms >= 0.0
    assert s.attributes.get("test.metric") == 42
    # Sensitive key 'api_key' must not be in attributes
    assert "api_key" not in s.attributes


def test_single_process_span_nesting(clean_telemetry_store: TelemetryStore):
    """Verify parent/child span relationship within a single process."""
    run_id = "run_nesting_test"
    with trace_span("parent.operation", run_id=run_id):
        with trace_span("child.operation", run_id=run_id):
            pass

    spans = clean_telemetry_store.get_spans_for_run(run_id)
    assert len(spans) == 2
    # Child ends first, then parent
    child_view = next(s for s in spans if s.name == "child.operation")
    parent_view = next(s for s in spans if s.name == "parent.operation")

    assert child_view.parent_span_id == parent_view.span_id
    assert parent_view.parent_span_id is None


def test_span_failure_capture_sanitized(clean_telemetry_store: TelemetryStore):
    """Verify exceptions set span status to ERROR and sanitize the error message."""
    run_id = "run_failure_test"
    with pytest.raises(RuntimeError):
        with trace_span("failing.operation", run_id=run_id):
            raise RuntimeError("Secret leaked here: AIzaSyFakeApiKey12345678901234567890")

    spans = clean_telemetry_store.get_spans_for_run(run_id)
    assert len(spans) == 1
    s = spans[0]
    assert s.status == "ERROR"
    assert s.error_message is not None
    assert "AIza" not in s.error_message
    assert "[REDACTED]" in s.error_message


def test_bounded_retention_fifo(clean_telemetry_store: TelemetryStore):
    """Verify TelemetryStore enforces bounded FIFO capacity, evicting oldest run and its spans."""
    # Max runs is set to 5 in fixture
    for i in range(8):
        with trace_span(f"step_{i}", run_id=f"run_{i}", attributes={"metric_val": i}):
            pass

    runs = clean_telemetry_store.get_runs()
    # Retained run count does not exceed configured maximum of 5
    assert len(runs) == 5
    run_ids = [r["run_id"] for r in runs]

    # Oldest runs (run_0, run_1, run_2) are completely absent from runs list
    assert "run_0" not in run_ids
    assert "run_1" not in run_ids
    assert "run_2" not in run_ids

    # Spans of evicted runs are completely removed from store
    assert clean_telemetry_store.get_spans_for_run("run_0") == []
    assert clean_telemetry_store.get_spans_for_run("run_1") == []
    assert clean_telemetry_store.get_spans_for_run("run_2") == []

    # Newest runs are present with their spans
    assert "run_7" in run_ids
    assert "run_6" in run_ids
    assert len(clean_telemetry_store.get_spans_for_run("run_7")) == 1


def test_trace_span_end_to_end_redaction(clean_telemetry_store: TelemetryStore):
    """Verify trace_span handles unsafe attributes, stripping secrets and URL query params."""
    unsafe_attributes = {
        "raw_prompt": "Find coffee near Geekdom with secret prompt details",
        "user_prompt": "Tell me everything about the competitor",
        "api_key": "AIzaSyFakeGoogleApiKey123456789012345678",
        "authorization": "Bearer ya29.a0AfH6SMDUMMYTOKENFORTEST",
        "target_url": "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=29.4,-98.4&key=AIzaSySecretKey",
        "safe_count": 42,
        "is_supported": True,
    }

    run_id = "run_redaction_e2e"
    with trace_span("operation.with_unsafe_attrs", attributes=unsafe_attributes, run_id=run_id):
        pass

    spans = clean_telemetry_store.get_spans_for_run(run_id)
    assert len(spans) == 1
    stored_span = spans[0]
    attrs = stored_span.attributes

    # Sensitive keys (prompts, api keys, auth tokens) are omitted
    assert "raw_prompt" not in attrs
    assert "user_prompt" not in attrs
    assert "api_key" not in attrs
    assert "authorization" not in attrs
    assert "AIza" not in str(attrs)
    assert "ya29." not in str(attrs)

    # URL query parameters are stripped
    assert "target_url" in attrs
    assert attrs["target_url"] == "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    assert "location=" not in attrs["target_url"]
    assert "key=" not in attrs["target_url"]

    # Safe attributes are retained
    assert attrs.get("safe_count") == 42
    assert attrs.get("is_supported") is True
