"""Command-line interface for AI Search Journey Lab."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

try:
    from ai_search_journey.doctor import print_diagnostic_report, run_all_diagnostics
except ImportError:
    from doctor import print_diagnostic_report, run_all_diagnostics  # type: ignore[no-redef]


def create_parser() -> argparse.ArgumentParser:
    """Create top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="ai-search-journey-lab",
        description="AI Search Journey Lab command-line tool.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Doctor subcommand
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose environment, configuration, and dependencies.",
    )
    doctor_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Display extended diagnostic information.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entrypoint."""
    args_list = sys.argv[1:] if argv is None else list(argv)
    parser = create_parser()

    if not args_list:
        parser.print_help()
        return 0

    args = parser.parse_args(args_list)

    if args.subcommand == "doctor":
        results = run_all_diagnostics()
        return print_diagnostic_report(results)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
