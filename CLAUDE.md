# CLAUDE.md — unifi_alerts

This is the primary context file for Claude Code. Read this first, then follow the references.

## What this project is

A Home Assistant custom integration (`domain: unifi_alerts`) that aggregates UniFi Network controller alerts into HA sensors, binary sensors, event entities, and buttons. It is intended for publication as a HACS custom repository.

This integration covers **UniFi Network** only (System Logs / SIEM events from the Network Application on UniFi OS). It does **not** support UniFi Protect (cameras, motion detection, NVR).

**Two data paths run in parallel:**
- **Webhook push** — UniFi Alarm Manager POSTs to per-category webhook URLs registered by HA. This is the real-time path.
- **REST polling** — the integration polls the UniFi controller's alarm API on a configurable interval to populate open-count sensors and catch alerts that missed the webhook.

## Reference documents

| File | Read when you need to... |
|---|---|
| `docs/ARCHITECTURE.md` | Understand how the modules fit together, data flow, and design decisions |
| `docs/HOMEASSISTANT.md` | Work with HA-specific patterns: coordinators, entity classes, config flows, platforms |
| `docs/UNIFI.md` | Understand the UniFi API, auth methods, alarm payloads, and event key taxonomy |
| `docs/TESTING.md` | Run, write, or extend tests |
| `docs/DEVELOPING.md` | Set up a local dev environment, run tests, contribute changes |
| `docs/TODO.md` | Find the prioritised backlog of next steps |
| `docs/ROADMAP.md` | See which TODOs are planned for each release (v1.0, v1.1, v1.2, v2.0) |
| `docs/HISTORY.md` | Read the chronological log of completed work (append a dated entry after each task) |
| `CHANGELOG.md` | User-facing release summary in Keep-a-Changelog format. Update the `[Unreleased]` section as user-visible changes land. |
| `SECURITY.md` | Vulnerability disclosure policy. If a task touches security-relevant components, check the in-/out-of-scope listing here before responding to a security report. |

## Repository layout

