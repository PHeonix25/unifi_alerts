"""Console-encoding helper for the standalone `scripts/*.py` entry points.

Several scripts print status lines that contain non-ASCII glyphs (e.g. the
U+2705 ✅ check mark used as a success marker). On Windows, when stdout is
attached to a console whose default codec is `cp1252` (the default on most
non-internationalised Windows installs), `print("✅ …")` raises
`UnicodeEncodeError` and the script exits non-zero — even though the
underlying tool (ruff, mypy, etc.) succeeded.

`use_utf8_console()` forces stdout and stderr to UTF-8 before any prints
happen, so the scripts behave identically on Linux, macOS, and Windows
without requiring contributors to set `PYTHONIOENCODING=utf-8` in their
shell. `errors="replace"` ensures even an exotic console that still cannot
encode the bytes degrades gracefully (printing `?`) rather than crashing.

The helper lives in `scripts/` (not the integration package) because it
must be importable from standalone scripts that are invoked as
`python scripts/<name>.py`. In that mode Python adds the script's
directory to `sys.path[0]`, so `from _console import use_utf8_console`
works without any `sys.path` manipulation.
"""

from __future__ import annotations

import sys


def use_utf8_console() -> None:
    """Reconfigure sys.stdout and sys.stderr to UTF-8 if possible.

    `TextIOWrapper.reconfigure` is available on Python 3.7+; this project
    floors at 3.12 so the `hasattr` guard is purely defensive (covers
    streams that have already been replaced with non-TextIOWrapper
    objects, e.g. by a test harness or a CI runner).
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
