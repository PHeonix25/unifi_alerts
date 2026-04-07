# History

## 2026-04-07 — v1.0.0 blocking bugs resolved (6 fixes, 10 new tests)

All remaining must-fix items from the v1.0.0 roadmap are now closed. 121 tests passing.

### `models.py` — UTC-aware datetimes everywhere
- Imported `UTC` from `datetime` (Python 3.11+).
- Replaced all three `datetime.now()` calls with `datetime.now(UTC)`: `from_webhook_payload` `received_at`, `from_api_alarm` fallback `received_at` (both the missing-ts and the parse-error branches), and `CategoryState.clear` `last_cleared_at`.
- HA automation time comparisons and entity attribute timestamps are now consistent with HA's own UTC-based clock.

### `config_flow.py` — options flow reads `entry.options` first
- `UniFiAlertsOptionsFlow.async_step_init` now reads `current_enabled`, `current_poll`, and `current_clear` from `entry.options` with a fallback to `entry.data`. Previously it always read from `entry.data`, so any settings saved via the options flow were silently discarded on the next visit to the Configure screen.

### `coordinator.py` — `cancel_clear` + polling does not increment `alert_count`
- Added `cancel_clear(category)` public method: cancels the pending asyncio task for a given category and removes it from `_clear_tasks`.
- Changed the polling code path (`_async_update_data`) to set `state.is_alerting = True` and `state.last_alert` directly instead of calling `state.apply_alert()`. This means `alert_count` is only ever incremented by real webhook-pushed events, not by repeated poll cycles that find the same unarchived alarm. Prevents spurious event entity triggers every poll cycle.

### `button.py` — manual clear cancels the pending auto-clear task
- `UniFiClearCategoryButton.async_press` now calls `self._coordinator.cancel_clear(self._category)` before `state.clear()` so the scheduled auto-clear task cannot fire after a manual clear and accidentally wipe a freshly-arriving alert.
- `UniFiClearAllButton.async_press` now calls `cancel_clear` for each alerting category before clearing its state.

### `__init__.py` — `ConfigEntryNotReady` on startup failure
- Imported `ConfigEntryNotReady` from `homeassistant.exceptions`.
- Auth failure now raises `ConfigEntryNotReady` (instead of returning `False`) so HA schedules a retry on the standard back-off schedule rather than marking the entry as permanently failed.
- `async_config_entry_first_refresh` is now wrapped in `try/except` and re-raises as `ConfigEntryNotReady` so poll failures during setup are also retried.

### Tests — 10 new tests (121 total)
- `test_models.py`: 4 new tests asserting `received_at` and `last_cleared_at` are UTC-aware across all code paths.
- `test_coordinator.py`: `TestCancelClear` (3 tests — cancels task, removes from dict, no-op when absent); `TestPollingPath` (2 tests — polling does not increment `alert_count`, polling does not re-fire when already alerting).
- `test_config_flow.py`: 1 new test asserting options flow schema defaults reflect `entry.options` values over `entry.data` values.

### `pytest.ini` — suppress third-party deprecation warnings
- Added `filterwarnings` to suppress `DeprecationWarning` from `josepy`, `acme`, and `homeassistant.components.http`. All three warnings came from third-party packages pulled in transitively by the `homeassistant` test dependency; none originated in integration code. Test run is now `121 passed, 0 warnings`.

### Documentation
- `ROADMAP.md`: all 6 v1.0 bug items marked `[x]`; status line updated to "v1.0.0 ready".
- `TODO.md`: entire "🔴 Must-fix before V1 tag" section removed (all items resolved).
- `CLAUDE.md`: updated module descriptions for `__init__.py`, `models.py`, `coordinator.py`, and `config_flow.py` to reflect all behavioural changes.

## 2026-04-02 — Security: per-entry webhook bearer token authentication

- `const.py` — added `CONF_WEBHOOK_SECRET = "webhook_secret"`
- `config_flow.py` — generate `secrets.token_urlsafe(32)` on first auth and store in `entry.data`; append `?token=<secret>` to all displayed webhook URLs in both the finish step and options flow
- `webhook_handler.py` — pass secret into `_make_handler()`; reject requests with missing/wrong token with HTTP 401 and a warning log; also removed `"GET"` from `allowed_methods` (was firing spurious alerts on health-check GETs — fixes two v1.0 items in one)
- `diagnostics.py` — added `CONF_WEBHOOK_SECRET` to `_TO_REDACT`; strip `?token=...` from webhook URLs in diagnostics output so secrets are not exposed in shared bug reports
- `tests/test_config_flow.py` — updated two URL tests to include a fake secret in entry data and assert the token appears in displayed URLs
- 111 tests passing

## 2026-04-02 — Security: flip SSL default to True + warn when disabled

- `const.py` — changed `DEFAULT_VERIFY_SSL` from `False` to `True`; secure-by-default, users with self-signed certs must explicitly disable it (UI copy already explains this)
- `__init__.py` — imported `DEFAULT_VERIFY_SSL` for use as fallback; emit `_LOGGER.warning` at setup time when SSL verification is disabled so the security tradeoff is always visible in the HA log
- 111 tests passing

## 2026-04-02 — V1 documentation & UX: 4 required items

- `config_flow.py` — default `network_device` and `network_client` categories to OFF; these fire on every device reboot and every phone joining Wi-Fi respectively, causing immediate alert fatigue for new users
- `strings.json` + `translations/en.json` — rewrote `user` step description with clear API key vs username/password guidance (where to find an API key, which controllers support each method); added SSL verification warning; rewrote `categories` step description with noise warning for chatty categories and plain-English explanations of polling interval and auto-clear timeout; fixed `finish` step description ("Setup is complete" → "click Submit to save") so users don't close the dialog before the entry is created
- `README.md` — made webhook URL retrieval step 5 in the numbered setup list (was a buried afterthought paragraph); added auth method guidance in step 2; added `⚠️ Local network required` callout in Configuring UniFi Alarm Manager
- All 4 v1.0 UX/documentation items checked off in ROADMAP.md (111 tests still passing)

## 2026-04-02 — V1 quick wins: 5 one-liner fixes

- `models.py:33` — replaced `str(payload)` fallback with `"Unknown alert"` to prevent raw webhook payload leaking into alert message and event entity attributes
- `diagnostics.py` — replaced `__import__("logging")` with standard `import logging`; added `CONF_USERNAME` to `_TO_REDACT` so usernames (often email addresses) are redacted in diagnostics output shared in bug reports
- `__init__.py:36` — replaced raw `"verify_ssl"` string with `CONF_VERIFY_SSL` constant
- `hacs.json` — removed contradictory `filename` field (`zip_release: false` makes it unused)
- Updated `test_diagnostics.py` to assert username is now redacted (111 tests passing)
- Checked off all 5 quick wins in `ROADMAP.md`

## 2026-04-02 — Pre-V1 review: add ROADMAP.md and expand TODO with multi-reviewer findings

Three parallel reviews (senior engineer, security architect, product owner) identified 8 blocking items and 4 UX gaps that must be resolved before tagging v1.0.0. Full findings documented in `TODO.md`. Created `ROADMAP.md` chunking all TODOs into v1.0/v1.1/v1.2/v2.0 releases with visual checklists. Added `cd` working-directory convention to `CLAUDE.md`. Updated reference table in `CLAUDE.md` with `ROADMAP.md` entry.

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