```
custom_components/unifi_alerts/   # integration source
  __init__.py                     # entry setup/teardown, platform forwarding; raises ConfigEntryNotReady on auth or first-refresh failure so HA retries; emits _LOGGER.warning when SSL verification is disabled; unload order: coordinator.async_shutdown() → unregister webhooks → client.close()
  manifest.json                   # HA metadata (domain, version, iot_class); do NOT add "homeassistant" min-version key — it is not in the HA manifest schema and breaks hassfest
  const.py                        # all constants, category defs, UniFi key→category map; DEFAULT_VERIFY_SSL = True (secure by default); CONF_WEBHOOK_SECRET = "webhook_secret"
  models.py                       # UniFiAlert and CategoryState dataclasses; all datetimes are UTC-aware (datetime.now(UTC))
  unifi_client.py                 # async HTTP client, auth auto-detect
  coordinator.py                  # DataUpdateCoordinator, owns all category state; polling path sets is_alerting/last_alert directly (does NOT call apply_alert, so alert_count is not incremented); open_count filtered by last_cleared_at watermark (alarms since last Clear only); async_clear_category()/async_clear_all() are the sole clear entry points — they cancel tasks, advance watermark, persist via Store, notify; cancel_clear(category) cancels pending auto-clear tasks; async_restore_watermarks() loads persisted watermarks from storage on startup; async_shutdown() cancels all pending clear tasks on unload
  webhook_handler.py              # registers HA webhooks (POST-only), dispatches to coordinator; rejects requests missing/wrong ?token= with HTTP 401; bearer secret from CONF_WEBHOOK_SECRET
  config_flow.py                  # three-step UI setup (credentials → categories → webhook URLs with token) + options flow; generates CONF_WEBHOOK_SECRET via secrets.token_urlsafe(32) on first auth; network_device and network_client default OFF; options flow reads entry.options first, falls back to entry.data
  diagnostics.py                  # HA diagnostics platform; redacts password/api_key/username, exposes webhook URLs + coordinator state
  binary_sensor.py                # per-category + rollup binary sensors
  sensor.py                       # message, count, and rollup count sensors
  event.py                        # event entities, fire per alert
  button.py                       # manual clear buttons
  strings.json                    # UI copy for config flow; must be identical to translations/en.json — CI enforces this
  translations/en.json            # runtime translation file loaded by HA; must be identical to strings.json — CI enforces this
tests/
  conftest.py                     # shared fixtures, MOCK_CONFIG; make_hass() and make_entry() module-level helpers for setup/unload tests
  test_models.py
  test_coordinator.py
  test_unifi_client.py
  test_config_flow.py             # config flow steps, webhook URL token display, options flow defaults
  test_diagnostics.py             # diagnostics platform: redaction, webhook URL exposure, coordinator state
  test_webhook_handler.py         # WebhookManager: register/unregister, token auth, alert dispatch
  test_init.py                    # async_setup_entry / async_unload_entry lifecycle, teardown order
  test_entities.py                # all entity property methods: binary_sensor, sensor, event, button
.github/workflows/
  ci.yml                          # hassfest + hacs-preflight + HACS action + lint (ruff, mypy, translation drift) + pytest; runs on push/PR to main and dev
  version-check.yml               # enforces version format per branch: main=X.Y.Z stable, dev=X.Y.Z-preN; runs on push/PR to main and dev
  release.yml                     # triggered by version tags (v1.0.0 stable, v1.0.0-pre1 pre-release); validates tag matches manifest, packages the integration, and publishes via `gh release create --generate-notes` (NOT softprops/action-gh-release — that was removed; do not re-introduce it). Pre-release detection regex uses `grep -qE -- '-pre[0-9]+$'` (the `--` terminator is load-bearing).
.github/
  dependabot.yml                  # tracks the github-actions ecosystem only (weekly, Brisbane TZ); minor+patch grouped, major bumps individual. Required to keep the SHA pins fresh — do NOT remove. Python deps stay manual.
  release.yml                     # release-notes categories file used by `gh release create --generate-notes` to group merged PRs by label (Security / Bug Fixes / Features / Documentation / Tests / CI / Other). DIFFERENT FILE from .github/workflows/release.yml.
  ISSUE_TEMPLATE/
    bug_report.yml                # required-field bug template; warns users to redact `?token=...` from logs.
    feature_request.yml           # problem → solution → alternatives template.
    config.yml                    # disables blank issues; surfaces the security-advisory link + Discussions.
    unclassified_event_key.yml    # for reporting UniFi event keys not yet in UNIFI_KEY_TO_CATEGORY.
.githooks/
  pre-push                        # local gate: HACS preflight → translation drift → ruff → mypy → pytest; install with: git config core.hooksPath .githooks
scripts/
  validate_hacs.py                # pure-Python HACS manifest pre-flight; checks required fields, iot_class, dependencies (no HA core built-ins); run locally or in CI
Makefile                          # convenience targets: setup, lint, typecheck, validate, test, check (default = all)
requirements-dev.txt              # single source of truth for all dev dependencies; used by make setup and both CI jobs
hacs.json
pyproject.toml                    # ruff and mypy config
pytest.ini
README.md                         # user-facing install, setup, and contributing guide
CHANGELOG.md                      # Keep-a-Changelog file. The `[Unreleased]` section accumulates user-visible changes between tags. `docs/HISTORY.md` is the dated narrative source-of-truth; `CHANGELOG.md` is the user-facing summary scoped to releases. Pre-releases (`X.Y.Z-preN`) are NOT listed individually — only the consolidated `X.Y.Z` entry that bundles them.
SECURITY.md                       # vulnerability disclosure policy. Reports go via GitHub private security advisories. Do NOT funnel security reports through public issues.
CODEOWNERS                        # auto-requests review from @PHeonix25 on every PR.
```

## Non-negotiable constraints

