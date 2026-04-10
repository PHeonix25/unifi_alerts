# CLAUDE.md — unifi_alerts

This is the primary context file for Claude Code. Read this first, then follow the references.

## What this project is

A Home Assistant custom integration (`domain: unifi_alerts`) that aggregates UniFi Network controller alerts into HA sensors, binary sensors, event entities, and buttons. It is intended for publication as a HACS custom repository.

**Two data paths run in parallel:**
- **Webhook push** — UniFi Alarm Manager POSTs to per-category webhook URLs registered by HA. This is the real-time path.
- **REST polling** — the integration polls the UniFi controller's alarm API on a configurable interval to populate open-count sensors and catch alerts that missed the webhook.

## Reference documents

| File | Read when you need to... |
|---|---|
| `ARCHITECTURE.md` | Understand how the modules fit together, data flow, and design decisions |
| `HOMEASSISTANT.md` | Work with HA-specific patterns: coordinators, entity classes, config flows, platforms |
| `UNIFI.md` | Understand the UniFi API, auth methods, alarm payloads, and event key taxonomy |
| `TESTING.md` | Run, write, or extend tests |
| `TODO.md` | Find the prioritised backlog of next steps |
| `ROADMAP.md` | See which TODOs are planned for each release (v1.0, v1.1, v1.2, v2.0) |

## Repository layout

```
custom_components/unifi_alerts/   # integration source
  __init__.py                     # entry setup/teardown, platform forwarding; raises ConfigEntryNotReady on auth or first-refresh failure so HA retries; emits _LOGGER.warning when SSL verification is disabled; unload order: coordinator.async_shutdown() → unregister webhooks → client.close()
  manifest.json                   # HA metadata (domain, version, iot_class); do NOT add "homeassistant" min-version key — it is not in the HA manifest schema and breaks hassfest
  const.py                        # all constants, category defs, UniFi key→category map; DEFAULT_VERIFY_SSL = True (secure by default); CONF_WEBHOOK_SECRET = "webhook_secret"
  models.py                       # UniFiAlert and CategoryState dataclasses; all datetimes are UTC-aware (datetime.now(UTC))
  unifi_client.py                 # async HTTP client, auth auto-detect
  coordinator.py                  # DataUpdateCoordinator, owns all category state; polling path sets is_alerting/last_alert directly (does NOT call apply_alert, so alert_count is not incremented); cancel_clear(category) cancels pending auto-clear tasks; async_shutdown() cancels all pending clear tasks on unload
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
  ci.yml                          # hassfest + hacs-preflight + HACS action + lint (ruff, mypy, translation drift) + pytest
  release.yml                     # zips and attaches release asset on GitHub release
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

## Coding conventions

- Module-level `_LOGGER = logging.getLogger(__name__)` in every file that logs.
- `_attr_*` class attributes for HA entity properties — only override as `@property` if the value is dynamic.
- `_device_info()` is a module-level helper function (not a method) duplicated across platform files intentionally — keeps each platform self-contained.
- All `const.py` additions go in the appropriate labelled section with a comment.
- Tests use `MagicMock` / `AsyncMock` for the UniFi client — never make real HTTP calls in tests.

## Working style

- **Never assume — always ask.** If anything about the task, scope, or approach is unclear, ask before proceeding. Do not guess intent.
- **Always pull `main` before starting work** — run `git pull origin main` at the start of every session to avoid diverging from origin. Never start implementing changes on a stale branch.
- **Move into the working directory at the start of every session** — avoids needing path prefixes on every command.
- Always run `make check` before committing — never commit broken code. `make check` runs lint, typecheck, HACS preflight, translation drift check, and the full test suite in one shot.
- Always update `HISTORY.md` with a detailed description of what was done, why, and how, including test coverage. This is the primary source of truth for what has been completed and should be reflected in the codebase. Do not rely on memory or Git history alone.
- Always update `TODO.md` by removing completed items and adding new ones as needed. This is the primary source of truth for what is pending work. Do not rely on memory or Git history alone.
- At the end of the day, make sure there are no commits outstanding, no changes locally that need to be pushed, and that the `auto-memory\dirty-files` file is empty (if it exists on disk). This ensures a clean slate for the next session.

## Resuming an interrupted session

Interruptions (timeouts, hibernation, re-login) are common. When a new conversation starts mid-task, always do this before anything else:

1. **Read `HISTORY.md`** — the last entry describes what was most recently completed.
2. **Run `git status` and `git diff HEAD`** — uncommitted changes show exactly what was in-flight.
3. **Read `TODO.md`** — the top remaining item is what was probably being worked on.
4. **Check the venv** — on Linux/Mac: `ls .venv/bin/pytest`; on Windows PowerShell: `Test-Path .venv\Scripts\pytest.exe`. If missing, recreate it:
   - **Linux/Mac:** `make setup` (or manually: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt --quiet`)
   - **Windows:** `py -3.12 -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt --quiet`
5. **Resume from where the diff left off** — do not re-do already-applied changes. Pick up at the next pending step (usually: run tests, fix lint, commit).

## Before making changes

1. Check `TODO.md` for context on what's known to be incomplete or broken.
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
