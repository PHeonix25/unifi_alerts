#!/usr/bin/env python3
"""Verify file paths referenced in agentrc.eval.json still exist.

agentrc.eval.json holds planning-evaluation cases for agent harnesses (see
AGENTS.md). Nothing executes the cases themselves, but the file paths its
case text points agents at (e.g. `coordinator.py`, `test_coordinator.py`)
rot silently when files are renamed or split - see issue #287. This is a
cheap, mechanical guard against exactly that: it does not judge whether a
case's premise is still semantically accurate (that needs a human or an
LLM-graded harness - out of scope here), only whether the backtick-quoted
file paths in its prose still resolve to a real file in the tree.

Symbol-level references (function/class/constant names) are deliberately
not checked: several cases name constants a good plan is expected to *add*
(e.g. `CONF_DEDUP_WINDOW`), so a bare-identifier existence check would flag
those as false positives. File paths don't have that ambiguity in this
file's current cases, so this guard stops there.

Run via `make doc-check` or directly: `python3 scripts/check_agentrc_refs.py`.
Pure stdlib so it runs on Windows without venv setup.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _console import use_utf8_console

use_utf8_console()

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_FILE = REPO_ROOT / "agentrc.eval.json"

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "node_modules", ".claude", ".mypy_cache", ".ruff_cache"}
)

# Backtick-quoted spans in case prose, e.g. `coordinator.py` or `models.py`.
BACKTICK_SPAN = re.compile(r"`([^`]+)`")

# A span counts as a file reference if it ends with one of these extensions
# and contains no whitespace (rules out prose/shell snippets like `make check`).
FILE_LIKE = re.compile(r"^[\w./-]+\.(py|json|md|yml|yaml)$")


def _repo_files() -> list[Path]:
    """Every file in the repo, skipping excluded directories."""
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue
        files.append(path)
    return files


def _file_reference_exists(ref: str, files: list[Path]) -> bool:
    """True if `ref` resolves to a real file.

    Case prose paths are written relative to whichever directory the reader
    has in mind (repo root, or the component/test package), not consistently
    relative to the repo root. So a multi-segment ref matches if it is a
    real repo-root-relative path, or a suffix of any real file's relative
    path; a bare filename matches on basename alone.
    """
    if "/" in ref:
        if (REPO_ROOT / ref).is_file():
            return True
        return any(
            str(path.relative_to(REPO_ROOT)).replace("\\", "/").endswith(f"/{ref}")
            for path in files
        )
    return any(path.name == ref for path in files)


def main() -> int:
    """Check that file paths named in agentrc.eval.json's cases still exist."""
    if not EVAL_FILE.exists():
        print(f"error: {EVAL_FILE} does not exist", file=sys.stderr)
        return 1

    data = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    files = _repo_files()

    rc = 0
    for case in data.get("cases", []):
        case_id = case.get("id", "<unknown>")
        text = f"{case.get('prompt', '')} {case.get('expectation', '')}"
        seen: set[str] = set()
        for span in BACKTICK_SPAN.findall(text):
            if span in seen or not FILE_LIKE.match(span):
                continue
            seen.add(span)
            if not _file_reference_exists(span, files):
                print(
                    f"{EVAL_FILE.name}: {case_id} references '{span}', "
                    "which no longer exists in the tree",
                    file=sys.stderr,
                )
                rc = 1

    if rc == 0:
        print("✅ agentrc.eval.json file references check out.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
