# AGENTS.md - unifi_alerts

> This file is the single home for the shared facts every agent needs: repo purpose, tech stack, build/test commands, and the repo map. Do not copy these blocks into [`CLAUDE.md`](CLAUDE.md) or [`.github/copilot-instructions.md`](.github/copilot-instructions.md); link here instead. `scripts/validate_docs.py` fails the build if the anchored blocks below are duplicated into another file.
> Claude-specific working style and the full non-negotiable constraint list live in [`CLAUDE.md`](CLAUDE.md). Release and branching detail lives in [`docs/RELEASING.md`](docs/RELEASING.md). Extended docs (architecture, HA patterns, UniFi API, testing) live in [`docs/`](docs/).

---

## What this repo is

A Home Assistant custom integration (`domain: unifi_alerts`) that aggregates UniFi Network controller alerts into HA sensors, binary sensors, event entities, and buttons. Distributed via HACS.

This integration covers **UniFi Network** only (System Logs / SIEM events from the Network Application on UniFi OS). It does **not** support UniFi Protect (cameras, motion detection, NVR).

Two data paths run in parallel:
- **Webhook push** - UniFi Alarm Manager POSTs to per-category webhook URLs registered by HA. Real-time path.
- **REST polling** - integration polls the UniFi controller's alarm API on a configurable interval. Backstop for open-count data and missed webhooks.

---

## Quick reference

| Topic | Where to look |
| ----- | ------------- |
| Architecture & data flow | `docs/ARCHITECTURE.md` |
| HA-specific patterns | `docs/HOMEASSISTANT.md` |
| UniFi API & payloads | `docs/UNIFI.md` |
| Outstanding work | GitHub Issues (taxonomy in `docs/TODO.md`) |
| Test guidance | `docs/TESTING.md` |
| Per-file responsibilities | `docs/REPO_LAYOUT.md` |

---

## Tech stack

<!-- shared:stack -->
| Layer | Tool |
| ----- | ---- |
| Language | Python 3.14+ |
| Async HTTP | `aiohttp` |
| Lint + format | `ruff` |
| Type checking | `mypy` (strict) |
| Tests | `pytest` + `MagicMock`/`AsyncMock` |
| HA integration | `custom_components/unifi_alerts/` |
<!-- /shared:stack -->

---

## Build & test commands

<!-- shared:commands -->
```bash
make check        # default: lint + typecheck + validate + test (run before every commit)
make lint         # ruff check + format check
make typecheck    # mypy
make validate     # HACS preflight + translation drift check
make test         # pytest
```
<!-- /shared:commands -->

All commands use `.venv` in the repo root - never the system Python. Run `make setup` once after cloning to create it.

---

## Repository structure

```
custom_components/unifi_alerts/   # integration source
  __init__.py                     # setup/teardown, config entry lifecycle
  const.py                        # all constants, category defs, UniFi key->category map
  coordinator.py                  # DataUpdateCoordinator - owns all category state
  webhook_handler.py              # registers HA webhooks, validates ?token= bearer auth
  config_flow.py                  # three-step UI setup + options flow
  models.py                       # UniFiAlert dataclass, UniFiClientConfig TypedDict
  unifi_client.py                 # async HTTP client for UniFi controller API
  binary_sensor.py                # per-category and rollup binary sensors
  sensor.py                       # per-category message + open-count sensors, rollup count
  event.py                        # per-category event entities
  button.py                       # per-category and rollup clear buttons
  services.py                     # HA service: clear alert category
  diagnostics.py                  # HA diagnostics redaction
  strings.json                    # UI strings - must stay identical to translations/en.json
  translations/en.json            # English translations - must stay identical to strings.json

tests/
  conftest.py                     # root fixtures
  unit/                           # unit tests by module
    conftest.py
    config_flow/                  # config flow tests split by flow type
      conftest.py
  integration/                    # full config-entry lifecycle tests

docs/                             # extended documentation
scripts/                          # validation helpers (validate_hacs.py, check_translations.py, etc.)
agentrc.eval.json                 # agent planning-eval cases (see below)
```

