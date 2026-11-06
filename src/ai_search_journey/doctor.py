"""Environment and configuration diagnostics for AI Search Journey Lab."""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence


class CheckStatus(str, Enum):
    """Status level for an individual diagnostic check."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DiagnosticResult:
    """Represents the outcome of a single diagnostic check."""

    category: str
    name: str
    status: CheckStatus
    message: str
    remediation: str | None = None


def mask_secret(value: str | None) -> str:
    """Safely mask sensitive values so keys are never printed in full."""
    if not value or not value.strip():
        return "(not set)"
    clean = value.strip().strip("'\"")
    if len(clean) < 16:
        return "********"
    return f"{clean[:4]}...{clean[-4:]}"


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a local TCP port is currently listening / bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def is_module_available(module_name: str) -> bool:
    """Safely check if a Python module is importable without raising exceptions."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError, AttributeError, ImportError):
        return False


def check_python_version() -> DiagnosticResult:
    """Verify that Python version meets the required >= 3.12 floor."""
    current = sys.version_info
    major = getattr(current, "major", current[0])
    minor = getattr(current, "minor", current[1])
    micro = getattr(current, "micro", current[2]) if len(current) > 2 else 0
    version_str = f"{major}.{minor}.{micro}"
    if (major, minor) >= (3, 12):
        return DiagnosticResult(
            category="Runtime",
            name="Python Version",
            status=CheckStatus.PASS,
            message=f"Python {version_str} meets requirement (>= 3.12)",
        )
    return DiagnosticResult(
        category="Runtime",
        name="Python Version",
        status=CheckStatus.FAIL,
        message=f"Python {version_str} is unsupported (requires >= 3.12)",
        remediation="Install Python 3.12 or newer and recreate your virtual environment.",
    )


def check_core_dependencies() -> DiagnosticResult:
    """Check presence of required core dependencies."""
    required = [
        ("google-genai", "google.genai"),
        ("streamlit", "streamlit"),
        ("pydantic", "pydantic"),
        ("pydantic-settings", "pydantic_settings"),
        ("requests", "requests"),
        ("python-dotenv", "dotenv"),
        ("pillow", "PIL"),
        ("opentelemetry-api", "opentelemetry"),
    ]
    missing = [pkg for pkg, mod in required if not is_module_available(mod)]
    if not missing:
        return DiagnosticResult(
            category="Dependencies",
            name="Core Packages",
            status=CheckStatus.PASS,
            message="All core packages are installed",
        )
    return DiagnosticResult(
        category="Dependencies",
        name="Core Packages",
        status=CheckStatus.FAIL,
        message=f"Missing required packages: {', '.join(missing)}",
        remediation="Run: pip install -e .",
    )


def check_optional_dependencies() -> DiagnosticResult:
    """Check optional dependencies (BigQuery and v4-agent extras)."""
    optional = [
        ("google-cloud-bigquery (v3 analytics)", "google.cloud.bigquery"),
        ("mcp (v4-agent)", "mcp"),
    ]
    missing = [pkg for pkg, mod in optional if not is_module_available(mod)]
    if not missing:
        return DiagnosticResult(
            category="Dependencies",
            name="Optional Extras",
            status=CheckStatus.PASS,
            message="Optional extras (bigquery, v4-agent) are installed",
        )
    return DiagnosticResult(
        category="Dependencies",
        name="Optional Extras",
        status=CheckStatus.WARN,
        message=f"Missing optional extras: {', '.join(missing)}",
        remediation='Install optional extras if needed: pip install -e ".[bigquery,v4-agent]"',
    )


def _load_env_dict() -> dict[str, str]:
    """Helper to read .env file values without relying on external libraries."""
    env_vars: dict[str, str] = {}
    env_file = Path(".env")
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
    # OS environment overrides .env
    for k, v in os.environ.items():
        env_vars[k] = v
    return env_vars


