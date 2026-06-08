#!/usr/bin/env python3
"""Seed the GitHub Issues backlog for unifi_alerts.

This is the one-time migration tool that moves the v1.8 / v1.9 / v2.0 backlog
out of `docs/TODO.md` and into GitHub Issues, where work is tracked from now
on. It is safe to re-run: labels, milestones, and issues that already exist are
skipped (issues are matched by exact title), so the script doubles as a way to
top up the backlog when new items are added to the ISSUES list below.

Requires the `gh` CLI, authenticated against this repository (run from a clone
of the repo, or pass --repo OWNER/NAME).

Usage:
    python3 scripts/seed_issues.py             # create labels, milestones, issues
    python3 scripts/seed_issues.py --dry-run   # print the plan, change nothing
    python3 scripts/seed_issues.py --repo PHeonix25/unifi_alerts
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Taxonomy
# --------------------------------------------------------------------------- #

# Labels referenced by the issues below. The category labels mirror those in
# `.github/release.yml` so auto-generated release notes group correctly; the
# `size:` / `priority:` / `v2.0-gate` labels are work-tracking metadata.
LABELS: list[tuple[str, str, str]] = [
    # category (kept in lockstep with .github/release.yml and setup-labels.sh)
    ("security", "b60205", "Security-related changes (vulnerabilities, hardening)"),
    ("feat", "a2eeef", "New feature or capability"),
    ("enhancement", "a2eeef", "New feature or capability (GitHub default alias)"),
    ("fix", "d73a4a", "Bug fix or correctness change"),
    ("bug", "d73a4a", "Confirmed defect (GitHub default alias)"),
    ("tests", "bfdadc", "Test changes (additions, refactors, fixtures)"),
    ("ci", "ededed", "CI, build, tooling, or release-pipeline changes"),
    ("documentation", "0075ca", "Documentation and process changes"),
    ("github-actions", "000000", "GitHub Actions workflow or pinned-action changes"),
    ("dependencies", "0366d6", "Dependency bumps and pinning"),
    # work-tracking metadata
    ("size: S", "c2e0c6", "Small: a single-sitting change"),
    ("size: M", "fef2c0", "Medium: a focused piece of work"),
    ("size: L", "f9d0c4", "Large: may need decomposition"),
    ("priority: high", "d93f0b", "Do first within its milestone"),
    ("priority: medium", "fbca04", "Standard priority"),
    ("priority: low", "0e8a16", "Guardrail or nice-to-have"),
    ("v2.0-gate", "5319e7", "Prerequisite for the HACS default catalogue submission"),
]

# Milestones. The base version matches the next planned release per CLAUDE.md.
MILESTONES: list[tuple[str, str]] = [
    (
        "v1.8.0",
        "Trust and Hardening: correctness, privacy, security, and "
        "onboarding-confidence work on the road to v2.0.",
    ),
    (
        "v1.9.0",
        "Localisation and Scale: i18n readiness, efficiency under load, "
        "and capability work on the road to v2.0.",
    ),
    (
        "v2.0.0",
        "HACS default catalogue submission. Gated on the v2.0-gate issues "
        "carried in the v1.8.0 and v1.9.0 milestones.",
    ),
]


@dataclass
class Issue:
    """A single backlog item destined for GitHub Issues."""

    title: str
    milestone: str
    labels: list[str]
    body: str = field(default="")


# --------------------------------------------------------------------------- #
# Backlog (source of truth, ordered by milestone then priority)
# --------------------------------------------------------------------------- #

ISSUES: list[Issue] = [
    # ----- v1.8.0: High value ------------------------------------------------
    Issue(
        title="Stop persisting raw alert payloads to disk",
        milestone="v1.8.0",
        labels=["security", "size: S", "priority: high", "v2.0-gate"],
        body=(
            "`UniFiAlert.to_dict()` (`models.py`) does `asdict(self)`, which "
            "serialises the entire `raw` payload (client MACs, IPs, hostnames) "
            "into `.storage` via the coordinator's `Store`. That is the one "
            "place those fields are not already redacted, and a non-JSON value "
            "in `raw` can break `Store.async_save`.\n\n"
            "**Approach:** persist an explicit scalar field list "
            "(`message`, `received_at`, `key`, `device_name`, `site`, "
            "`severity`); default `raw={}` in `from_dict`.\n\n"
            "**Acceptance**\n"
            "- [ ] `to_dict()` no longer serialises `raw`\n"
            "- [ ] Restore path still rebuilds `last_alert` from the scalar fields\n"
            "- [ ] Test asserts a non-JSON value in `raw` cannot break persistence\n"
            "- [ ] CHANGELOG `[Unreleased]` updated (privacy)"
        ),
    ),
    Issue(
        title="Fix stale alert_received replay on reload",
        milestone="v1.8.0",
        labels=["fix", "size: S", "priority: high"],
        body=(
            "`UniFiAlertEventEntity._last_seen_count` resets to 0 in `__init__` "
            "(`event.py`), so the first coordinator update after any options "
            "save (which triggers a full reload) sees a restored non-zero "
            "`alert_count` and re-fires `alert_received` for a stale alert into "
            "users' automations.\n\n"
            "**Approach:** seed `_last_seen_count` from the restored "
            "`state.alert_count` in `async_added_to_hass`, before the first "
            "`_handle_coordinator_update`.\n\n"
            "**Acceptance**\n"
            "- [ ] Reload after an options change does not fire a fresh event\n"
            "- [ ] A genuine new push still fires exactly once\n"
            "- [ ] Regression test covers the reload sequence"
        ),
    ),
    Issue(
        title="Add a per-category webhook health signal",
        milestone="v1.8.0",
        labels=["feat", "size: M", "priority: high"],
        body=(
            "After pasting webhook URLs into Alarm Manager, a user has no way "
            "to know setup worked until a real alert fires. This is the biggest "
            "source of 'it does not work' reports for a push integration.\n\n"
            "**Approach:** expose a per-category 'last webhook received' "
            "timestamp (attribute and diagnostics) plus a healthy/stale "
            "indicator. The webhook handler already timestamps receipt.\n\n"
            "**Acceptance**\n"
            "- [ ] Last-received timestamp surfaced per category\n"
            "- [ ] A never-received / stale category is visibly distinguishable\n"
            "- [ ] Documented in the README setup section\n"
            "- [ ] CHANGELOG `[Unreleased]` updated"
        ),
    ),
    Issue(
        title="Coalesce watermark persistence and surface failures",
        milestone="v1.8.0",
        labels=["fix", "size: S", "priority: high"],
        body=(
            "The per-push fire-and-forget `async_save` (`coordinator.py`) has a "
            "lost-update hazard under bursts and no error path, so a failed "
            "persist dies silently.\n\n"
            "**Approach:** route writes through `Store.async_delay_save`, and "
            "run background tasks through a shared helper whose done-callback "
            "logs any non-`CancelledError` exception.\n\n"
            "**Acceptance**\n"
            "- [ ] Bursted pushes coalesce to a single durable write\n"
            "- [ ] A persist exception is logged, not swallowed\n"
            "- [ ] Test covers the save-raises path"
        ),
    ),
    # ----- v1.8.0: Medium value ---------------------------------------------
    Issue(
        title="Consolidate alert classification into a single seam",
        milestone="v1.8.0",
        labels=["size: M", "priority: medium"],
        body=(
            "Two parallel category resolvers exist: legacy prefix-match in "
            "`unifi_client._classify`, and exact-key plus enum fallback in "
            "`models.from_system_log_event`, each with its own unknown-key "
            "warning path. The process-global `_unknown_system_log_keys` set is "
            "shared mutable state.\n\n"
            "**Approach:** collapse the taxonomy into one location so both "
            "paths share resolution and warning dedup; remove the module-global "
            "set in favour of instance/coordinator-scoped state.\n\n"
            "**Acceptance**\n"
            "- [ ] One classification entry point\n"
            "- [ ] No process-global mutable warning set\n"
            "- [ ] Existing classification tests still pass"
        ),
    ),
    Issue(
        title="Extract controller auth into a dedicated seam",
        milestone="v1.8.0",
        labels=["size: L", "priority: medium"],
        body=(
            "In `unifi_client.py`, auth-method autodetect, session state, "
            "login, key verification, and header construction are interleaved "
            "with transport, version probing, pagination, and parsing in one "
            "class.\n\n"
            "**Approach:** pull the auth concern into its own strategy so a "
            "future third auth method or token refresh slots in cleanly and "
            "auth becomes unit-testable in isolation. Large item; decompose if "
            "needed.\n\n"
            "**Acceptance**\n"
            "- [ ] Auth logic lives behind a single seam\n"
            "- [ ] Auth is unit-testable without the full client\n"
            "- [ ] Coordinator re-auth coupling still works"
        ),
    ),
    Issue(
        title="Add an end-to-end secret-rotation test",
        milestone="v1.8.0",
        labels=["tests", "size: M", "priority: medium"],
        body=(
            "Rotation is unit-tested in pieces but nothing proves the full "
            "cycle, and rotation is a security boundary.\n\n"
            "**Approach:** in `tests/integration/`, drive options finish -> "
            "entry update -> reload -> webhook re-register; assert the old "
            "token returns 401 and the new token returns 200 after reload.\n\n"
            "**Acceptance**\n"
            "- [ ] One integration test covers the whole rotation cycle\n"
            "- [ ] Old token rejected, new token accepted post-reload"
        ),
    ),
    Issue(
        title="Catch InvalidAuthError on the re-auth retry",
        milestone="v1.8.0",
        labels=["fix", "size: S", "priority: medium"],
        body=(
            "After a 401 triggers re-authentication, the retried fetch "
            "(`coordinator.py`) only catches `CannotConnectError`; a second "
            "`InvalidAuthError` escapes `_async_update_data` as a generic error "
            "instead of raising `ConfigEntryAuthFailed` to trigger HA "
            "re-auth.\n\n"
            "**Acceptance**\n"
            "- [ ] Retry that still 401s raises `ConfigEntryAuthFailed`\n"
            "- [ ] Coordinator test covers 're-auth succeeds, retry still 401'"
        ),
    ),
    Issue(
        title="Harden _render_message_raw substitution",
        milestone="v1.8.0",
        labels=["security", "size: S", "priority: medium"],
        body=(
            "Sequential `str.replace` over controller-supplied `parameters` "
            "(`models.py`) is order-dependent and lets a parameter value that "
            "itself contains a `{TOKEN}` be re-substituted.\n\n"
            "**Approach:** switch to single-pass substitution; add tests for "
            "embedded-token, overlapping-prefix (`{IP}` vs `{IP_DST}`), and "
            "non-string parameter values.\n\n"
            "**Acceptance**\n"
            "- [ ] Substitution is single-pass and order-independent\n"
            "- [ ] Tests cover the three hostile-input cases"
        ),
    ),
    Issue(
        title="Define the empty or malformed webhook contract",
        milestone="v1.8.0",
        labels=["fix", "size: S", "priority: medium"],
        body=(
            "An authenticated POST with an empty or unrecognisable body "
            "currently flips the binary sensor to 'Problem' and fires an event "
            "(`webhook_handler.py`, `coordinator.push_alert`).\n\n"
            "**Approach (decide during implementation):** either skip "
            "`push_callback` when no recognisable fields are present, or keep "
            "the behaviour. Either way, lock the chosen contract in with a "
            "test.\n\n"
            "**Acceptance**\n"
            "- [ ] Contract decided and documented in the code\n"
            "- [ ] Test asserts the behaviour for `{}` and a no-field body"
        ),
    ),
    Issue(
        title="Clarify retention and data handling",
        milestone="v1.8.0",
        labels=["documentation", "security", "size: M", "priority: medium", "v2.0-gate"],
        body=(
            "`clear()` advances the watermark but leaves `last_alert` (message, "
            "device name) in state and on disk, so a 'cleared' category still "
            "retains identifying content. There is no user-facing statement of "
            "what is stored or for how long.\n\n"
            "**Approach:** clear `last_alert` on `clear()` (or document that "
            "clearing is acknowledgement, not deletion); add a README 'Data "
            "handled and retention' section covering what is stored, where, and "
            "how to purge it.\n\n"
            "**Acceptance**\n"
            "- [ ] Clear semantics defined and implemented\n"
            "- [ ] README documents stored fields, location, and purge path"
        ),
    ),
    Issue(
        title="Complete the Alarm Manager onboarding docs",
        milestone="v1.8.0",
        labels=["documentation", "size: S", "priority: medium", "v2.0-gate"],
        body=(
            "The hardest, most error-prone half of setup (configuring Alarm "
            "Manager) has the thinnest docs, and the 'copy URLs before clicking "
            "Submit' ordering is a footgun.\n\n"
            "**Approach:** add a per-category trigger-mapping table and "
            "annotated screenshots; remove the footgun by re-showing the URLs "
            "after the entry is created (the options flow already supports "
            "this).\n\n"
            "**Acceptance**\n"
            "- [ ] Per-category trigger table in the README\n"
            "- [ ] URLs viewable after entry creation, not only before Submit"
        ),
    ),
    # ----- v1.8.0: Low value / guardrails -----------------------------------
    Issue(
        title="Disable redirect-following on authenticated outbound calls",
        milestone="v1.8.0",
        labels=["security", "size: S", "priority: low"],
        body=(
            "Authenticated requests in `unifi_client.py` use aiohttp's default "
            "`allow_redirects=True`, so the `X-API-Key` header and session "
            "cookie can ride a controller-issued redirect to another host.\n\n"
            "**Approach:** pass `allow_redirects=False` and treat a 3xx as an "
            "error on the authenticated call sites.\n\n"
            "**Acceptance**\n"
            "- [ ] Authed calls do not follow redirects\n"
            "- [ ] A 3xx is surfaced as an error"
        ),
    ),
    Issue(
        title="Length-validate inbound key, severity, device_name",
        milestone="v1.8.0",
        labels=["security", "size: S", "priority: low"],
        body=(
            "`models.from_webhook_payload` truncates `message` but passes "
            "`key`, `severity`, and `device_name` through untruncated, so a "
            "token-bearing caller can push unbounded values into state and "
            "logs.\n\n"
            "**Acceptance**\n"
            "- [ ] All three fields truncated like `message`\n"
            "- [ ] Test covers oversized inputs"
        ),
    ),
    Issue(
        title="Document the diagnostics content exclusion",
        milestone="v1.8.0",
        labels=["documentation", "size: S", "priority: low"],
        body=(
            "Diagnostics deliberately excludes per-category alert content "
            "(`message`, `device_name`, `raw`). Add a comment in "
            "`diagnostics.py` recording that this must stay excluded; if alert "
            "detail is ever added, route it through a field redactor.\n\n"
            "**Acceptance**\n"
            "- [ ] Guardrail comment in place"
        ),
    ),
    Issue(
        title="Optional host guard on the controller URL",
        milestone="v1.8.0",
        labels=["security", "size: S", "priority: low"],
        body=(
            "URL validation in `config_flow.py` is scheme-only. Optionally "
            "reject loopback and link-local hosts, or document that the URL is "
            "fully trusted under the local-admin model. Low-priority "
            "guardrail.\n\n"
            "**Acceptance**\n"
            "- [ ] Decision made and either guard added or trust documented"
        ),
    ),
    Issue(
        title="Reconcile docs/REPO_LAYOUT.md with the file tree",
        milestone="v1.8.0",
        labels=["documentation", "size: S", "priority: low"],
        body=(
            "`docs/REPO_LAYOUT.md` (the per-file source of truth) omits "
            "`services.py`, `services.yaml`, `scripts/run_lint.py`, and "
            "`scripts/run_typecheck.py`.\n\n"
            "**Approach:** add the missing rows; optionally add a "
            "`scripts/validate_docs.py` check that every `*.py` under "
            "`custom_components/` and `scripts/` appears at least once.\n\n"
            "**Acceptance**\n"
            "- [ ] All four files documented\n"
            "- [ ] Optional drift check wired into validate_docs"
        ),
    ),
    Issue(
        title="Fix the Actions version comments in copilot-setup-steps.yml",
        milestone="v1.8.0",
        labels=["ci", "github-actions", "size: S", "priority: low"],
        body=(
            "The pinned SHAs in `.github/workflows/copilot-setup-steps.yml` "
            "carry `# v4` and `# v5` comments but resolve to `# v6`, breaking "
            "the human-readable pin contract Dependabot review relies on.\n\n"
            "**Acceptance**\n"
            "- [ ] Comments match the resolved tags for the pinned SHAs"
        ),
    ),
    # ----- v1.9.0: High value -----------------------------------------------
    Issue(
        title="Make category labels translatable",
        milestone="v1.9.0",
        labels=["feat", "size: M", "priority: high"],
        body=(
            "Entity name templates already use `_attr_translation_key`, but the "
            "`{category}` placeholder is filled from the English-only "
            "`CATEGORY_LABELS` dict (`const.py`), leaving entity names "
            "half-translated for non-English Home Assistant.\n\n"
            "**Approach:** give each category its own `translation_key` so the "
            "label resolves through the translation layer.\n\n"
            "**Acceptance**\n"
            "- [ ] Category names resolve via translations\n"
            "- [ ] strings.json / translations drift check passes"
        ),
    ),
    Issue(
        title="Make the system-log key map self-healing",
        milestone="v1.9.0",
        labels=["feat", "size: S", "priority: high"],
        body=(
            "`SYSTEM_LOG_KEY_TO_CATEGORY` is intentionally incomplete and the "
            "fallback enum keeps unmapped events roughly categorised, but there "
            "is no user-visible signal when a key is unclassified, so the map "
            "only improves via users who dig through DEBUG logs.\n\n"
            "**Approach:** add an 'uncategorised' counter or a diagnostics "
            "field listing recently seen unmapped keys so every install "
            "passively surfaces the keys to add.\n\n"
            "**Acceptance**\n"
            "- [ ] Unclassified keys are visible without DEBUG logging\n"
            "- [ ] Documented how to report them"
        ),
    ),
    # ----- v1.9.0: Medium value ---------------------------------------------
    Issue(
        title="Add severity filtering for noisy categories",
        milestone="v1.9.0",
        labels=["feat", "size: M", "priority: medium"],
        body=(
            "Noisy categories are blunt on/off toggles today. A min-severity "
            "option (or a consistently surfaced severity attribute automations "
            "can key off) makes them usable instead of muted on day one.\n\n"
            "**Acceptance**\n"
            "- [ ] Severity is filterable at the integration level\n"
            "- [ ] Documented; CHANGELOG `[Unreleased]` updated"
        ),
    ),
    Issue(
        title="Clamp the watermark fetch window",
        milestone="v1.9.0",
        labels=["fix", "size: M", "priority: medium"],
        body=(
            "`since = min(watermarks)` (`coordinator.py`) lets the fetch window "
            "grow without bound when one category is rarely cleared, "
            "re-paginating the full range every poll and risking recent alarms "
            "being pushed past `MAX_SYSTEM_LOG_PAGES`.\n\n"
            "**Approach:** clamp to `max(min(watermarks), now - lookback_cap)` "
            "and log when the page cap is hit.\n\n"
            "**Acceptance**\n"
            "- [ ] Fetch window is bounded under skewed clear-rates\n"
            "- [ ] Page-cap hit is logged"
        ),
    ),
    Issue(
        title="Add probe backoff for the system-log endpoint",
        milestone="v1.9.0",
        labels=["fix", "size: S", "priority: medium"],
        body=(
            "A persistent non-404 failure makes "
            "`unifi_client.probe_system_log_endpoint` re-probe on every poll "
            "forever, doubling the request rate against a misbehaving "
            "endpoint.\n\n"
            "**Approach:** add a transient-failure counter that caches 'legacy' "
            "after a threshold, with periodic re-probe.\n\n"
            "**Acceptance**\n"
            "- [ ] No permanent re-probe loop on persistent failure\n"
            "- [ ] Capable controllers still detected"
        ),
    ),
    Issue(
        title="Localise the remaining inline strings",
        milestone="v1.9.0",
        labels=["enhancement", "size: S", "priority: medium"],
        body=(
            "`'No alerts yet'` (`sensor.py`) is returned in code with no "
            "translation key, and some config descriptions carry meaning via "
            "emoji and em-dashes.\n\n"
            "**Approach:** move the state string to a translation key; replace "
            "emoji/em-dash-carried meaning with plain-text prefixes so meaning "
            "survives translation and screen readers.\n\n"
            "**Acceptance**\n"
            "- [ ] No user-facing English string hard-coded in platform files\n"
            "- [ ] Meaning does not depend on an emoji glyph"
        ),
    ),
    Issue(
        title="Clarify the multi-controller setup in the docs",
        milestone="v1.9.0",
        labels=["documentation", "size: S", "priority: medium"],
        body=(
            "Multi-entry is supported and a `site` field exists, but the "
            "multi-controller / multi-site story is undocumented and the `site` "
            "field's role is unclear.\n\n"
            "**Approach:** document the pattern and clarify the field. Defer "
            "full per-category site config (parked, low value).\n\n"
            "**Acceptance**\n"
            "- [ ] README explains multi-controller setup and the site field"
        ),
    ),
    # ----- v1.9.0: Low value ------------------------------------------------
    Issue(
        title="Add unicode and large-volume round-trip tests",
        milestone="v1.9.0",
        labels=["tests", "size: S", "priority: low"],
        body=(
            "Assert non-ASCII alert text (emoji, CJK, RTL) and 300-character "
            "strings survive parse -> store -> restore and 255-character "
            "truncation, and that a roughly 500-alert batch keeps counts and "
            "watermark filtering deterministic.\n\n"
            "**Acceptance**\n"
            "- [ ] Unicode round-trip test added\n"
            "- [ ] Large-batch determinism test added"
        ),
    ),
    Issue(
        title="Add coverage measurement in CI",
        milestone="v1.9.0",
        labels=["ci", "size: S", "priority: low"],
        body=(
            "There is no `--cov` reporting, so thin-test regressions are "
            "invisible until they bite. Add coverage reporting (not "
            "necessarily a gate).\n\n"
            "**Acceptance**\n"
            "- [ ] Coverage reported in the test job"
        ),
    ),
    Issue(
        title="Pin dev dependencies for reproducible CI",
        milestone="v1.9.0",
        labels=["ci", "dependencies", "size: M", "priority: low"],
        body=(
            "`requirements-dev.txt` floats `homeassistant`, `ruff`, `mypy`, and "
            "`pytest`, making CI and local `make check` non-reproducible.\n\n"
            "**Approach (maintainer call):** decide whether a hashed "
            "constraints file is warranted without enabling the pip Dependabot "
            "ecosystem.\n\n"
            "**Acceptance**\n"
            "- [ ] Decision recorded; pinning added if adopted"
        ),
    ),
    # ----- v2.0.0 -----------------------------------------------------------
    Issue(
        title="Submit the integration to the HACS default catalogue",
        milestone="v2.0.0",
        labels=["documentation", "size: M", "priority: high"],
        body=(
            "Umbrella issue for the HACS default submission. Gated on all "
            "`v2.0-gate` issues (raw-payload persistence, retention statement, "
            "Alarm Manager onboarding docs) and the localisation-maturity work "
            "being complete.\n\n"
            "**Acceptance**\n"
            "- [ ] All `v2.0-gate` issues closed\n"
            "- [ ] PR opened against https://github.com/hacs/default"
        ),
    ),
]


# --------------------------------------------------------------------------- #
# gh plumbing
# --------------------------------------------------------------------------- #


def run_gh(args: list[str], *, dry_run: bool = False, capture: bool = False) -> str:
    """Run a `gh` command. Returns stdout when capture=True, else ''."""
    printable = "gh " + " ".join(args)
    if dry_run and not capture:
        print(f"  would run: {printable}")
        return ""
    result = subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout if capture else ""


def detect_repo() -> str:
    """Return OWNER/NAME for the current repo via gh."""
    out = run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], capture=True)
    return out.strip()


def existing_labels(repo: str) -> set[str]:
    out = run_gh(["label", "list", "--repo", repo, "--limit", "300", "--json", "name"], capture=True)
    return {item["name"] for item in json.loads(out or "[]")}


def existing_milestones(repo: str) -> set[str]:
    out = run_gh(["api", f"repos/{repo}/milestones", "--paginate", "--jq", ".[].title"], capture=True)
    return {line for line in out.splitlines() if line}


def existing_issue_titles(repo: str) -> set[str]:
    out = run_gh(
        ["issue", "list", "--repo", repo, "--state", "all", "--limit", "400", "--json", "title"],
        capture=True,
    )
    return {item["title"] for item in json.loads(out or "[]")}


def ensure_labels(repo: str, present: set[str], dry_run: bool) -> None:
    print("Labels:")
    for name, color, desc in LABELS:
        if name in present:
            print(f"  skip  {name}")
            continue
        run_gh(
            ["label", "create", name, "--repo", repo, "--color", color, "--description", desc],
            dry_run=dry_run,
        )
        print(f"  ok    {name}")


def ensure_milestones(repo: str, present: set[str], dry_run: bool) -> None:
    print("Milestones:")
    for title, desc in MILESTONES:
        if title in present:
            print(f"  skip  {title}")
            continue
        run_gh(
            ["api", f"repos/{repo}/milestones", "-f", f"title={title}", "-f", f"description={desc}"],
            dry_run=dry_run,
        )
        print(f"  ok    {title}")


def ensure_issues(repo: str, present: set[str], dry_run: bool) -> None:
    print("Issues:")
    for issue in ISSUES:
        if issue.title in present:
            print(f"  skip  {issue.title}")
            continue
        args = [
            "issue", "create", "--repo", repo,
            "--title", issue.title,
            "--body", issue.body,
            "--milestone", issue.milestone,
        ]
        for label in issue.labels:
            args += ["--label", label]
        run_gh(args, dry_run=dry_run)
        print(f"  ok    [{issue.milestone}] {issue.title}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="OWNER/NAME (default: detect via gh)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parsed = parser.parse_args()

    if subprocess.run(["gh", "--version"], capture_output=True).returncode != 0:
        print("error: the `gh` CLI is required and must be authenticated.", file=sys.stderr)
        return 1

    repo = parsed.repo or detect_repo()
    print(f"Repository: {repo}{'  (dry run)' if parsed.dry_run else ''}\n")

    ensure_labels(repo, existing_labels(repo), parsed.dry_run)
    print()
    ensure_milestones(repo, existing_milestones(repo), parsed.dry_run)
    print()
    ensure_issues(repo, existing_issue_titles(repo), parsed.dry_run)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
