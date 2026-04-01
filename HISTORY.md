# History

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
