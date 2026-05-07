#!/usr/bin/env python3
"""Verify strings.json and translations/en.json are byte-identical.

The integration uses both files: HA reads strings.json for the config flow
UI and translations/en.json for runtime. They MUST be identical or HA emits
warnings. CI enforces this; run locally via `make doc-check` or `make check`.

Pure stdlib so it runs on Windows without venv setup.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STRINGS = REPO_ROOT / "custom_components" / "unifi_alerts" / "strings.json"
EN = REPO_ROOT / "custom_components" / "unifi_alerts" / "translations" / "en.json"


def main() -> int:
    if not STRINGS.exists():
        print(f"error: {STRINGS} does not exist", file=sys.stderr)
        return 1
    if not EN.exists():
        print(f"error: {EN} does not exist", file=sys.stderr)
        return 1

    if STRINGS.read_bytes() != EN.read_bytes():
        print(
            f"error: {STRINGS.relative_to(REPO_ROOT)} and "
            f"{EN.relative_to(REPO_ROOT)} have drifted - keep them identical.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
