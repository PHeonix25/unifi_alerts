# History

## 2026-04-10 — Pre-release v1pre2: 4 blockers resolved (4 new tests, 238 total)

Four issues surfaced during v1pre1 testing resolved across targeted commits.

### `unifi_client.py` — UCG-Ultra login: dual-path fallback in `_login_userpass`
- UCG-Ultra (and some other UniFi OS devices) do not return `x-csrf-token` on `GET /`, causing `_detect_unifi_os()` to return a false negative. The client then tries `/api/login` (classic path) instead of `/api/auth/login` (UniFi OS path), which returns 401.
- `_login_userpass` now tries both paths in order (primary based on detection result, then the alternate) and only raises `InvalidAuthError` after both fail. This makes auth resilient to OS-detection misses.
- `InvalidAuthError` gained a `login_url` keyword attribute (already added to `_verify_api_key`; now also populated by `_login_userpass`) so the failing endpoint is surfaced in error messages.
- 2 new tests: `test_invalid_auth_error_carries_login_url`, `test_fallback_path_succeeds_on_ucg_ultra`.

### `__init__.py` — Webhook URLs demoted from INFO to DEBUG
- Full webhook URLs were written to HA logs at INFO level and exposed in routine bug reports. Now logs only the count at INFO; full URLs at DEBUG.
- No new tests (logging level is an internal concern).

### `config_flow.py` — Config flow session always closed in `try/finally`
- `async_create_clientsession` created a session per flow run. `client.close()` only issued an HTTP logout request but left the underlying aiohttp session open, leaking connection-pool resources.
- Session is now created before a `try/finally` block and `await session.close()` is always called regardless of auth outcome. The `client.close()` call (redundant logout on a temp session) was removed.
- 1 new test: `test_config_flow_session_closed_on_auth_error`.

### `config_flow.py` + `strings.json` + `translations/en.json` — At-least-one-category validation
- If the user unchecked every category, setup completed silently with zero entities. Both `async_step_categories` (initial setup) and `async_step_init` (options flow) now reject an empty selection with an `at_least_one_category` error.
- Error string added to both `strings.json` and `translations/en.json`.
- 1 new test: `test_categories_all_disabled_shows_error`.

### `TODO.md` cleanup
- Removed resolved items from the backlog: UCG-Ultra blocker, webhook URL logging, session leak, category validation, and two v1.0.0 quick-wins that were applied but never removed (`CONF_VERIFY_SSL` raw string, `diagnostics.py __import__`).


## 2026-04-09 — docs: align all documentation with new tooling and processes

Full documentation pass to reflect the Makefile, requirements-dev.txt, pre-push
hook, and HACS pre-flight validator added in recent commits. Goal: no developer
should need to read the git log to understand how to set up or validate locally.

### CLAUDE.md
- Repository layout updated to include `Makefile`, `requirements-dev.txt`,
  `.githooks/pre-push`, and `scripts/validate_hacs.py` with descriptions.
- `strings.json` and `translations/en.json` entries note that CI enforces parity.
- Working style: replaced "run tests and ruff before committing" with "run
  `make check` before committing" (single command, catches everything).
- "Before making changes" section lists all five checks `make check` runs.
- Pre-push hook section and hook install command consolidated at the bottom.

### README.md
- Contributing section expanded from 2 lines to a full developer workflow:
  clone → `git config core.hooksPath .githooks` → `make setup` → `make check`.
- CI pipeline table explaining every job and what it guards.
- Key rules table (manifest dependencies, strings drift, async, no YAML, token
  auth) so contributors know the sharp edges before opening a PR.

### TESTING.md
- Full rewrite. Replaces hardcoded `pip install` with `make setup` /
  `requirements-dev.txt`. Adds `make` target table as the primary interface.
- Documents pre-push hook and that `--no-verify` must not be used.
- Adds translation drift check and HACS pre-flight to the "other checks" list.
- Notes `make_hass()` / `make_entry()` as canonical conftest helpers.
- Renamed "Adding a test for a new category" → "Adding a test for a new event
  key" (more accurate).

### HOMEASSISTANT.md
- Translations section updated: "must be kept in sync" → "drift is caught
  automatically by CI and the pre-push hook", with details of where.

### ARCHITECTURE.md
- Added "Tooling and validation" section documenting `scripts/validate_hacs.py`,
  `Makefile`, and `requirements-dev.txt` so the repo layout is fully explained.

---