def check_gemini_config(env: dict[str, str] | None = None) -> DiagnosticResult:
    """Verify Gemini API configuration without exposing secrets."""
    env_vars = env if env is not None else _load_env_dict()
    key = env_vars.get("GEMINI_API_KEY")
    masked = mask_secret(key)
    if key and key.strip() and not key.startswith("your_") and not key.startswith("YOUR_"):
        return DiagnosticResult(
            category="Configuration",
            name="Gemini API Key",
            status=CheckStatus.PASS,
            message=f"Configured ({masked})",
        )
    return DiagnosticResult(
        category="Configuration",
        name="Gemini API Key",
        status=CheckStatus.WARN,
        message=f"GEMINI_API_KEY is not set or placeholder ({masked})",
        remediation="Add valid GEMINI_API_KEY to .env to use live Gemini features.",
    )


def check_maps_config(env: dict[str, str] | None = None) -> DiagnosticResult:
    """Verify Google Maps / Places API configuration without exposing secrets."""
    env_vars = env if env is not None else _load_env_dict()
    key = env_vars.get("GOOGLE_MAPS_API_KEY")
    masked = mask_secret(key)
    if key and key.strip() and not key.startswith("your_") and not key.startswith("YOUR_"):
        return DiagnosticResult(
            category="Configuration",
            name="Google Maps API Key",
            status=CheckStatus.PASS,
            message=f"Configured ({masked})",
        )
    return DiagnosticResult(
        category="Configuration",
        name="Google Maps API Key",
        status=CheckStatus.WARN,
        message=f"GOOGLE_MAPS_API_KEY is not set or placeholder ({masked})",
        remediation="Add valid GOOGLE_MAPS_API_KEY to .env to enable live search and places.",
    )


def check_bigquery_config(env: dict[str, str] | None = None) -> DiagnosticResult:
    """Check optional BigQuery project configuration."""
    env_vars = env if env is not None else _load_env_dict()
    project = env_vars.get("BIGQUERY_PROJECT")
    if project and project.strip():
        return DiagnosticResult(
            category="Configuration",
            name="BigQuery (Optional)",
            status=CheckStatus.PASS,
            message=f"Project set to '{project.strip()}'",
        )
    return DiagnosticResult(
        category="Configuration",
        name="BigQuery (Optional)",
        status=CheckStatus.WARN,
        message="BIGQUERY_PROJECT is not set (optional for local in-memory runs)",
        remediation="Set BIGQUERY_PROJECT in .env if testing BigQuery persistence (Stage 3).",
    )


