#!/usr/bin/env python3
"""Run repository type checks in a single maintainable entry point."""

from __future__ import annotations

import subprocess
import sys

# Force UTF-8 on Windows consoles whose default codec (cp1252) cannot encode
# emoji glyphs used in success messages — raises UnicodeEncodeError otherwise.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _run_step(command: list[str], success_message: str) -> None:
    """Run a typecheck command and stop immediately if it fails."""
    print(f"Running: {' '.join(command)}")
    subprocess.run(command, check=True)
    print(success_message)

def main() -> int:
    """Run all typecheck steps and return the exit code."""
    try:
        _run_step(
            [
                sys.executable,
                "-m",
                "mypy",
                "custom_components/unifi_alerts",
                "--ignore-missing-imports",
            ],
            "✅ MyPy type check passed.",
        )
    except subprocess.CalledProcessError as error:
        return error.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
