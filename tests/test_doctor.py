"""Unit tests for ai-search-journey-lab doctor diagnostics and CLI."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

from ai_search_journey.cli import create_parser, main
from ai_search_journey.doctor import (
    CheckStatus,
    DiagnosticResult,
    check_bigquery_config,
    check_core_dependencies,
    check_docker_availability,
    check_filesystem_permissions,
    check_gemini_config,
    check_maps_config,
    check_optional_dependencies,
    check_port_conflicts,
    check_python_version,
    is_module_available,
    mask_secret,
    print_diagnostic_report,
    run_all_diagnostics,
)


def test_mask_secret() -> None:
    """Ensure secrets are never exposed in plaintext."""
    assert mask_secret(None) == "(not set)"
    assert mask_secret("") == "(not set)"
    assert mask_secret("   ") == "(not set)"
    assert mask_secret("short") == "********"
    assert mask_secret("123456789012") == "********"
    assert mask_secret("AIzaSy1234567890abcdef") == "AIza...cdef"
    assert "1234567890" not in mask_secret("AIzaSy1234567890abcdef")


def test_is_module_available() -> None:
    """Test safe module availability check."""
    assert is_module_available("sys") is True
    assert is_module_available("non_existent_module_xyz_123") is False


def test_check_python_version_pass() -> None:
    """Test python version check on supported version."""
    with patch.object(sys, "version_info", (3, 12, 0)):
        res = check_python_version()
        assert res.status == CheckStatus.PASS
        assert "meets requirement" in res.message


def test_check_python_version_fail() -> None:
    """Test python version check on unsupported version."""
    with patch.object(sys, "version_info", (3, 11, 4)):
        res = check_python_version()
        assert res.status == CheckStatus.FAIL
        assert "unsupported" in res.message
        assert res.remediation is not None


def test_check_core_dependencies_pass() -> None:
    """Test core dependencies check when all packages are available."""
    with patch("ai_search_journey.doctor.is_module_available", return_value=True):
        res = check_core_dependencies()
        assert res.status == CheckStatus.PASS
        assert "All core packages are installed" in res.message


def test_check_core_dependencies_fail() -> None:
    """Test core dependencies check when a required package is missing."""
    with patch("ai_search_journey.doctor.is_module_available", return_value=False):
        res = check_core_dependencies()
        assert res.status == CheckStatus.FAIL
        assert "Missing required packages" in res.message
        assert res.remediation is not None


def test_check_optional_dependencies_warn() -> None:
    """Test optional dependencies report WARN rather than FAIL when missing."""
    with patch("ai_search_journey.doctor.is_module_available", return_value=False):
        res = check_optional_dependencies()
        assert res.status == CheckStatus.WARN
        assert "Missing optional extras" in res.message
        assert res.remediation is not None


def test_check_gemini_config() -> None:
    """Verify Gemini API key check passes when configured and warns when missing."""
    # Configured
    res_pass = check_gemini_config({"GEMINI_API_KEY": "AIzaSyTestKey123456"})
    assert res_pass.status == CheckStatus.PASS
    assert "AIza...3456" in res_pass.message

    # Unset
    res_warn = check_gemini_config({})
    assert res_warn.status == CheckStatus.WARN

    # Placeholder
    res_placeholder = check_gemini_config({"GEMINI_API_KEY": "YOUR_GEMINI_API_KEY"})
    assert res_placeholder.status == CheckStatus.WARN


def test_check_maps_config() -> None:
    """Verify Google Maps API key check passes when configured and warns when missing."""
    res_pass = check_maps_config({"GOOGLE_MAPS_API_KEY": "AIzaSyMapsTestKey99"})
    assert res_pass.status == CheckStatus.PASS
    assert "AIza...ey99" in res_pass.message

    res_warn = check_maps_config({})
    assert res_warn.status == CheckStatus.WARN


def test_check_bigquery_config() -> None:
    """Verify BigQuery optional check passes when set and warns when unset."""
    res_pass = check_bigquery_config({"BIGQUERY_PROJECT": "my-gcp-project"})
    assert res_pass.status == CheckStatus.PASS

    res_warn = check_bigquery_config({})
    assert res_warn.status == CheckStatus.WARN


def test_check_docker_availability() -> None:
    """Test Docker daemon detection states without starting containers."""
    # Docker not in PATH
    with patch("shutil.which", return_value=None):
        res = check_docker_availability()
        assert res.status == CheckStatus.WARN
        assert "binary not found" in res.message

    # Docker running and reachable
    mock_success = MagicMock(returncode=0)
    with patch("shutil.which", return_value="/usr/bin/docker"), patch(
        "subprocess.run", return_value=mock_success
    ):
        res = check_docker_availability()
        assert res.status == CheckStatus.PASS
        assert "running and reachable" in res.message

    # Docker daemon stopped (returncode != 0)
    mock_fail = MagicMock(returncode=1)
    with patch("shutil.which", return_value="/usr/bin/docker"), patch(
        "subprocess.run", return_value=mock_fail
    ):
        res = check_docker_availability()
        assert res.status == CheckStatus.WARN
        assert "not running" in res.message

    # Docker check timeout
    with patch("shutil.which", return_value="/usr/bin/docker"), patch(
        "subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 3.0)
    ):
        res = check_docker_availability()
        assert res.status == CheckStatus.WARN
        assert "timed out" in res.message


def test_check_port_conflicts() -> None:
    """Test port availability check for clean and conflicting states."""
    # All ports free
    with patch("ai_search_journey.doctor.is_port_in_use", return_value=False):
        res = check_port_conflicts([(8080, "App"), (3000, "Grafana")])
        assert res.status == CheckStatus.PASS
        assert "free" in res.message

    # Port in use reports warning with service name
    with patch("ai_search_journey.doctor.is_port_in_use", side_effect=lambda p: p == 8080):
        res = check_port_conflicts([(8080, "App"), (3000, "Grafana")])
        assert res.status == CheckStatus.WARN
        assert "8080 (App)" in res.message


def test_check_filesystem_permissions() -> None:
    """Test filesystem permissions check."""
    with patch("os.access", return_value=True):
        res = check_filesystem_permissions()
        assert res.status == CheckStatus.PASS

    with patch("os.access", return_value=False):
        res = check_filesystem_permissions()
        assert res.status == CheckStatus.FAIL

    # World-readable .env warning on POSIX
    mock_stat = MagicMock(st_mode=0o100644)
    with (
        patch("os.access", return_value=True),
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.stat", return_value=mock_stat),
        patch("os.name", "posix"),
    ):
        res = check_filesystem_permissions()
        assert res.status == CheckStatus.WARN
        assert "world-readable" in res.message


def test_print_diagnostic_report_exit_codes() -> None:
    """Ensure report returns 0 on all pass/warn, and 1 if any failure occurs."""
    all_pass = [
        DiagnosticResult("Test", "Check 1", CheckStatus.PASS, "Good"),
        DiagnosticResult("Test", "Check 2", CheckStatus.WARN, "Warning"),
    ]
    assert print_diagnostic_report(all_pass) == 0

    has_fail = [
        DiagnosticResult("Test", "Check 1", CheckStatus.PASS, "Good"),
        DiagnosticResult("Test", "Check 2", CheckStatus.FAIL, "Bad", "Fix it"),
    ]
    assert print_diagnostic_report(has_fail) == 1


def test_run_all_diagnostics() -> None:
    """Ensure run_all_diagnostics executes default suite."""

    def dummy_check() -> DiagnosticResult:
        return DiagnosticResult("Cat", "Dummy", CheckStatus.PASS, "OK")

    results = run_all_diagnostics([dummy_check])
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASS


def test_cli_doctor_dispatch() -> None:
    """Test CLI parser and execution of doctor subcommand."""
    parser = create_parser()
    args = parser.parse_args(["doctor", "--verbose"])
    assert args.subcommand == "doctor"
    assert args.verbose is True

    # Test main function dispatch
    with patch("ai_search_journey.cli.run_all_diagnostics", return_value=[]), patch(
        "ai_search_journey.cli.print_diagnostic_report", return_value=0
    ) as mock_print:
        exit_code = main(["doctor"])
        assert exit_code == 0
        mock_print.assert_called_once()
