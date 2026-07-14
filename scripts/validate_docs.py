#!/usr/bin/env python3
"""Documentation linter for unifi_alerts.

Catches AI-style prose patterns and HISTORY.md format drift before they land:

- em-dash characters
- unicode arrows
- "bundle/cluster/track/session N" framing phrases
- HISTORY.md h2 headings that are not `## YYYY-MM-DD`
- shared-fact blocks duplicated across the agent instruction files
- cross-file markdown pointers that do not resolve to an existing file
- markdown claims about `make <target>` capabilities that do not match Makefile

Scans every `*.md` file in the repository (excluding `.git`, `.venv`,
`node_modules`, `.claude`, and similar generated/vendored directories) so
new markdown added anywhere inherits the same rules automatically.

Run via `make doc-check` / `make validate` or directly:
`python3 scripts/validate_docs.py`. Exits non-zero if any violations are
found, printing `path:line:col: message` for each one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _console import use_utf8_console

use_utf8_console()

REPO = Path(__file__).resolve().parent.parent
MAKEFILE = REPO / "Makefile"

# Every markdown file in the repo is in scope, recursively, so the same rules
# apply to docs, agent definitions, PR templates, and anything else added
# later. Directories that hold generated or vendored content are excluded so
# the linter cannot trip on files we do not own.
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "node_modules", ".claude", ".mypy_cache", ".ruff_cache"}
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

# Single-sourcing of shared agent facts. AGENTS.md is the canonical home for the
# repo purpose, tech stack, build/test commands, and repo map. Each shared block
# is wrapped in a `<!-- shared:NAME -->` / `<!-- /shared:NAME -->` anchor pair in
# AGENTS.md and must not be copied into any other markdown file. `CANONICAL_FILE`
# is the one file allowed to carry the anchors.
CANONICAL_FILE = "AGENTS.md"
SHARED_ANCHORS: tuple[str, ...] = ("shared:stack", "shared:commands")

# The agent instruction files whose cross-file `.md` links must resolve.
AGENT_FILES: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    ".github/copilot-instructions.md",
)

# Markdown inline link: `[text](target)`.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MAKE_TARGET_REF = re.compile(
    r"`make\s+([a-z][a-z0-9-]*)`|^\s*make\s+([a-z][a-z0-9-]*)(?:\s|$)",
    re.IGNORECASE,
)


def _significant_lines(text: str) -> list[str]:
    """Return stripped, non-empty lines - a whitespace-insensitive signature."""
    return [stripped for line in text.splitlines() if (stripped := line.strip())]


def _extract_anchor_block(text: str, anchor: str) -> str | None:
    """Return the inner text between `<!-- anchor -->` and `<!-- /anchor -->`."""
    pattern = re.compile(
        rf"<!--\s*{re.escape(anchor)}\s*-->(.*?)<!--\s*/{re.escape(anchor)}\s*-->",
        re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1) if m else None


def _contains_subsequence(haystack: list[str], needle: list[str]) -> bool:
    """True if `needle` appears as a contiguous run inside `haystack`."""
    if not needle or len(needle) > len(haystack):
        return False
    first = needle[0]
    for i in range(len(haystack) - len(needle) + 1):
        if haystack[i] == first and haystack[i : i + len(needle)] == needle:
            return True
    return False


def scan_shared_blocks(files: list[Path]) -> list[str]:
    """Fail if a shared block is missing, multiply-anchored, or duplicated.

    Each anchor must appear in exactly one file (`CANONICAL_FILE`), and the block
    it wraps must not reappear (anchored or bare) in any other markdown file.
    Returns a list of human-readable violation messages.
    """
    texts = {path: path.read_text(encoding="utf-8") for path in files}

    violations: list[str] = []
    for anchor in SHARED_ANCHORS:
        marker = re.compile(rf"<!--\s*{re.escape(anchor)}\s*-->")
        anchored = [p for p, t in texts.items() if marker.search(t)]
        rels = sorted(str(p.relative_to(REPO)) for p in anchored)

        if not anchored:
            violations.append(
                f"shared block '{anchor}' has no anchor; expected it in {CANONICAL_FILE}"
            )
            continue
        if rels != [CANONICAL_FILE]:
            violations.append(
                f"shared block '{anchor}' must be anchored only in {CANONICAL_FILE}, "
                f"found in: {', '.join(rels)}"
            )

        canonical_path = next(
            (p for p in anchored if str(p.relative_to(REPO)) == CANONICAL_FILE), None
        )
        if canonical_path is None:
            continue
        inner = _extract_anchor_block(texts[canonical_path], anchor)
        if inner is None:
            violations.append(
                f"shared block '{anchor}' in {CANONICAL_FILE} is missing its closing anchor"
            )
            continue
        signature = _significant_lines(inner)
        for path, text in texts.items():
            if path == canonical_path:
                continue
            if _contains_subsequence(_significant_lines(text), signature):
                rel = path.relative_to(REPO)
                violations.append(
                    f"{rel}: duplicates the '{anchor}' block that is canonical in "
                    f"{CANONICAL_FILE}; link to {CANONICAL_FILE} instead"
                )
    return violations


def scan_pointers() -> list[str]:
    """Fail if an agent file links to a `.md` target that does not exist."""
    violations: list[str] = []
    for rel in AGENT_FILES:
        path = REPO / rel
        if not path.is_file():
            continue
        base = path.parent
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for m in MD_LINK.finditer(line):
                target = m.group(1).split()[0]  # drop any `(url "title")`
                target = target.split("#", 1)[0]  # drop anchor fragment
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not target.endswith(".md"):
                    continue
                if not (base / target).resolve().is_file():
                    violations.append(
                        f"{rel}:{line_no}: pointer to '{target}' does not resolve"
                    )
    return violations


def _parse_makefile_targets(makefile: Path) -> dict[str, tuple[list[str], list[str]]]:
    """Parse `target: deps` rules and tab-indented recipe lines from Makefile."""
    targets: dict[str, tuple[list[str], list[str]]] = {}
    current: str | None = None
    for raw in makefile.read_text(encoding="utf-8").splitlines():
        if raw.startswith("\t") and current is not None:
            deps, commands = targets[current]
            commands.append(raw.strip())
            targets[current] = (deps, commands)
            continue

        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:(.*)$", raw)
        if not m:
            current = None
            continue

        name = m.group(1)
        if name.startswith("."):
            current = None
            continue
        deps = [d for d in m.group(2).strip().split() if d and not d.startswith("#")]
        targets[name] = (deps, [])
        current = name
    return targets


def _target_capabilities(targets: dict[str, tuple[list[str], list[str]]]) -> dict[str, set[str]]:
    """Resolve transitive capabilities implemented by each make target."""
    cache: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def direct(commands: list[str]) -> set[str]:
        text = "\n".join(commands).lower()
        out: set[str] = set()
        if "check_translations.py" in text:
            out.add("translation_drift")
        if "validate_docs.py" in text:
            out.add("docs_prose")
        if "validate_hacs.py" in text:
            out.add("hacs_preflight")
        return out

    def resolve(name: str) -> set[str]:
        if name in cache:
            return cache[name]
        if name in visiting:
            return set()
        visiting.add(name)
        deps, commands = targets.get(name, ([], []))
        out = direct(commands)
        for dep in deps:
            if dep in targets:
                out |= resolve(dep)
        visiting.remove(name)
        cache[name] = out
        return out

    for target in targets:
        resolve(target)
    return cache


def scan_make_claims(files: list[Path]) -> list[str]:
    """Fail when markdown `make <target>` capability claims contradict Makefile."""
    if not MAKEFILE.is_file():
        return [f"Makefile not found at expected path: {MAKEFILE}"]

    targets = _parse_makefile_targets(MAKEFILE)
    capabilities = _target_capabilities(targets)
    capability_patterns: tuple[tuple[str, re.Pattern[str], str], ...] = (
        (
            "translation_drift",
            re.compile(
                r"translation drift|translation parity|check_translations|"
                r"strings\.json\s*/\s*translations/en\.json",
                re.IGNORECASE,
            ),
            "translation drift check",
        ),
        (
            "docs_prose",
            re.compile(r"docs prose|prose linter|validate_docs", re.IGNORECASE),
            "docs prose check",
        ),
        ("hacs_preflight", re.compile(r"hacs preflight|validate_hacs", re.IGNORECASE), "HACS preflight"),
    )

    violations: list[str] = []
    for path in files:
        rel = path.relative_to(REPO)
        if rel.as_posix() in {"CHANGELOG.md", "docs/HISTORY.md"}:
            # Historical files may intentionally describe past Makefile behaviour.
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            matches = list(MAKE_TARGET_REF.finditer(line))
            if not matches:
                continue

            for i, match in enumerate(matches):
                target = (match.group(1) or match.group(2)).lower()
                segment_end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
                segment = line[match.start() : segment_end]
                for cap_key, cap_pat, cap_label in capability_patterns:
                    if cap_pat.search(segment) and cap_key not in capabilities.get(target, set()):
                        violations.append(
                            f"{rel}:{line_no}: claims `make {target}` includes {cap_label}, "
                            f"but Makefile wiring does not"
                        )
    return violations


def collect_files() -> list[Path]:
    """Collect every markdown file in the repo, skipping excluded directories."""
    files: list[Path] = []
    for path in REPO.rglob("*.md"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(REPO).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue
        files.append(path)
    return sorted(files)


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
    files = collect_files()
    for path in files:
        rel = path.relative_to(REPO)
        violations = scan_forbidden(path)
        if path.name == "HISTORY.md":
            violations.extend(scan_history_format(path))
        violations.sort()
        for line_no, col, msg in violations:
            print(f"{rel}:{line_no}:{col}: {msg}", file=sys.stderr)
            rc = 1

    for msg in scan_shared_blocks(files):
        print(msg, file=sys.stderr)
        rc = 1
    for msg in scan_pointers():
        print(msg, file=sys.stderr)
        rc = 1
    for msg in scan_make_claims(files):
        print(msg, file=sys.stderr)
        rc = 1

    if rc == 0:
        print("✅ Docs validation passed.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
