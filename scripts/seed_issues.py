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
    Issue(
        title="Adopt one test-layout convention across the unit suite",
        milestone="v1.8.0",
        labels=["tests", "size: M", "priority: low"],
        body=(
            "Unit test files mix class-grouped (`class Test*`) and flat "
            "function layouts, and the inconsistency appears even within a "
            "single directory. In `tests/unit/config_flow/`: `test_options.py` "
            "uses 4 classes, `test_reauth.py` uses 1, and `test_setup.py` is "
            "fully flat. Most unit files are class-grouped "
            "(`test_coordinator.py` 19, `test_unifi_client.py` 12, "
            "`test_entities.py` 11, `test_webhook_handler.py` 10, "
            "`test_models.py`/`test_services.py` 7 each, `test_init.py` 6), "
            "while `test_setup.py` and `test_diagnostics.py` are flat. "
            "Integration tests are uniformly flat, which is fine.\n\n"
            "**Approach**\n"
            "- Codify the convention in `docs/TESTING.md`: unit tests are "
            "grouped into `Test<BehaviourArea>` classes (the existing "
            "majority style); integration tests stay flat functions.\n"
            "- Align the outliers to match: group the flat unit files "
            "(`tests/unit/config_flow/test_setup.py`, "
            "`tests/unit/test_diagnostics.py`) into behaviour classes, and "
            "even out `config_flow/test_reauth.py` so the directory is "
            "internally consistent.\n"
            "- Pure reorganisation: do not rename, merge, or drop any test. "
            "Test count and coverage must be identical before and after.\n\n"
            "**Out of scope:** integration tests (leave flat); any behavioural "
            "change.\n\n"
            "**Acceptance**\n"
            "- [ ] Convention written down in `docs/TESTING.md`\n"
            "- [ ] No unit-test directory mixes class-grouped and flat layouts\n"
            "- [ ] Integration tests unchanged (still flat)\n"
            "- [ ] Collected test count and coverage identical to before"
        ),
    ),
    # ----- v1.9.0: High value -----------------------------------------------
    Issue(
        title="Make category labels translatable",
        milestone="v1.9.0",
        labels=["feat", "size: M", "priority: high"],
        body=(
            "Entity name templates already use `_attr_translation_key`, but the "
            "`{category}` placeholder is filled from an English-only label map "
            "in `const.py`, leaving entity names "
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
    Issue(
        title="Target Python 3.14 across tooling and CI",
        milestone="v1.9.0",
        labels=["ci", "size: S", "priority: high"],
        body=(
            "Tooling targets a Python runtime no current Home Assistant user "
            "runs. `pyproject.toml` sets `[tool.ruff] target-version = "
            '"py312"` and `[tool.mypy] python_version = "3.12"`, and every '
            "`setup-python` step in `.github/workflows/ci.yml` (the "
            "`hacs-preflight`, `lint`, and `test` jobs) pins `3.12`. Current "
            "Home Assistant (2026.6.x) requires Python >= 3.14, and HA "
            "supports only a single Python minor at a time, so lint, "
            "type-check, and tests should run on the version HA actually "
            "ships.\n\n"
            "**Approach**\n"
            '- `pyproject.toml`: set `[tool.ruff] target-version = "py314"` '
            'and `[tool.mypy] python_version = "3.14"`.\n'
            '- `.github/workflows/ci.yml`: change `python-version: "3.12"` to '
            '`"3.14"` in the `hacs-preflight`, `lint`, and `test` jobs.\n'
            "- Check `.github/workflows/copilot-setup-steps.yml` and "
            "`version-check.yml` for hard-coded `3.12` and bump to match.\n"
            "- Run `ruff check`, `ruff format --check`, `mypy`, and `pytest` "
            "on 3.14 and fix any newly surfaced lint/typing findings directly "
            "(do NOT silence them with new `# type: ignore` / `# noqa`).\n\n"
            "**Out of scope:** the `hacs.json` `homeassistant` minimum "
            "(2024.5.0) — that is the minimum HA version, not the dev Python.\n\n"
            "**Acceptance**\n"
            "- [ ] ruff `target-version = \"py314\"` and mypy "
            '`python_version = "3.14"`\n'
            "- [ ] All three CI jobs run on Python 3.14\n"
            "- [ ] No new `# type: ignore` or `# noqa` added to pass\n"
            "- [ ] Lint, typecheck, and full test suite green on 3.14"
        ),
    ),
    Issue(
        title="Test the UniFi HTTP client at the wire with aioresponses",
        milestone="v1.9.0",
        labels=["tests", "size: M", "priority: high"],
        body=(
            "`tests/unit/test_unifi_client.py` injects a bare `MagicMock()` as "
            "the aiohttp session and hand-builds response objects "
            "(`resp.json = AsyncMock(...)`, `resp.raise_for_status = "
            "MagicMock()`). Those doubles assert against a fabricated aiohttp "
            "surface, so they cannot catch real `ClientResponse` behaviour "
            "(status -> `raise_for_status`, content-type handling, redirects) "
            "and they couple the tests to the client's exact internal call "
            "sequence rather than to the HTTP it actually sends.\n\n"
            "**Approach**\n"
            "- Add `aioresponses` to `requirements-dev.txt`.\n"
            "- In the `make_client` helper, pass a real `aiohttp.ClientSession` "
            "instead of `MagicMock()`. The constructor already takes the "
            "session by injection: `UniFiClient(session, base_url, config)`.\n"
            "- Wrap each test body in `with aioresponses() as m:` and register "
            "the expected call, e.g. `m.get(url, status=200, payload={...})`; "
            "for auth-failure cases use `status=401` and let the client's real "
            "`raise_for_status` raise `InvalidAuthError`.\n"
            "- Assert on the request the client MADE (URL, method, headers such "
            "as `X-API-Key`, JSON body) via the aioresponses request history, "
            "not on mock call args.\n"
            "- Note: aioresponses patches `ClientSession._request`, so no real "
            "socket is opened — this stays compatible with the pytest-socket "
            "loopback guard already active in the suite.\n\n"
            "**Scope:** `test_unifi_client.py` only. The integration suite's "
            "existing HTTP stubbing in `tests/integration/conftest.py` is out "
            "of scope.\n\n"
            "**Acceptance**\n"
            "- [ ] `make_client` uses a real `ClientSession`; no MagicMock "
            "session remains in this file\n"
            "- [ ] Success, 401, 404, and malformed-body paths are driven by "
            "aioresponses `status`/`payload`\n"
            "- [ ] At least one test asserts the outbound URL, method, and "
            "auth header\n"
            "- [ ] Coverage of `unifi_client.py` does not drop"
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
    Issue(
        title="Lint, format-check, and type the tests/ tree in CI",
        milestone="v1.9.0",
        labels=["ci", "tests", "size: S", "priority: medium"],
        body=(
            "CI enforces style and types on `custom_components/` only. The "
            "`lint` job runs `ruff check custom_components/`, "
            "`ruff format --check custom_components/`, and "
            "`mypy custom_components/unifi_alerts`; `pytest` runs the tests but "
            "nothing holds the `tests/` tree to the same bar. `pyproject.toml` "
            "already defines a `[tool.ruff.lint.per-file-ignores]` entry for "
            "`tests/*` (allowing `assert`), so the intent to lint tests "
            "exists — CI just never acts on it. This is the root cause of "
            "style/structure drift across test files.\n\n"
            "**Approach**\n"
            "- In `.github/workflows/ci.yml` `lint` job, widen the ruff steps "
            "to cover tests: `ruff check custom_components/ tests/` and "
            "`ruff format --check custom_components/ tests/` (or just `.`).\n"
            "- Run `ruff check`/`ruff format` over `tests/` locally first and "
            "commit the fixups in the same PR so CI starts green.\n"
            "- mypy on tests is optional and often low-value (heavy mock usage "
            "fights strict typing). If added, scope it loosely — do NOT extend "
            "`strict = true` to tests; a separate relaxed override or simply "
            "leaving tests untyped is acceptable. Record the decision in the "
            "PR.\n\n"
            "**Acceptance**\n"
            "- [ ] `ruff check` and `ruff format --check` run over `tests/` in "
            "CI\n"
            "- [ ] Existing tests reformatted/fixed so the job passes\n"
            "- [ ] mypy-on-tests decision made and recorded (in or out)"
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
    Issue(
        title="Fold pytest.ini into pyproject [tool.pytest.ini_options]",
        milestone="v1.9.0",
        labels=["ci", "size: S", "priority: low"],
        body=(
            "Pytest config lives in a standalone `pytest.ini` while ruff, "
            "mypy, and coverage config live in `pyproject.toml`. Moving to a "
            "single source of truth removes one root file and the chance of "
            "the two drifting.\n\n"
            "**Approach**\n"
            "- Recreate every key from `pytest.ini` under a new "
            "`[tool.pytest.ini_options]` table in `pyproject.toml`: "
            "`asyncio_mode`, `asyncio_default_fixture_loop_scope`, `testpaths`, "
            "`pythonpath`, `python_files`, `python_classes`, "
            "`python_functions`, `addopts`, `filterwarnings`, `markers`. "
            "`filterwarnings` and `markers` become TOML arrays of strings.\n"
            "- Delete `pytest.ini`.\n"
            "- Confirm pytest discovers the same tests and the `integration` "
            "marker still resolves.\n\n"
            "**Leave as-is:** the split `requirements-dev.txt` / "
            "`requirements-lint.txt`. A lint-only env that skips the HA stack "
            "is a deliberate speed win, not drift.\n\n"
            "**Acceptance**\n"
            "- [ ] All pytest config lives in `pyproject.toml`\n"
            "- [ ] `pytest.ini` removed\n"
            "- [ ] Same collected test count as before; `-m integration` still "
            "selects the integration tests"
        ),
    ),
    Issue(
        title="Collapse repetitive test bodies with parametrize",
        milestone="v1.9.0",
        labels=["tests", "size: M", "priority: low"],
        body=(
            "Parametrize is used well where it counts (the `_classify` mapping "
            "table in `test_unifi_client.py`) and the factory helpers "
            "(`make_client`, `make_coordinator`, `make_alert`) keep setup DRY, "
            "but the two largest files — `test_coordinator.py` (~84 tests) and "
            "`test_entities.py` (~80 tests) — still carry near-duplicate test "
            "bodies that differ only by input and expected value.\n\n"
            "**Approach**\n"
            "- Find clusters of tests that share a body and vary only in "
            "inputs/expectations; fold each cluster into one "
            "`@pytest.mark.parametrize` with an `ids=` list so failures stay "
            "readable.\n"
            "- Do NOT merge tests that assert genuinely different behaviour or "
            "that would need an `if` inside the body — splitting beats a "
            "parametrize with branching.\n"
            "- Pure refactor: the number of logical assertions and the "
            "coverage figure should be unchanged.\n\n"
            "**Acceptance**\n"
            "- [ ] Duplicate bodies in the two files collapsed where it "
            "improves clarity\n"
            "- [ ] Every parametrized case has a readable `ids` entry\n"
            "- [ ] Coverage of the affected modules is unchanged\n"
            "- [ ] No behavioural test was silently dropped"
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