def check_docker_availability() -> DiagnosticResult:
    """Detect Docker daemon without starting any containers."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return DiagnosticResult(
            category="Infrastructure",
            name="Docker",
            status=CheckStatus.WARN,
            message="Docker CLI binary not found in PATH",
            remediation=(
                "Install Docker Desktop or Docker Engine "
                "if you plan to run containerized services."
            ),
        )
    try:
        proc = subprocess.run(
            [docker_bin, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
        )
        if proc.returncode == 0:
            return DiagnosticResult(
                category="Infrastructure",
                name="Docker",
                status=CheckStatus.PASS,
                message="Docker daemon is running and reachable",
            )
        return DiagnosticResult(
            category="Infrastructure",
            name="Docker",
            status=CheckStatus.WARN,
            message="Docker daemon is not running or current user lacks socket permissions",
            remediation="Start Docker: 'sudo systemctl start docker' or open Docker Desktop.",
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return DiagnosticResult(
            category="Infrastructure",
            name="Docker",
            status=CheckStatus.WARN,
            message=f"Docker check timed out or failed: {e}",
            remediation="Ensure Docker daemon is responsive.",
        )


def check_port_conflicts(ports: Sequence[tuple[int, str]] | None = None) -> DiagnosticResult:
    """Detect potential port conflicts on standard ports used by the app and observability."""
    check_list = ports or [
        (8080, "App (Docker default)"),
        (8501, "Streamlit default"),
        (3000, "Grafana"),
        (9090, "Prometheus"),
        (3200, "Tempo"),
        (4317, "OTel gRPC"),
        (4318, "OTel HTTP"),
    ]
    conflicts: list[str] = []
    for port, service in check_list:
        if is_port_in_use(port):
            conflicts.append(f"{port} ({service})")

    if not conflicts:
        return DiagnosticResult(
            category="Infrastructure",
            name="Port Availability",
            status=CheckStatus.PASS,
            message="All standard ports are free (8080, 8501, 3000, 9090, 3200, 4317, 4318)",
        )
    return DiagnosticResult(
        category="Infrastructure",
        name="Port Availability",
        status=CheckStatus.WARN,
        message=f"Ports currently in use: {', '.join(conflicts)}",
        remediation=(
            "Check running processes or containers if encountering bind errors "
            "when starting services."
        ),
    )


def check_filesystem_permissions() -> DiagnosticResult:
    """Verify read and write access to current working directory and .env."""
    can_write_cwd = os.access(".", os.W_OK)
    if not can_write_cwd:
        return DiagnosticResult(
            category="Filesystem",
            name="Permissions",
            status=CheckStatus.FAIL,
            message="Current working directory is not writable",
            remediation="Ensure proper file permissions for the workspace directory.",
        )
    env_file = Path(".env")
    if env_file.exists():
        if not os.access(env_file, os.R_OK):
            return DiagnosticResult(
                category="Filesystem",
                name="Permissions",
                status=CheckStatus.FAIL,
                message=".env exists but is not readable",
                remediation="Fix .env permissions: chmod 600 .env",
            )
        if os.name == "posix":
            try:
                if env_file.stat().st_mode & 0o004:
                    return DiagnosticResult(
                        category="Filesystem",
                        name="Permissions",
                        status=CheckStatus.WARN,
                        message=".env file is world-readable, which may expose API keys",
                        remediation="Restrict permissions: chmod 600 .env",
                    )
            except OSError:
                pass
    return DiagnosticResult(
        category="Filesystem",
        name="Permissions",
        status=CheckStatus.PASS,
        message="Workspace and configuration files are accessible",
    )


def run_all_diagnostics(
    custom_checks: Sequence[Callable[[], DiagnosticResult]] | None = None,
) -> list[DiagnosticResult]:
    """Execute all diagnostic checks in sequence and return their results."""
    checks = custom_checks or [
        check_python_version,
        check_core_dependencies,
        check_optional_dependencies,
        check_filesystem_permissions,
        check_gemini_config,
        check_maps_config,
        check_bigquery_config,
        check_docker_availability,
        check_port_conflicts,
    ]
    return [check() for check in checks]


def print_diagnostic_report(results: list[DiagnosticResult]) -> int:
    """Print formatted diagnostic summary to stdout and return exit code."""
    colors = {
        CheckStatus.PASS: "\033[32m",  # Green
        CheckStatus.WARN: "\033[33m",  # Yellow
        CheckStatus.FAIL: "\033[31m",  # Red
    }
    reset = "\033[0m"

    # Header
    print("\nAI Search Journey Lab — Environment Diagnostics\n" + "=" * 55)

    passes = 0
    warns = 0
    fails = 0

    current_category = ""
    for r in results:
        if r.category != current_category:
            current_category = r.category
            print(f"\n[{current_category}]")

        status_tag = f"[{r.status.value}]"
        # Colorize if stdout is a tty or standard terminal
        if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
            colored_tag = f"{colors[r.status]}{status_tag:<6}{reset}"
        else:
            colored_tag = f"{status_tag:<6}"

        print(f"  {colored_tag} {r.name}: {r.message}")
        if r.remediation:
            print(f"         👉 Remediation: {r.remediation}")

        if r.status == CheckStatus.PASS:
            passes += 1
        elif r.status == CheckStatus.WARN:
            warns += 1
        elif r.status == CheckStatus.FAIL:
            fails += 1

    print("\n" + "=" * 55)
    print(f"Summary: {passes} passed, {warns} warnings, {fails} failures")

    if fails > 0:
        print("❌ Environment has critical failures that must be addressed before running.")
        return 1
    if warns > 0:
        print("⚠️ Environment is functional, but optional features or keys are missing.")
        return 0
    print("✅ Environment is fully configured and ready to run.")
    return 0