- **Python 3.12+ only.** Use modern type hints (`list[str]` not `List[str]`, `X | None` not `Optional[X]`).
- **All I/O is async.** No blocking calls anywhere. Use `aiohttp` for HTTP, never `requests`.
- **No YAML configuration.** Everything goes through the config flow. Do not add `async_setup` or `configuration.yaml` support.
- **`iot_class: local_push`** must stay in `manifest.json` — this is accurate and affects HA's energy/performance classification.
- **`manifest.json` key order is enforced by hassfest** — keys must be: `domain`, `name`, then all remaining keys alphabetically. Violating this order breaks CI.
- **`manifest.json` `dependencies` must only list HA integrations installable by HACS** — do NOT list HA core built-ins (e.g. `webhook`, `http`, `frontend`). hassfest accepts them but the HACS validator rejects them, breaking CI.
- **`DEFAULT_VERIFY_SSL = True`** — SSL verification is on by default; only disable for controllers with self-signed certificates. Never silently change this default.
- **Webhooks are `local_only: True`** — do not remove this without a documented reason.
- **Webhook bearer token auth is mandatory** — every inbound webhook request must be validated against `CONF_WEBHOOK_SECRET` via `?token=` query param. Never remove this check or accept requests that fail it.
- **Category state lives only in the coordinator** — entities must not cache state themselves.
- **Every GitHub Actions `uses:` reference must be pinned to a full 40-character commit SHA** — no branch names (`@main`, `@master`), no tag names (`@v2`, `@v6`), no short SHAs. Add a trailing comment noting the resolved version or branch for human readers (e.g. `# v3.0.0` or `# master tip 2026-04-22`). This applies to every workflow in `.github/workflows/`. When bumping an action, resolve the new SHA via `gh api repos/OWNER/REPO/git/refs/tags/TAG` (or `.../heads/BRANCH` for repos without tags) and replace both the SHA and its comment in the same edit. Dependabot (`.github/dependabot.yml`) proposes these bumps weekly — review the SHA against the upstream tag before merging.
- **The release pipeline uses `gh release create --generate-notes` only** — no third-party release actions. `softprops/action-gh-release` was deliberately removed in cluster D; do NOT re-introduce it (or any other third-party release publisher) when editing `.github/workflows/release.yml`. The GitHub CLI is pre-installed on `ubuntu-latest` runners. `actions/checkout` in that workflow MUST keep `fetch-depth: 0` — `--generate-notes` needs the full tag history to compute the previous-tag boundary.
- **`CHANGELOG.md` must be updated alongside notable user-visible changes.** Add bullets under `[Unreleased]` as features/fixes/security work lands; never edit released sections. When bumping the manifest from `X.Y.Z-preN` to a stable `X.Y.Z`, rename `[Unreleased]` to `[X.Y.Z] — YYYY-MM-DD`, add a fresh empty `[Unreleased]` above it, and update the link references at the bottom. Pre-release version bumps (`-preN`) do NOT touch `CHANGELOG.md`. `docs/HISTORY.md` is still the dated narrative source-of-truth for everything; `CHANGELOG.md` is just the user-facing release summary.
- **PRs must carry one of the labels recognised by `.github/release.yml`** so auto-generated release notes group them correctly: `security`, `bug`, `enhancement` / `feature`, `documentation` / `docs`, `tests`, `ci` / `github-actions` / `dependencies`. Unlabelled PRs fall through to "🧹 Other Changes". Apply the label when opening the PR; reviewers don't need to remember.

## Coding conventions

- Module-level `_LOGGER = logging.getLogger(__name__)` in every file that logs.
- `_attr_*` class attributes for HA entity properties — only override as `@property` if the value is dynamic.
- `_device_info()` is a module-level helper function (not a method) duplicated across platform files intentionally — keeps each platform self-contained.
- All `const.py` additions go in the appropriate labelled section with a comment.
- Tests use `MagicMock` / `AsyncMock` for the UniFi client — never make real HTTP calls in tests.

## Branching strategy and versioning

This project uses a two-branch model. All active development happens on `dev`; `main` is stable-only.

### Branches