`agentrc.eval.json` holds planning-evaluation cases for agent harnesses: each case pairs a realistic task prompt with the expectations a good implementation plan must meet (files touched, constraints respected, tests updated). It is not executed by CI. If you rename a symbol or move a test file referenced in its expectations, update the case text in the same PR.

---

## Key source files

| File | Role |
| ---- | ---- |
| `custom_components/unifi_alerts/const.py` | All constants, category defs, `UNIFI_KEY_TO_CATEGORY` map |
| `custom_components/unifi_alerts/coordinator.py` | DataUpdateCoordinator - owns all category state |
| `custom_components/unifi_alerts/webhook_handler.py` | Registers HA webhooks, validates `?token=` bearer auth |
| `custom_components/unifi_alerts/config_flow.py` | Three-step UI setup + options flow |
| `custom_components/unifi_alerts/strings.json` | Must stay identical to `translations/en.json` |
| `tests/conftest.py` | Root fixtures and shared helpers |

---

## Adding a new alert category

This is the most common extension task. Every step is required - missing any one breaks the integration silently or at runtime.

1. **`const.py`** - add `CATEGORY_<NAME>: str = "<name>"` constant; add it to `ALL_CATEGORIES`; add entries to `CATEGORY_ICONS`, `CATEGORY_ICONS_OK`; add all relevant `EVT_*` keys to `UNIFI_KEY_TO_CATEGORY`.
2. **`strings.json`** - add `"cat_<name>"` key under each config step that lists categories (`categories.data`, `options.data`). Add webhook URL label under `finish.data` and `options.data`. Add the per-category entity display-name keys (binary sensor, last message, open count, event, clear button) under `entity` - these supply the localised entity names that used to come from `CATEGORY_LABELS`.
3. **`translations/en.json`** - mirror every change made to `strings.json` exactly. Run `scripts/check_translations.py` to validate.
4. **`binary_sensor.py`**, **`sensor.py`**, **`event.py`**, **`button.py`** - no code changes needed for most categories (platforms iterate `ALL_CATEGORIES` dynamically), but review each if adding a category with unusual display logic.
5. **`tests/`** - add the new category key to fixtures in `tests/unit/conftest.py` and `tests/integration/conftest.py`. Check `tests/unit/coordinator/` and `test_entities.py` for category-enumerated tests that need updating.
6. Run `make check` - this runs the translation drift check and all tests. Fix any failures before committing.

---

## Hard rules

- **No blocking I/O** - every function touching the network or disk must be `async`.
- **`X | None`** not `Optional[X]`; `list[str]` not `List[str]`.
- **Entities never cache state** - read from coordinator only.
- **`manifest.json` keys** must be `domain`, `name`, then all remaining keys alphabetically - hassfest enforces order.
- **Webhook token auth is mandatory** - every inbound webhook request must be validated against `CONF_WEBHOOK_SECRET` via `?token=`. Never remove this check.
- **GitHub Actions `uses:` must be full 40-char SHA** - no tags, no branch refs.
- **No third-party release actions** - use `gh release create --generate-notes` only.
- **`strings.json` and `translations/en.json` must be identical** - CI enforces this.

---

## Common pitfalls

- **Partial category registration** - the most common mistake. Adding a category to `const.py` but forgetting `strings.json`/`translations/en.json` breaks the config flow UI silently. Always run `make validate` after touching categories.
- **Blocking I/O in coordinator** - `UniFiAlertsCoordinator._async_update_data` must stay async-clean. Importing and calling `requests` or any sync HTTP here will block the HA event loop.
- **Caching state in entities** - entities must read state from `self.coordinator.data` on every `@property` call. Storing a local copy causes stale UI after coordinator updates.
- **`manifest.json` key order** - hassfest rejects any manifest where keys after `domain`/`name` are not alphabetical. Always check with `make validate` after editing this file.
- **Squash-merging `dev > main`** - use "Create a merge commit" only. Squash leaves the release commit out of `dev`'s ancestry and causes merge conflicts on the next cycle.
- **Short or tag-ref GitHub Actions SHAs** - Dependabot proposes SHA bumps weekly; always resolve the new SHA fully before merging.
