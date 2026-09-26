"""Process-local, thread-safe in-memory store for OpenTelemetry spans."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from ai_search_journey.telemetry.redaction import (
    is_sensitive_key,
    sanitize_attribute_value,
    sanitize_error_message,
)


@dataclass(frozen=True)
class TelemetrySpanView:
    """Safe, immutable read-only view of a completed span for the UI."""

    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    run_id: str
    start_time_iso: str
    end_time_iso: str
    duration_ms: float
    status: str  # "OK", "ERROR", "UNSET"
    status_description: str | None
    attributes: dict[str, Any]
    error_message: str | None = None
    stage: str = "v1"  # "v1", "v3", "v4", or "custom"


class TelemetryStore:
    """Singleton process-local, thread-safe in-memory store with bounded capacity."""

    _instance: TelemetryStore | None = None
    _lock = threading.Lock()

    def __init__(self, max_runs: int = 50, max_spans_per_run: int = 100) -> None:
        self._max_runs = max_runs
        self._max_spans_per_run = max_spans_per_run
        self._access_lock = threading.RLock()
        # Keep track of run order in FIFO
        self._run_order: deque[str] = deque()
        # Map run_id -> list of spans
        self._spans_by_run: dict[str, list[TelemetrySpanView]] = {}
        # Map run_id -> run metadata (e.g. stage, start_time, duration, status)
        self._run_metadata: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_instance(cls, max_runs: int = 50) -> TelemetryStore:
        """Get or create the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(max_runs=max_runs)
            elif max_runs != 50:
                cls._instance._max_runs = max_runs
            return cls._instance

    def clear(self) -> None:
        """Clear all stored runs and spans (useful for tests)."""
        with self._access_lock:
            self._run_order.clear()
            self._spans_by_run.clear()
            self._run_metadata.clear()

    def add_span(self, span: ReadableSpan) -> TelemetrySpanView:
        """Convert a ReadableSpan into a TelemetrySpanView and store it safely."""
        with self._access_lock:
            # Extract safe attributes
            safe_attrs: dict[str, Any] = {}
            if span.attributes:
                for k, v in span.attributes.items():
                    if is_sensitive_key(str(k)):
                        continue
                    safe_attrs[str(k)] = sanitize_attribute_value(v)

            # Group executions by OpenTelemetry trace ID (canonical safe internal ID)
            trace_hex = f"trace_{span.context.trace_id:032x}"
            run_id = (
                str(safe_attrs.get("journey.run_id"))
                if "journey.run_id" in safe_attrs
                else trace_hex
            )

            # Identify stage
            stage = "v1"
            if span.name.startswith("visibility.") or "visibility.scan_id" in safe_attrs:
                stage = "v3"
            elif span.name.startswith("v4.") or "v4.session_id" in safe_attrs:
                stage = "v4"

            # Compute timing
            start_ns = span.start_time or 0
            end_ns = span.end_time or start_ns
            duration_ms = max(0.0, (end_ns - start_ns) / 1_000_000.0)

            start_dt = datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc)
            end_dt = datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc)

            # Status
            status_code = span.status.status_code
            status_str = "OK"
            if status_code == StatusCode.ERROR:
                status_str = "ERROR"
            elif status_code == StatusCode.UNSET:
                status_str = "UNSET"

            status_desc = span.status.description
            if status_desc:
                status_desc = sanitize_error_message(status_desc)

            error_msg = None
            if span.events:
                for ev in span.events:
                    if ev.name == "exception" and ev.attributes:
                        raw_ex = ev.attributes.get("exception.message")
                        if raw_ex:
                            error_msg = sanitize_error_message(str(raw_ex))
                            break

            parent_id = f"{span.parent.span_id:016x}" if span.parent else None

            view = TelemetrySpanView(
                name=span.name,
                trace_id=f"{span.context.trace_id:032x}",
                span_id=f"{span.context.span_id:016x}",
                parent_span_id=parent_id,
                run_id=run_id,
                start_time_iso=start_dt.isoformat(),
                end_time_iso=end_dt.isoformat(),
                duration_ms=round(duration_ms, 2),
                status=status_str,
                status_description=status_desc,
                attributes=safe_attrs,
                error_message=error_msg,
                stage=stage,
            )

            # Manage FIFO capacity for runs
            if run_id not in self._spans_by_run:
                if len(self._run_order) >= self._max_runs:
                    oldest = self._run_order.popleft()
                    self._spans_by_run.pop(oldest, None)
                    self._run_metadata.pop(oldest, None)
                self._run_order.append(run_id)
                self._spans_by_run[run_id] = []
                self._run_metadata[run_id] = {
                    "run_id": run_id,
                    "stage": stage,
                    "started_at": start_dt.isoformat(),
                    "status": status_str,
                    "span_count": 0,
                }

            run_spans = self._spans_by_run[run_id]
            if len(run_spans) < self._max_spans_per_run:
                run_spans.append(view)
                meta = self._run_metadata[run_id]
                meta["span_count"] = len(run_spans)
                if status_str == "ERROR":
                    meta["status"] = "ERROR"

            return view

    def get_runs(self, stage_filter: str | None = None) -> list[dict[str, Any]]:
        """Return list of run summaries in reverse chronological order."""
        with self._access_lock:
            runs = []
            for r_id in reversed(self._run_order):
                meta = self._run_metadata.get(r_id)
                if not meta:
                    continue
                if stage_filter and meta.get("stage") != stage_filter:
                    continue
                runs.append(dict(meta))
            return runs

    def get_spans_for_run(self, run_id: str) -> list[TelemetrySpanView]:
        """Return all spans for a specific run in order of occurrence."""
        with self._access_lock:
            return list(self._spans_by_run.get(run_id, []))

    def get_all_spans(self) -> list[TelemetrySpanView]:
        """Return all spans across all runs."""
        with self._access_lock:
            res: list[TelemetrySpanView] = []
            for r_id in self._run_order:
                res.extend(self._spans_by_run.get(r_id, []))
            return res
