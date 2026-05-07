#!/usr/bin/env python3
"""Bump the integration version and prep a claude/bump-* branch.

Three modes, matching the release workflow in CLAUDE.md:

    --pre         within current cycle:  1.5.0-pre1 -> 1.5.0-pre2
    --stable      promote to stable:     1.5.0-pre3 -> 1.5.0
    --next-cycle  start next minor:      1.5.0      -> 1.6.0-pre1

For all modes:

    1. Verifies the working tree is clean.
    2. Fetches origin, checks out dev, pulls.
    3. Creates `claude/bump-<new-version>` from the dev tip.
    4. Updates `version` in custom_components/unifi_alerts/manifest.json.
    5. For --stable: also rewrites CHANGELOG.md - renames the
       [Unreleased] heading to [X.Y.Z] - YYYY-MM-DD, inserts a fresh
       empty [Unreleased] above it, and adds the [X.Y.Z] link reference.
    6. Stages the changes (does not commit).
    7. Prints the merge list since the previous tag (for the
       docs/HISTORY.md block) and the post-merge tag command.

Usage:
    python3 scripts/bump_version.py --pre
    python3 scripts/bump_version.py --stable
    python3 scripts/bump_version.py --next-cycle
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "unifi_alerts" / "manifest.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-pre(\d+))?$")


def run(*args: str, capture: bool = False, check: bool = True) -> str:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def fail(msg: str) -> NoReturn:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_version() -> str:
    data = json.loads(MANIFEST.read_text())
    return str(data["version"])


def write_version(new_version: str) -> None:
    # Python preserves dict insertion order, so json.loads + json.dumps keeps
    # the manifest key order. hassfest enforces: domain, name, then alphabetical.
    data = json.loads(MANIFEST.read_text())
    data["version"] = new_version
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n")


def parse_version(v: str) -> tuple[int, int, int, int | None]:
    m = VERSION_RE.match(v)
    if not m:
        fail(f"unrecognised version format: {v!r}")
    major, minor, patch = int(m[1]), int(m[2]), int(m[3])
    pre = int(m[4]) if m[4] else None
    return major, minor, patch, pre


def bump_pre(current: str) -> str:
    major, minor, patch, pre = parse_version(current)
    if pre is None:
        fail(
            f"--pre requires a -preN version, but manifest is at {current!r}. "
            f"Did you mean --next-cycle?"
        )
    return f"{major}.{minor}.{patch}-pre{pre + 1}"


def bump_stable(current: str) -> str:
    major, minor, patch, pre = parse_version(current)
    if pre is None:
        fail(f"--stable requires a -preN version, but manifest is at {current!r}.")
    return f"{major}.{minor}.{patch}"


def bump_next_cycle(current: str) -> str:
    major, minor, _patch, pre = parse_version(current)
    if pre is not None:
        fail(
            f"--next-cycle requires a stable version, but manifest is at "
            f"{current!r}. Did you mean --pre?"
        )
    return f"{major}.{minor + 1}.0-pre1"


def assert_clean_tree() -> None:
    out = run("git", "status", "--porcelain", capture=True)
    if out:
        fail("working tree is not clean. Commit or stash changes first.\n" + out)


def checkout_fresh_dev() -> None:
    print("Fetching origin/dev...")
    run("git", "fetch", "origin", "dev")
    branches = run("git", "branch", "--list", "dev", capture=True)
    if not branches:
        run("git", "checkout", "-b", "dev", "origin/dev")
    else:
        run("git", "checkout", "dev")
        run("git", "pull", "origin", "dev")


def create_bump_branch(new_version: str) -> str:
    branch = f"claude/bump-{new_version}"
    existing = run("git", "branch", "--list", branch, capture=True)
    if existing:
        fail(
            f"branch {branch!r} already exists locally. Delete it with "
            f"`git branch -D {branch}` if it is stale."
        )
    print(f"Creating branch {branch}...")
    run("git", "checkout", "-b", branch)
    return branch


def previous_tag() -> str | None:
    try:
        return run(
            "git",
            "describe",
            "--tags",
            "--abbrev=0",
            "--match",
            "v*",
            capture=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None


def merges_since(tag: str) -> str:
    return run("git", "log", f"{tag}..HEAD", "--merges", "--oneline", capture=True)


def update_changelog_for_stable(new_version: str) -> None:
    today = date.today().isoformat()
    text = CHANGELOG.read_text()

    if "## [Unreleased]" not in text:
        fail("CHANGELOG.md has no [Unreleased] heading to promote.")

    text = text.replace(
        "## [Unreleased]",
        f"## [Unreleased]\n\n## [{new_version}] - {today}",
        1,
    )

    # Update the [Unreleased] compare link to use the new stable as the base,
    # and insert a [X.Y.Z]: .../releases/tag/vX.Y.Z entry above the prior one.
    unreleased_link_re = re.compile(
        r"^\[Unreleased\]: (?P<base>.+/compare/v)(?P<prev>[\d.]+(?:-pre\d+)?)\.\.\.HEAD$",
        re.MULTILINE,
    )
    match = unreleased_link_re.search(text)
    if not match:
        fail("CHANGELOG.md has no [Unreleased] compare link to update.")
    prev_version = match.group("prev")
    text = unreleased_link_re.sub(
        f"[Unreleased]: {match.group('base')}{new_version}...HEAD",
        text,
        count=1,
    )

    prev_link_re = re.compile(
        rf"^\[{re.escape(prev_version)}\]: (?P<url>.+/releases/tag/v{re.escape(prev_version)})$",
        re.MULTILINE,
    )
    prev_link = prev_link_re.search(text)
    if not prev_link:
        fail(f"CHANGELOG.md has no link reference for previous version [{prev_version}].")
    new_link_url = prev_link.group("url").replace(
        f"v{prev_version}", f"v{new_version}"
    )
    text = prev_link_re.sub(
        f"[{new_version}]: {new_link_url}\n[{prev_version}]: {prev_link.group('url')}",
        text,
        count=1,
    )

    CHANGELOG.write_text(text)
    print(f"Updated {CHANGELOG.name}: [Unreleased] -> [{new_version}] - {today}")


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Bump the integration version and prep a claude/bump-* branch."
        )
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pre", action="store_true", help="bump preN counter")
    g.add_argument(
        "--stable", action="store_true", help="promote pre-release to stable"
    )
    g.add_argument(
        "--next-cycle",
        action="store_true",
        help="start next minor cycle (X.Y.Z -> X.(Y+1).0-pre1)",
    )
    args = p.parse_args()

    assert_clean_tree()

    current = read_version()
    if args.pre:
        new_version = bump_pre(current)
    elif args.stable:
        new_version = bump_stable(current)
    else:
        new_version = bump_next_cycle(current)

    print(f"Current version: {current}")
    print(f"New version:     {new_version}")
    print()

    checkout_fresh_dev()
    branch = create_bump_branch(new_version)

    write_version(new_version)
    print(f"Updated {MANIFEST.relative_to(REPO_ROOT)}")

    files_to_stage: list[str] = [str(MANIFEST.relative_to(REPO_ROOT))]
    if args.stable:
        update_changelog_for_stable(new_version)
        files_to_stage.append(str(CHANGELOG.relative_to(REPO_ROOT)))

    run("git", "add", *files_to_stage)
    print(f"Staged: {', '.join(files_to_stage)}")
    print()
    print(f"On branch: {branch}")
    print()

    prev = previous_tag()
    if prev:
        print(f"Most recent tag: {prev}")
        merges = merges_since(prev)
        if merges:
            print(
                f"Merges since {prev} (write these into docs/HISTORY.md as a "
                f"single ## {date.today().isoformat()} block):"
            )
            print()
            for line in merges.splitlines():
                print(f"  {line}")
            print()
        else:
            print(f"No merges since {prev}.")
            print()
    else:
        print("No previous tag found; skipping merges-since list.")
        print()

    print("Next steps:")
    print(
        f"  1. Write the docs/HISTORY.md block (## {date.today().isoformat()}) "
        f"summarising the merges above."
    )
    print("  2. Update docs/ROADMAP.md if this tag advances a release section.")
    print("  3. Run `make check`.")
    print("  4. Commit and push, then open a PR targeting dev.")
    print("  5. After the PR merges, tag with:")
    print("     git checkout dev && git pull origin dev")
    print(f"     git tag v{new_version} && git push origin v{new_version}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
