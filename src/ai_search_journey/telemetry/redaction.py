"""Redaction and sanitization utilities for safe OpenTelemetry tracing."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# Patterns identifying potential secrets / API keys
_API_KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z-_]{10,}"),  # Google API key
    re.compile(r"ya29\.[0-9A-Za-z-_]+"),  # OAuth token
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|secret|token|password|auth)=([^\s&'\"]+)", re.IGNORECASE),
]

_SENSITIVE_KEY_SUBSTRINGS = (
    "key",
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "bearer",
    "api_key",
    "apikey",
    "prompt",
    "raw_prompt",
    "user_prompt",
    "system_prompt",
    "model_output",
    "response_text",
    "query_text",
    "raw_query",
)


def sanitize_string(val: str, max_length: int = 500) -> str:
    """Sanitize strings by removing secrets, stripping URL query parameters, and truncating."""
    if not val:
        return ""
    res = val
    if res.startswith("http://") or res.startswith("https://"):
        try:
            parsed = urlparse(res)
            scheme = parsed.scheme or "https"
            netloc = parsed.netloc.split("@")[-1]
            res = f"{scheme}://{netloc}{parsed.path}"
        except Exception:
            return "[INVALID_URL]"

    for pat in _API_KEY_PATTERNS:
        res = pat.sub("[REDACTED]", res)

    if len(res) > max_length:
        res = res[:max_length] + "..."
    return res


def sanitize_url(url: str | None) -> str | None:
    """Strip query strings and userinfo from URLs to ensure no keys leak."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        # Reconstruct without query parameters or credentials
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc.split("@")[-1]  # remove username:password if present
        clean = f"{scheme}://{netloc}{parsed.path}"
        return clean
    except Exception:
        return "[INVALID_URL]"


def sanitize_error_message(err: Exception | str) -> str:
    """Sanitize error messages, stripping API keys, tokens, or URL query parameters."""
    raw = str(err)
    return sanitize_string(raw, max_length=1000)


def sanitize_attribute_value(val: Any) -> Any:
    """Ensure attribute values are OpenTelemetry-compliant and free of secrets.

    OpenTelemetry supports: bool, int, float, str, or sequences thereof.
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        return sanitize_string(val)
    if isinstance(val, (list, tuple)):
        # Convert to tuple/list of sanitized primitive values
        return [sanitize_attribute_value(item) for item in val if item is not None]
    if isinstance(val, dict):
        # Convert dict to a sanitized scalar/str representation or summary
        return f"<dict len={len(val)}>"
    return sanitize_string(str(val))


def is_sensitive_key(key: str) -> bool:
    """Check if an attribute key name suggests confidential or secret contents."""
    lowered = key.lower()
    return any(sub in lowered for sub in _SENSITIVE_KEY_SUBSTRINGS)
