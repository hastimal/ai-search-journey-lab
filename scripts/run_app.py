"""Helper script to launch the Streamlit Search Journey Inspector GUI."""

import subprocess
import sys


def main() -> None:
    """Launch the Streamlit app using subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/ai_search_journey/app.py",
        "--server.headless=true",
    ]
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
