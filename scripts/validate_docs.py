#!/usr/bin/env python3
"""Documentation linter for unifi_alerts.

Catches AI-style prose patterns and HISTORY.md format drift before they land:

- em-dash characters
- unicode arrows
- "bundle/cluster/track/session N" framing phrases
- HISTORY.md h2 headings that are not `## YYYY-MM-DD`

Run via `make lint` or directly: `python3 scripts/validate_docs.py`. Exits
non-zero if any violations are found, printing `path:line:col: message` for
each one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Files in scope. Anything outside this list is ignored on purpose so plugin
# generated content (e.g. .claude, scripts) cannot trip the linter.
TARGET_GLOBS: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "README.md",
    "info.md",
    "SECURITY.md",
    "docs/*.md",
)

# (compiled pattern, human message). Patterns are matched per-line.
FORBIDDEN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"—"), "em-dash (use '-', ':', or ';')"),
    (re.compile(r"[→←↑↓]"), "unicode arrow (use '>', '->', or words)"),
    (
        re.compile(r"\bcluster [A-Za-z]\b"),
        "'cluster X' framing (describe what changed, not how it was bundled)",
    ),
    (
        re.compile(r"\bbundle \d+\b", re.IGNORECASE),
        "'bundle N' framing (describe what changed, not how it was bundled)",
    ),
    (
        re.compile(r"\btrack [A-Za-z]\b"),
        "'track X' framing (describe what changed, not how it was bundled)",
    ),
    (
        re.compile(r"\bsession \d+\b", re.IGNORECASE),
        "'session N' framing (describe what changed, not how it was bundled)",
    ),
]

# HISTORY.md every h2 must be a date heading. Plain `# History` (h1) is fine.
HISTORY_H2_VALID = re.compile(r"^## \d{4}-\d{2}-\d{2}\s*$")


def collect_files() -> list[Path]:
    """Collect all target markdown files from the repository."""
    files: list[Path] = []
    for pat in TARGET_GLOBS:
        files.extend(sorted(REPO.glob(pat)))
    return [f for f in files if f.is_file()]


def scan_forbidden(path: Path) -> list[tuple[int, int, str]]:
    """Scan file for forbidden patterns and return violations as (line, col, msg)."""
    out: list[tuple[int, int, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for pat, msg in FORBIDDEN:
            for m in pat.finditer(line):
                out.append((line_no, m.start() + 1, msg))
    return out


def scan_history_format(path: Path) -> list[tuple[int, int, str]]:
    """Check HISTORY.md h2 headings are in YYYY-MM-DD format."""
    out: list[tuple[int, int, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## ") and not HISTORY_H2_VALID.match(line):
            out.append((line_no, 1, "HISTORY.md h2 headings must be '## YYYY-MM-DD'"))
    return out


def main() -> int:
    """Run documentation validation checks on target files."""
    rc = 0
    for path in collect_files():
        rel = path.relative_to(REPO)
        violations = scan_forbidden(path)
        if path.name == "HISTORY.md":
            violations.extend(scan_history_format(path))
        violations.sort()
        for line_no, col, msg in violations:
            print(f"{rel}:{line_no}:{col}: {msg}", file=sys.stderr)
            rc = 1
    if rc == 0:
        print("✅ Docs validation passed.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
