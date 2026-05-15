#!/usr/bin/env python3
"""Run repository lint checks in a single maintainable entry point."""

from __future__ import annotations

import subprocess
import sys


def _run_step(command: list[str], success_message: str) -> None:
    """Run a lint command and stop immediately if it fails."""
    print(f"Running: {' '.join(command)}")
    subprocess.run(command, check=True)
    print(success_message)


def main() -> int:
    """Run all lint steps and return the exit code."""
    try:
        _run_step(
            [sys.executable, "-m", "ruff", "check", "custom_components/", "tests/"],
            "✅ Ruff check passed.",
        )
        print("")
        _run_step(
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--check",
                "custom_components/",
                "tests/",
            ],
            "✅ Ruff format passed.",
        )
    except subprocess.CalledProcessError as error:
        return error.returncode

    print("")
    print("✅ All lint checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
