# History

## 2026-04-02 — Fix CI: hassfest manifest key order + HACS validation

Fixed two CI failures on the `main` branch:
- **hassfest:** removed invalid `"homeassistant"` key (not in HA manifest schema), then fixed key ordering to `domain`, `name`, then alphabetical — both required by hassfest.
- **HACS Action:** added repo description and topics (`home-assistant`, `hacs`, `unifi`, `homeassistant`) via `gh repo edit`; added `custom_components/unifi_alerts/brand/icon.png` placeholder (replace with real 256×256 icon before HACS submission).

## 2026-04-01 — Graceful shutdown: cancel pending auto-clear tasks

Added `async_shutdown()` to `UniFiAlertsCoordinator` which cancels all pending `_clear_tasks` and clears the dict. Called from `async_unload_entry` in `__init__.py` so HA stop no longer logs `CancelledError` noise from abandoned asyncio sleep tasks. Added 2 tests (`TestShutdown`; 111 total). Removed completed item from `TODO.md`.

## 2026-04-01 — Config flow: webhook URL display

Added `async_step_finish` as a third step in the config flow (between `async_step_categories` and `async_create_entry`). The step pre-generates the deterministic webhook URLs for all enabled categories using `async_generate_url` + `webhook_id_for_category` and renders them as `description_placeholders` so the user can copy them into UniFi Alarm Manager before completing setup. Also added `description_placeholders` with the current webhook URLs to the options flow `init` step, so users can look up URLs at any time via the Configure button. Updated `strings.json` and `translations/en.json` with the new `finish` step copy and options `description`. Added 4 new tests (8 total in `test_config_flow.py`; 109 total). Removed completed item from TODO.md.

## 2026-04-01 — Expand UNIFI_KEY_TO_CATEGORY map + session resumption guide

Expanded `UNIFI_KEY_TO_CATEGORY` in `const.py` from 26 to 62 entries using the aiounifi library and community sources (DM, XG, roam events, rogue AP/DHCP, PoE overload, client blocked, etc.). Added debug logging in `_classify` for unclassified keys pointing users to the issue tracker. Added GitHub issue template (`.github/ISSUE_TEMPLATE/unclassified_event_key.yml`) for reporting new keys. Added 57 new parametrised test cases (105 total, all passing). Added `pythonpath = .` to `pytest.ini`. Added session-resumption guide and venv instructions to `CLAUDE.md`.

## 2026-03-31 — Add 256×256 icon.png

Added `custom_components/unifi_alerts/icon.png` (256×256 PNG) required by HACS and HA for display in the integrations UI and HACS browser. Closed the corresponding TODO item.

## 2026-03-31 — Fix coroutine-never-awaited warning in coordinator tests

Replaced plain `MagicMock()` for `hass.async_create_task` with a helper that calls `coro.close()`, cleanly discarding the `_auto_clear` coroutine and eliminating the `RuntimeWarning`.

## 2026-03-31 — Fix asyncio_default_fixture_loop_scope deprecation warning

Added `asyncio_default_fixture_loop_scope = function` to `pytest.ini` to silence the pytest-asyncio deprecation warning about unset fixture loop scope.

## 2026-03-31 — Config flow duplicate entry guard + full lint/type pass

Added `async_set_unique_id` + `_abort_if_unique_id_configured` to config flow step 1 so re-adding the same controller URL aborts cleanly. Fixed all pre-existing ruff (unused imports, unsorted imports, SIM105) and mypy errors (DeviceInfo return types, TypedDict context key). Established and validated the full local dev pipeline: pytest (48/48), ruff lint, ruff format, mypy — all clean on Windows. Added `tests/test_config_flow.py` with 4 tests. Removed completed item from TODO.md.

## 2026-03-31 — Developer guide + TODO cleanup

Created `DEVELOPING.md` covering local setup, venv, running tests, linting, adding categories, manual HA testing, CI overview, and branching conventions. Removed completed items from `TODO.md` and stripped numbering from all remaining items so the list is worked top-to-bottom.

## 2026-03-31 — TODO #2: Diagnostics platform

Added `diagnostics.py` — exposes per-category webhook URLs via HA's built-in diagnostics UI so users can copy them into UniFi Alarm Manager without hunting through logs. Passwords and API keys are redacted. Also fixed a pre-existing import bug (`Request` from `aiohttp.web` not `homeassistant.core`), set `homeassistant: 2026.1.0` minimum in manifest, and fixed a flaky coordinator test. All 44 tests pass.

## 2026-03-31 — Project conventions established

Set up core workflow conventions:
- Always show diff and commit when a task is complete
- Always add tests for new functionality; tests must pass before committing
- Maintain this HISTORY.md log (appended after each task, date/time prefixed)
- Keep memories, history, and TODOs local to the repo for portability