| Branch | Purpose | Version format | Example |
|--------|---------|---------------|---------|
| `main` | Stable releases only. CI enforces no pre-release suffix. | `X.Y.Z` | `1.0.0`, `1.1.0` |
| `dev` | Active development. CI accepts `-preN` during development, or stable `X.Y.Z` when preparing a release — no merge-back needed. | `X.Y.Z-preN` or `X.Y.Z` | `1.1.0-pre1`, `1.1.0` |
| `feature/*` or `claude/*` | Short-lived work. **Must branch off `dev`, not `main`.** No version format enforced by CI. | Any | — |

### Versioning conventions

- **Minor bumps on main:** releases from `main` increment the minor version (`1.0.0 → 1.1.0 → 1.2.0`). Patch releases (`1.0.1`) are reserved for critical hotfixes.
- **Pre-release sequence on dev:** each tagged checkpoint on `dev` increments the pre-release counter (`1.1.0-pre1 → 1.1.0-pre2`). The base version (`1.1.0`) matches the *next* planned minor release on `main`.
- **`manifest.json` is the single source of truth** for the version — the release workflow validates the pushed tag matches it exactly.

### Release workflow

```
dev  ──┬── (work) ──► tag v1.1.0-pre1  ──► GitHub pre-release  (automated)
       │
       ├── (work) ──► tag v1.1.0-pre2  ──► GitHub pre-release  (automated)
       │
       ├── bump manifest to 1.1.0 (via claude/* PR → dev)
       │    └─► PR dev → main
       │         └─► tag v1.1.0  ──► GitHub stable release  (automated)
       │
       └── bump manifest to 1.2.0-pre1 (via claude/* PR → dev)  ← start next cycle
```

1. **Development:** work on `dev`. Version in manifest stays at `X.Y.Z-preN`.
2. **Pre-release checkpoint:** bump the `N` in manifest (e.g. `pre1 → pre2`) on a short-lived `claude/*` branch, open a PR targeting `dev`, merge it, then provide the user with the tag command (Claude cannot push tags). After the PR merges, the user runs:
   ```bash
   git checkout dev && git pull origin dev
   git tag vX.Y.Z-preN && git push origin vX.Y.Z-preN
   ```
   GitHub Actions creates a pre-release automatically.
