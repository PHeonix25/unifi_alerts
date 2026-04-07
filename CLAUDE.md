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
  strings.json                    # UI copy for config flow
  translations/en.json            # copy of strings.json (HA translation convention)
tests/
  conftest.py                     # shared fixtures, MOCK_CONFIG
  test_models.py
  test_coordinator.py
  test_unifi_client.py
  test_config_flow.py             # config flow steps, webhook URL token display, options flow defaults
  test_diagnostics.py             # diagnostics platform: redaction, webhook URL exposure, coordinator state
.github/workflows/
  ci.yml                          # hassfest + HACS validate + ruff + mypy + pytest
  release.yml                     # zips and attaches release asset on GitHub release
hacs.json
pyproject.toml                    # ruff and mypy config
pytest.ini
README.md                         # user-facing install and setup guide
```

## Non-negotiable constraints

- **Python 3.12+ only.** Use modern type hints (`list[str]` not `List[str]`, `X | None` not `Optional[X]`).
- **All I/O is async.** No blocking calls anywhere. Use `aiohttp` for HTTP, never `requests`.
- **No YAML configuration.** Everything goes through the config flow. Do not add `async_setup` or `configuration.yaml` support.
- **`iot_class: local_push`** must stay in `manifest.json` — this is accurate and affects HA's energy/performance classification.
- **`manifest.json` key order is enforced by hassfest** — keys must be: `domain`, `name`, then all remaining keys alphabetically. Violating this order breaks CI.
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
- **Move into the working directory at the start of every session** — avoids needing path prefixes on every command.
- Always run tests before committing — never commit broken code. If tests are failing, fix them before committing.
- Always run ruff lint and format checks before committing — maintain a clean codebase.
- Always update `HISTORY.md` with a detailed description of what was done, why, and how, including test coverage. This is the primary source of truth for what has been completed and should be reflected in the codebase. Do not rely on memory or Git history alone.
- Always update `TODO.md` by removing completed items and adding new ones as needed. This is the primary source of truth for what is pending work. Do not rely on memory or Git history alone.
- At the end of the day, make sure there are no commits outstanding, no changes locally that need to be pushed, and that the `auto-memory\dirty-files` file is empty (if it exists on disk). This ensures a clean slate for the next session.

## Resuming an interrupted session

Interruptions (timeouts, hibernation, re-login) are common. When a new conversation starts mid-task, always do this before anything else:

1. **Read `HISTORY.md`** — the last entry describes what was most recently completed.
2. **Run `git status` and `git diff HEAD`** — uncommitted changes show exactly what was in-flight.
3. **Read `TODO.md`** — the top remaining item is what was probably being worked on.
4. **Check the venv** — run `Test-Path .venv\Scripts\pytest.exe` in PowerShell. If `False`, recreate it:
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\pip install pytest pytest-asyncio aiohttp homeassistant ruff mypy --quiet
   ```
5. **Resume from where the diff left off** — do not re-do already-applied changes. Pick up at the next pending step (usually: run tests, fix lint, commit).

## Before making changes

1. Check `TODO.md` for context on what's known to be incomplete or broken.
2. Run `.venv\Scripts\pytest tests/ -v` and confirm it passes before and after your change.
3. Run `.venv\Scripts\ruff check custom_components/` and `.venv\Scripts\ruff format --check custom_components/` before committing.
4. All test/lint/format commands use the `.venv` in the repo root — never the system Python.