## 2026-04-09 — chore: close remaining local dev tooling gaps

Four gaps between local validation and what CI actually runs:

1. **mypy missing from pre-push hook** — CI ran mypy; the hook didn't. Added
   `.venv/bin/mypy custom_components/unifi_alerts --ignore-missing-imports` to
   `.githooks/pre-push` so type errors are caught before push.

2. **`strings.json` ↔ `translations/en.json` drift unchecked** — no guard
   anywhere. Added a `diff` step to the pre-push hook (exits 1 on mismatch) and
   a matching CI step in the `lint` job. Removed the corresponding TODO/ROADMAP
   entry; it is now enforced automatically.

3. **No `requirements-dev.txt`** — the venv setup command in CLAUDE.md was
   hardcoded and diverged from what CI installs (CI included `homeassistant` for
   mypy stubs; local didn't). Created `requirements-dev.txt` with the union of
   all CI deps. Updated CI lint and test jobs to use it. Updated CLAUDE.md to
   point to `make setup` / `pip install -r requirements-dev.txt`.

4. **No `Makefile`** — multiple manual commands were documented in CLAUDE.md.
   Added `Makefile` with: `setup`, `lint`, `typecheck`, `validate`, `test`, and
   `check` (default) targets. Updated CLAUDE.md's "Before making changes" section
   to lead with `make check`.

`make check` now runs lint + typecheck + HACS preflight + translation drift +
tests in one command. 234 tests pass, all checks clean.

---

## 2026-04-09 — chore: add HACS manifest pre-flight validator and pre-push hook

Root cause of the CI failure that let `"webhook"` slip into `dependencies`: the
only local checks were ruff and pytest; neither exercises the HACS action rules.

Added three things to close the gap:

- **`scripts/validate_hacs.py`** — standalone Python script that replicates the
  HACS action's key manifest checks: required fields, version format, iot_class
  validity, and the core-integration guard on `dependencies`. Catches the exact
  class of mistake that broke CI. No Docker or GitHub required.

- **`ci.yml` — `hacs-preflight` job** — runs `validate_hacs.py` in CI *before*
  the real HACS action job (`needs: hacs-preflight`). Fast feedback (pure Python,
  no container pull) and a second opinion alongside the authoritative check.

- **`.githooks/pre-push`** — tracked git hook that runs HACS preflight, ruff
  lint, ruff format, and pytest before every `git push`. One-time setup:
  `git config core.hooksPath .githooks`. Documented in CLAUDE.md.

---

## 2026-04-09 — hotfix: revert manifest webhook dependency (broke HACS CI)

The `"dependencies": ["webhook"]` added in the previous commit caused the HACS validator to fail CI. hassfest accepts HA core built-ins in `dependencies`, but the HACS action rejects them — it only allows entries that are installable external integrations.

Reverted `manifest.json` back to `"dependencies": []`. Added a non-negotiable constraint to `CLAUDE.md` to prevent recurrence: never list HA core built-ins in `dependencies`. Updated `ROADMAP.md` to mark the item as "won't do" with the reason.

---

## 2026-04-09 — v1.1.0 quick wins: manifest webhook dependency + demote URL logging

Two small v1.1.0 items from the roadmap addressed together:

### `manifest.json` — declare `"webhook"` dependency
The integration relies on `homeassistant.components.webhook` being loaded, but `manifest.json` had an empty `"dependencies": []`. Added `"webhook"` so hassfest and HA's component loader see the explicit dependency. No behaviour change at runtime (HA loads webhook early anyway), but makes the dependency discoverable.

### `__init__.py` — demote webhook URL logging from INFO to DEBUG
Full webhook URLs (including the `?token=` bearer secret) were written to HA logs at INFO level on every startup. Log files are routinely shared in bug reports, which would expose the URL even though webhooks are local-only. Changed to: log only the count of registered webhooks at INFO, and emit the full URLs at DEBUG for developers who need them.

No test changes needed — 234 tests all pass. Lint clean.

---

## 2026-04-09 — Test coverage expansion: 5 new test files, 103 new tests (233 total)

Addressed all major coverage gaps identified in a structured analysis of the codebase. Previous suite: 130 tests. New suite: 233 tests (+103). All passing, lint clean.

### New: `tests/test_webhook_handler.py` (15 tests)
`WebhookManager` had zero test coverage — this is the entire real-time alert path.
- `TestRegisterAll` (6 tests): registers one webhook per enabled category; skips disabled categories; URL includes `?token=` when secret set; no token suffix when secret empty; `_registered` list populated; returns `{category: url}` dict.
- `TestUnregisterAll` (3 tests): calls `async_unregister` for each registered ID; clears `_registered` after; suppresses exceptions silently.
- `TestMakeHandler` (6 tests): valid token → push callback called with correct category/alert; missing token → HTTP 401, callback not called; wrong token → HTTP 401, callback not called; no secret configured → accepts any request; malformed JSON → falls back to empty dict (alert still dispatched with "Unknown alert"); well-formed payload → all alert fields populated correctly.

### New: `tests/test_init.py` (14 tests)
`async_setup_entry` / `async_unload_entry` / `_async_update_listener` had zero coverage.
- `TestAsyncSetupEntry` (7 tests): happy path returns True; stores coordinator/webhook IDs/unregister callable in `hass.data`; auth failure → `ConfigEntryNotReady`; first-refresh failure → `ConfigEntryNotReady`; `verify_ssl=False` logs SSL warning; `verify_ssl=True` produces no warning; platforms forwarded via `async_forward_entry_setups`.
- `TestAsyncUnloadEntry` (5 tests): returns True on success; calls `coordinator.async_shutdown()`; calls `unregister_all()`; calls `client.close()`; when platform unload fails returns False and skips all teardown (correct teardown ordering guarded).
- `TestAsyncUpdateListener` (1 test): calls `hass.config_entries.async_reload(entry.entry_id)`.

### Extended: `tests/test_unifi_client.py` (+25 tests, was 19)
- `TestFetchAlarms` (5 tests): returns only non-archived alarms; filters archived alarms; HTTP 401 raises `InvalidAuthError` and clears `_authenticated`; `ClientConnectionError` raises `CannotConnectError`; unauthenticated client calls `authenticate()` before fetching.
- `TestCategoriseAlarms` (3 tests): groups alarms by category; skips unclassifiable keys; empty alarm list returns `{}`.
- `TestAuthenticate` (3 tests): API key path used when `auth_method=apikey`; API key falls back to userpass when key invalid and method not explicit; explicit `auth_method=apikey` does not fall back.
- `TestClose` (4 tests): userpass posts to `/api/logout`; UniFi OS userpass posts to `/api/auth/logout`; API key auth skips logout; unauthenticated skips logout.

### Extended: `tests/test_coordinator.py` (+9 tests, was 19)
- `TestPollingErrorPaths` (4 tests): `InvalidAuthError` triggers one re-auth then retries; `InvalidAuthError` on retry raises `UpdateFailed`; `CannotConnectError` raises `UpdateFailed`; categories absent from poll result get `open_count` zeroed.
- `TestRollupOpenCount` (3 tests): sums `open_count` for enabled categories only; excludes disabled; zero when no alarms.
- `TestAutoClear` (2 tests): `_auto_clear` clears state and notifies listeners after delay; no-op when category is not alerting.

### New: `tests/test_entities.py` (51 tests)
All four entity platforms had zero coverage for their property methods and update logic.
- `TestUniFiCategoryBinarySensor` (11 tests): `is_on` true/false/missing-state; `available` enabled/disabled; `icon` alert/ok; `extra_state_attributes` with alert, without alert, missing state, with `last_cleared_at`; `unique_id` format.
- `TestUniFiRollupBinarySensor` (6 tests): `is_on` delegates to `any_alerting`; icon variants; attributes with/without last alert.
- `TestUniFiCategoryMessageSensor` (8 tests): `native_value` with/without alert/missing state; `available`; `icon`; `extra_state_attributes` with/without alert.
- `TestUniFiCategoryCountSensor` (3 tests): `native_value` reflects `open_count`; zero for missing state; `available`.
- `TestUniFiRollupCountSensor` (3 tests): `native_value` is `rollup_open_count`; attributes with/without last alert.
- `TestUniFiAlertEventEntity` (8 tests): `available` enabled/disabled/missing; `_handle_coordinator_update` fires event only when `alert_count` increases (not on unchanged count); increments `_last_seen_count` correctly; no-op on missing state / missing `last_alert`; event payload contains all required fields.
- `TestUniFiClearCategoryButton` (5 tests): `async_press` cancels pending task, clears state, notifies coordinator, no-op on missing state; `unique_id` format.
- `TestUniFiClearAllButton` (4 tests): clears all alerting categories; skips non-alerting; cancels clear tasks; notifies coordinator exactly once.

### `TODO.md` updated
Replaced the old "Integration tests with the hass fixture" item with a more accurate two-part entry: the remaining integration-test work (end-to-end with real hass fixture) and an "extended coverage" item marked as partially complete (since the plain-mock layer is now covered).

### Environment note
Tests run with `.venv` (Python 3.12, matching CI). Created `.venv` using `python3.12 -m venv .venv` and installed `pytest pytest-asyncio pytest-homeassistant-custom-component aiohttp ruff`.
## 2026-04-08 — CI housekeeping: GitHub Actions upgraded to Node.js 24

- `actions/checkout`: `@v4` → `@v6`
- `actions/setup-python`: `@v5` → `@v6`
- `softprops/action-gh-release`: `@v2` → `@v2.6.1`

All three were generating "Node.js 20 deprecated" warnings in CI output. `home-assistant/actions/hassfest@master` and `hacs/action@main` are Docker-based and unaffected.

## 2026-04-08 — Tagged and released v1-pre1

- Pushed three uncommitted commits from the session to `origin/main`.
- Tagged `v1-pre1` and created a pre-release on GitHub.
- Initial release workflow run failed with `Resource not accessible by integration` — the `GITHUB_TOKEN` lacked `contents: write` permission to upload release assets. Fixed by adding `permissions: contents: write` at the workflow level in `release.yml`.
- Deleted and recreated the tag and release so a fresh workflow run would pick up the permissions fix. Second run succeeded and attached `unifi_alerts.zip`.

## 2026-04-08 — Post-v1 must-fix bugs: 4 items resolved (9 new tests, 130 total)

Four "must-fix" items from the v1-pre backlog resolved across two parallel worktrees, reconciled and committed together.

### `config_flow.py` — user step preserves submitted values on validation error
- `async_step_user` now rebuilds `data_schema` with the submitted `user_input` values as defaults when an auth or connectivity error occurs. Previously the form reset to hardcoded defaults (`https://192.168.1.1`, etc.), forcing the user to re-enter every field.

### `unifi_client.py` — UniFi OS detection and HTTP 400 handling
- `_detect_unifi_os`: changed `allow_redirects=False` → `True` so HTTP→HTTPS redirects (UCG-Ultra) are followed correctly. Removed `or resp.status == 200` from the heuristic — the `x-csrf-token` header is the only reliable signal; any HTTP 200 was incorrectly classifying generic web servers as UniFi OS.
- `_login_userpass`: separated HTTP 400 from 401/403. 400 now raises `CannotConnectError` (wrong endpoint / controller version mismatch — not a credentials problem); 401/403 still raise `InvalidAuthError`. Added `_LOGGER.warning` with the endpoint URL and status on every auth failure.
- `_login_apikey`: added `_LOGGER.warning` with endpoint and status on 401/403.
- `cannot_connect` error string updated to mention URL, port, and SSL settings and point users to HA logs.

### `config_flow.py` + `strings.json` — webhook URLs as copyable form fields
- `async_step_finish`: replaced `description_placeholders` URL list with `vol.Optional` string fields pre-filled with each enabled category's webhook URL. Users can now select and copy individual URLs from the form rather than trying to highlight text in a description block.
- `async_step_init` (options flow): same change — webhook URL fields now appear as copyable form inputs.
- Removed `{webhook_url_list}` placeholder from both step descriptions.

### `strings.json` + `translations/en.json` — SSL warning corrected
- Removed stale `⚠️ SSL verification is disabled by default` sentence from the `user` step description (was accurate when `DEFAULT_VERIFY_SSL = False`; wrong since the default was flipped to `True`).
- New copy: `"SSL verification is enabled by default. Disable it only if your controller uses a self-signed certificate."`
- Added `data` label entries for all `webhook_url_*` fields in both `finish` and `init` steps.

### Tests — 9 new tests (130 total)
- `test_config_flow.py`: `test_user_step_error_preserves_submitted_values`, `test_user_step_initial_load_uses_hardcoded_defaults` (config flow schema fix); updated `test_finish_shows_webhook_urls` and `test_options_init_includes_webhook_urls` to assert schema fields instead of `description_placeholders`.
- `test_unifi_client.py`: `TestDetectUnifiOs` (4 tests — CSRF token present/absent, redirect followed, exception fallback); `TestLoginUserpass` (3 tests — HTTP 400 raises `CannotConnectError`, 401/403 raise `InvalidAuthError`).

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