3. **Stable release:** bump manifest from `X.Y.Z-preN` to `X.Y.Z` on a `claude/*` branch, open PR targeting `dev`. **In the same PR, finalise `CHANGELOG.md`:** rename the `[Unreleased]` heading to `[X.Y.Z] — YYYY-MM-DD`, insert a fresh empty `[Unreleased]` above it, and add a `[X.Y.Z]: …/releases/tag/vX.Y.Z` link at the bottom. `dev` CI now accepts stable versions, so this passes. Merge to `dev`, then open a PR from `dev` → `main`. After that merges, provide the user with the tag command:
   ```bash
   git checkout main && git pull origin main
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
   GitHub Actions creates a stable release automatically; the auto-generated notes are grouped by the labels on PRs merged between the previous tag and this one.
4. **Start next cycle:** bump manifest to `X.(Y+1).0-pre1` on a `claude/*` branch, open PR targeting `dev`, merge. Development continues forward — no merge-back from `main` to `dev` needed. Notable changes between releases accumulate under `CHANGELOG.md` `[Unreleased]` as their PRs land — don't batch them at release time.

> **Tag convention reminder:** Claude cannot push tags directly. Whenever the user says "update the tag", "cut a release", "tag the branch", or similar — open a version-bump PR to `dev` (or `main` for stable), wait for merge, then give the user the exact `git tag` + `git push origin <tag>` commands to run locally.

### CI enforcement

- `version-check.yml` blocks pushes and PRs that violate the format for the target branch.
- `release.yml` fails if the pushed tag does not exactly match `manifest.json`.
- Never manually create a GitHub release — always push a version tag and let the workflow do it.

### Branch protection (configure once in GitHub Settings → Branches)

Recommended rules:
- **`main`:** require PR, require status checks (`CI / *`, `Version Check / *`), no direct push, no force-push.
- **`dev`:** require PR, require status checks (`CI / *`, `Version Check / *`), no direct push, no force-push. Version bumps go via a short-lived `chore/bump-*` branch PR.

## Working style

- **Never assume — always ask.** If anything about the task, scope, or approach is unclear, ask before proceeding. Do not guess intent.
- **Always pull `dev` before starting work** — run `git pull origin dev` at the start of every session to avoid diverging from origin. Never start implementing changes on a stale branch. Pull `main` only when checking stable state.
- **Work on `dev`, not `main`** — `main` is only updated via PRs from `dev`. Never commit directly to `main`.
- **Feature and claude/* branches must be created from `dev`** — run `git checkout dev && git pull origin dev && git checkout -b <branch>`. Never branch off `main`. PRs from feature branches must target `dev`, not `main`.
- **Always start fresh from `dev` for new work.** At the very start of a new task, even if a branch is already specified by the system instructions, run `git checkout dev && git pull origin dev` first, then create or recreate the working branch from that fresh `dev` tip. Never inherit whatever branch the previous session left checked out — it may be a stale `chore/bump-*` or other already-merged branch, and committing on top of it produces a branch that contains commits already in `dev`.
- **After a PR merges, delete the local branch and switch back to `dev`** — run `git checkout dev && git pull origin dev && git branch -D <merged-branch>`. This forces the next task to branch off a clean `dev` instead of accidentally building on a stale, already-merged branch.
- **Move into the working directory at the start of every session** — avoids needing path prefixes on every command.
- Always run `make check` before committing — never commit broken code. `make check` runs lint, typecheck, HACS preflight, translation drift check, and the full test suite in one shot.
- Always update `docs/HISTORY.md` with a detailed description of what was done, why, and how, including test coverage. This is the primary source of truth for what has been completed and should be reflected in the codebase. Do not rely on memory or Git history alone.
- Always update `docs/TODO.md` by removing completed items and adding new ones as needed. This is the primary source of truth for what is pending work. Do not rely on memory or Git history alone.
- At the end of the day, make sure there are no commits outstanding, no changes locally that need to be pushed, and that the `auto-memory\dirty-files` file is empty (if it exists on disk). This ensures a clean slate for the next session.

## Resuming an interrupted session

Interruptions (timeouts, hibernation, re-login) are common. When a new conversation starts mid-task, always do this before anything else:

1. **Read `docs/HISTORY.md`** — the last entry describes what was most recently completed.
2. **Run `git status` and `git diff HEAD`** — uncommitted changes show exactly what was in-flight.
3. **Read `docs/TODO.md`** — the top remaining item is what was probably being worked on.
4. **Check the venv** — on Linux/Mac: `ls .venv/bin/pytest`; on Windows PowerShell: `Test-Path .venv\Scripts\pytest.exe`. If missing, recreate it:
   - **Linux/Mac:** `make setup` (or manually: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt --quiet`)
   - **Windows:** `py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt --quiet`
5. **Resume from where the diff left off** — do not re-do already-applied changes. Pick up at the next pending step (usually: run tests, fix lint, commit).

## Before making changes

1. Check `docs/TODO.md` for context on what's known to be incomplete or broken.
2. Run `make check` (or `make` — it's the default target) to run all local validation in one shot:
   - ruff lint + format check
   - mypy type check
   - HACS manifest pre-flight (`scripts/validate_hacs.py`)
   - strings.json ↔ translations/en.json drift check
   - full pytest suite
3. Individual targets: `make lint`, `make typecheck`, `make validate`, `make test`.
4. All commands use the `.venv` in the repo root — never the system Python.

## Pre-push hook (install once per clone)

A git hook at `.githooks/pre-push` runs all of the above automatically before every `git push`. Activate it once after cloning:

```bash
git config core.hooksPath .githooks
```

If the hook is not installed, run `scripts/validate_hacs.py` manually before every push that touches `manifest.json` or `hacs.json`.
