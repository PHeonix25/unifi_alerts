# History

## 2026-04-21 (session 11) — Distinguish re-auth failure from post-re-auth update failure in polling

- **`coordinator.py`**: split the single `except (InvalidAuthError, CannotConnectError)` retry handler into two separate `try/except` blocks — one around `authenticate()` and one around the retried `categorise_alarms()` call.
- Re-auth failures (`InvalidAuthError` or `CannotConnectError` from `authenticate()`) now raise `ConfigEntryAuthFailed` so HA can surface the reauth flow to the user; log message is "Re-authentication failed; credentials may have changed".
- Post-re-auth poll failures (`CannotConnectError` from the second `categorise_alarms()`) now raise `UpdateFailed` with "Cannot reach UniFi controller after re-authentication" — clearly distinguishable from the first-pass "Cannot reach UniFi controller" message.
- Added `ConfigEntryAuthFailed` import from `homeassistant.exceptions`.
- **`tests/unit/test_coordinator.py`**: replaced the old `test_invalid_auth_on_retry_raises_update_failed` test with three new tests in `TestPollingErrorPaths`: re-auth `InvalidAuthError` → `ConfigEntryAuthFailed`; re-auth `CannotConnectError` → `ConfigEntryAuthFailed`; re-auth succeeds but retry fails → `UpdateFailed` containing "after re-authentication".
- All 282 tests pass; lint, mypy, HACS preflight, and translation drift checks clean.

---

## 2026-04-21 (session 11) — README: Lovelace card and automation examples

- Added `## Examples` section to `README.md` replacing the minimal one-liner automation stub.
- Lovelace snippet: `entities` card mixing `binary_sensor.unifi_alerts_any_alert`, five per-category binary sensors, and `sensor.unifi_alerts_total_open_alerts`; only uses entity IDs actually produced by the integration.
- Automation snippet: `platform: state` trigger on `event.unifi_alerts_security_threat` (correct for HA `EventEntity`); documents all seven event-data attributes (`message`, `category`, `device_name`, `alert_key`, `severity`, `site`, `received_at`) sourced directly from `event.py:_handle_coordinator_update`.
- Clarified that UniFi Alerts uses HA Event entities (not the hass event bus) — the `event_type` used by `_trigger_event` is `alert_received` and is a per-entity event type, not a bus event.
- `TODO.md`: removed both nice-to-have items for Lovelace and automation README examples.
- `ROADMAP.md`: ticked both v1.1.0 UX / Documentation items.

---

## 2026-04-21 (session 11) — Add info.md HACS display page

- Created `info.md` at the repository root as the HACS UI display card (56 lines).
- Covers features, alert categories, requirements, quick setup, and links; kept concise and scannable per HACS conventions.
- Ticked `[ ] Create info.md` in `ROADMAP.md` v2.0.0 prerequisites.
- Noted info.md completion in `TODO.md` HACS default repository submission entry.

---

## 2026-04-21 (session 11) — Pin CI action versions to commit SHAs

- Pinned all `uses:` lines across `ci.yml`, `release.yml`, and `version-check.yml` to full 40-character commit SHAs.
- Actions pinned: `actions/checkout@v6`, `actions/setup-python@v6`, `home-assistant/actions/hassfest@master`, `hacs/action@main`, `softprops/action-gh-release@v2.6.1`.
- Each pinned line includes a trailing `# <tag-or-ref>` comment so the human-readable version remains visible.
- Eliminates supply-chain risk from floating `@master` / `@main` refs silently picking up breaking upstream changes.
- No source code changes; `make check` passes (only YAML workflow files modified).
- Removed the `### CI action versions are floating` entry from `TODO.md`; ticked the corresponding item in `ROADMAP.md` v1.1.0 Tech debt.

---

## 2026-04-21 (session 11) — Add clear_category and clear_all services

- Created `custom_components/unifi_alerts/services.py`: defines `SERVICE_CLEAR_CATEGORY` and `SERVICE_CLEAR_ALL` with voluptuous schemas; handlers call `coordinator.cancel_clear(category)`, mutate `state.clear()`, and dispatch `coordinator.async_set_updated_data()` — matching button entity behaviour exactly.
- Created `custom_components/unifi_alerts/services.yaml`: HA service descriptions with `selector.select` for the `category` field (all 7 slugs listed) and an optional `entry_id` `selector.text` on both services.
- Wired services into `custom_components/unifi_alerts/__init__.py`: `async_register_services(hass)` called after platform setup (idempotent, safe for multiple entries); `async_unregister_services(hass)` called in `async_unload_entry` only when `hass.data[DOMAIN]` is empty (i.e. last entry is gone).
- Added `"services"` top-level key to both `custom_components/unifi_alerts/strings.json` and `custom_components/unifi_alerts/translations/en.json` (kept identical — CI drift check verified).
- Created `tests/unit/test_services.py` with 28 new tests covering: schema validation (valid/invalid category, missing required field, optional entry_id); `clear_category` clears state, cancels clear task, dispatches listeners, skips non-alerting, filters by entry_id; `clear_all` clears all alerting categories with one dispatch per coordinator, skips non-alerting, filters by entry_id; registration idempotency; unregistration only on last-entry unload.
- All 308 tests pass (280 pre-existing + 28 new); lint, mypy, HACS preflight, and translation drift checks all clean.
- `TODO.md`: removed `### Service calls` entry under Nice-to-have.
- `ROADMAP.md`: ticked `[ ] Service calls: ...` to `[x]` under v1.1.0 Tech debt.

---

## 2026-04-21 (session 11) — Options flow: edit credentials and controller URL without re-adding integration

### Goal

Close the `Options flow: allow credentials and controller URL to be updated without re-adding integration` v1.1 roadmap item.  Previously the only way to change credentials or the controller URL was to delete the integration and set it up again from scratch — a painful workflow whenever the UniFi admin password rotated or the controller was moved to a new address.

### `config_flow.py` — new `async_step_credentials` step in the options flow

Added a new first step to `UniFiAlertsOptionsFlow` that optionally updates credentials before the existing categories step.  All fields are optional:

- `CONF_CONTROLLER_URL`, `CONF_USERNAME`, `CONF_PASSWORD`, `CONF_API_KEY` — blank values mean "leave unchanged".
- `CONF_VERIFY_SSL` — always defaulted from the current entry value.

Router step (`async_step_init`) now delegates straight to `async_step_credentials`.  The legacy options-flow logic (category toggles, poll interval, clear timeout, site, webhook URL display) was renamed to `async_step_categories` and is reached either after a successful credentials update or when the credentials step is skipped (all fields blank).

Validation flow for a non-blank submission:

1. Merge the new fields over the existing `entry.data` to produce a test credential dict.
2. Validate the URL scheme (`http`/`https` only — same check as initial setup).
3. Construct a temporary `UniFiClient`, call `authenticate()` and `fetch_alarms()`.  Surface `invalid_auth`, `cannot_connect`, or `unknown` as form errors.
4. If a new URL would collide with another configured entry for this domain, abort with `already_configured`.
5. On success, call `hass.config_entries.async_update_entry(...)` with the merged `data`, updating `CONF_AUTH_METHOD` and `CONF_IS_UNIFI_OS` from the validated client too.

Only fields the user actually filled in are overwritten — blank fields preserve the existing values.  This means a user can change just the password without having to re-enter the URL or API key.

### `strings.json` / `translations/en.json` — new options-flow strings

Added `options.step.credentials` (title, description, field labels) and the existing `options.error.invalid_auth`, `options.error.cannot_connect`, `options.error.invalid_url_scheme`, `options.error.unknown`, and `options.abort.already_configured`.  Both files remain byte-identical (CI enforces this).

### Tests

Added `TestOptionsFlowCredentials` in `tests/unit/test_config_flow.py` covering:

- All fields blank → credentials step skipped, flows straight to categories.
- Valid password update → `entry.data[CONF_PASSWORD]` overwritten, auth_method persisted.
- Valid URL + API key update → both persisted, old username left untouched.
- Invalid URL scheme → form re-shown with `invalid_url_scheme` error, no `async_update_entry` call.
- Invalid auth → `invalid_auth` error on form.
- URL collision with existing entry → abort with `already_configured`.
- Verify SSL toggle → persisted even when other fields blank (treated as credentials change only if truly blank).

Test count: 280 → 287 (+7).  `make check` passes cleanly.

### Why this matters

This is the last UX paper-cut from v1.0.  Combined with the config-entry repair flow (session 11a) it means credentials can now be rotated or corrected entirely in-place: HA surfaces a repair notification on auth failure, the user clicks through to a re-auth form, or they can proactively open Options → Configure to pre-emptively rotate a password.  No more "delete and re-add the integration" dance.

---

## 2026-04-15 (session 10) — v1.1 security: credentials leak + unbounded webhook body

### Goal

Close the two remaining security items from the v1.1.0 roadmap. Both were non-blocking for v1.0 but important for production quality.

### `unifi_client.py` — credentials leak via exception messages

`fetch_alarms()` and `_login_userpass()` both had `raise CannotConnectError(str(err)) from err`. Some `aiohttp.ClientError` subclasses embed the full request URL in their `__str__()` representation — which can include usernames, passwords, or API keys when the client was constructed with credentials in the URL. Changed both sites to `raise CannotConnectError(type(err).__name__) from err` so only the exception class name appears in HA logs.

### `const.py` — new `WEBHOOK_MAX_BODY_BYTES` constant

Added `WEBHOOK_MAX_BODY_BYTES = 8192` (8 KB) in the defaults section. 8 KB is far larger than any real UniFi alert payload and provides a generous safety margin.

### `webhook_handler.py` — bounded webhook body read

Replaced `payload = await request.json()` (unbounded) with a three-step pattern:
1. `raw = await request.content.read(WEBHOOK_MAX_BODY_BYTES + 1)` — reads at most 8 193 bytes.
2. If `len(raw) > WEBHOOK_MAX_BODY_BYTES` → log warning and return HTTP 413, callback not called.
3. `payload = json.loads(raw.decode())` with `except (json.JSONDecodeError, UnicodeDecodeError, TypeError)` falling back to `{}`.

Added `WEBHOOK_MAX_BODY_BYTES` to the import from `const`.

### Tests

- `test_unifi_client.py`: added `test_client_error_message_is_class_name_not_url` in `TestFetchAlarms` — asserts that a `ClientConnectionError` with a URL-containing message does not propagate the URL into `CannotConnectError.args[0]`; added `test_login_client_error_message_is_class_name_not_url` in `TestLoginUserpass` with the same assertion for the `_login_userpass` path.
- `test_webhook_handler.py`: updated `make_request()` helper to mock `req.content.read` (returns `json.dumps(body).encode()`) instead of `req.json`; updated `test_malformed_json_uses_empty_dict_fallback` to pass raw invalid bytes via `content.read`; added `test_oversized_body_returns_413` — feeds `WEBHOOK_MAX_BODY_BYTES + 1` bytes and asserts HTTP 413 and no callback invocation. Added `import json` and `WEBHOOK_MAX_BODY_BYTES` to imports.

All 280 tests pass; lint, mypy, HACS preflight, and translation drift checks clean.

### Documentation

- `ROADMAP.md`: ticked both security items `[x]` in the v1.1.0 section.
- `TODO.md`: removed both resolved items from the Known issues section.

---

## 2026-04-15 (session 9) — Move to two-branch model; add versioning CI enforcement

### Goal

Transition from trunk-driven development to a two-branch model (`main` = stable, `dev` = active pre-release development), add CI that enforces the correct version format on each branch, and update release automation so tags drive publishing rather than manual GitHub UI releases.

### `.github/workflows/version-check.yml` (new)

New workflow triggered on push and PR to `main` and `dev`. Extracts the version from `manifest.json` and:
- On `main` (or a PR targeting `main`): validates the version matches `^[0-9]+\.[0-9]+\.[0-9]+$` (stable semver, no suffix). Fails with a clear message if a pre-release suffix is present.
- On `dev` (or a PR targeting `dev`): validates the version matches `^[0-9]+\.[0-9]+\.[0-9]+-pre[0-9]+$`. Fails if the version is stable or uses a non-standard suffix.
- Feature branches (`claude/*`, `feature/*`) are not checked — any version is accepted.

### `.github/workflows/release.yml` (updated)

Switched trigger from `release: types: [published]` to `push: tags` matching `v*.*.*` (stable) and `v*.*.*-pre*` (pre-release). New behaviour:
1. Detects whether the tag is a pre-release by checking for a `-pre` suffix.
2. Validates that the pushed tag version exactly matches the `version` field in `manifest.json`. Fails fast with a descriptive error if they diverge.
3. Creates the release zip as before.
4. Calls `softprops/action-gh-release` with `prerelease: true` for pre-release tags and `prerelease: false` for stable tags — the GitHub release type is now automatic, not manual.

### `.github/workflows/ci.yml` (updated)

Added `dev` to `pull_request.branches` so CI runs on PRs targeting `dev` as well as `main`. (Push triggers for `dev` were already present.)

### `manifest.json` (version bump)

Bumped version from `1.0.0-pre3` to `1.0.0`. All v1.0.0 blockers were resolved in sessions 1–8; this marks the first stable release on `main`.

### `dev` branch (created)

Created `dev` branch from the post-merge state of `main`. Bumped `manifest.json` on `dev` to `1.1.0-pre1` to start the next development cycle. All v1.1.0 work (security hardening, reliability, QA) proceeds on `dev` under that version prefix.

### Documentation

- **`CLAUDE.md`**: added "Branching strategy and versioning" section documenting the two-branch model, version conventions, the release workflow diagram, CI enforcement, and recommended branch protection rules. Updated "Working style" to say pull `dev` (not `main`) at the start of each session, and to note that `main` is only updated via PRs.
- **`ROADMAP.md`**: updated current status blurb; marked v1.0.0 as released; added an "Infrastructure" subsection to v1.1.0 ticking off the branch model and CI versioning work.
- **`TODO.md`**: no items removed or added (branch setup was not in the backlog; all relevant changes are now live).

### No test changes

No production code was modified. CI workflow changes are validated by the GitHub Actions runner, not by the local pytest suite.

## 2026-04-11 (session 8) — Fix silent api.err.InvalidObject: persist UniFi OS detection + validate alarm endpoint at setup

### Root cause

After a successful config flow, the polling path returned `{"meta":{"rc":"error","msg":"api.err.InvalidObject"},"data":[]}` from `/proxy/network/api/s/default/alarm?limit=200`. Two bugs combined to make this silent and unrecoverable:

1. `fetch_alarms()` never validated `meta.rc` — `resp.raise_for_status()` only checks the HTTP status code, which is 200 even for API-level errors. The code then called `data.get("data", [])` on the error payload (which returns `[]`) and silently returned an empty list.
2. `_is_unifi_os` was re-detected on every `authenticate()` call and never persisted to `entry.data`. If detection flips between config-flow time and post-install (e.g. a reverse proxy strips `x-csrf-token` intermittently), the client silently uses the wrong API path prefix, which causes `api.err.InvalidObject` from the controller.

### `const.py` — new `CONF_IS_UNIFI_OS` constant

Added `CONF_IS_UNIFI_OS = "is_unifi_os"` to the config entry key constants. This value is now stored in `entry.data` after setup and read back by `UniFiClient` on every subsequent load.

### `unifi_client.py` — three changes

1. **Import `CONF_IS_UNIFI_OS`** from `.const`.
2. **Pre-load `_is_unifi_os` from config**: changed `self._is_unifi_os: bool = False` to `self._is_unifi_os: bool | None = config.get(CONF_IS_UNIFI_OS)`. `None` means "not yet detected"; a stored `True/False` skips detection on the next `authenticate()` call.
3. **Skip re-detection when already known**: in `authenticate()`, wrapped `self._is_unifi_os = await self._detect_unifi_os()` in `if self._is_unifi_os is None:`. Backward-compatible — existing entries without the key fall back to fresh detection as before.
4. **Validate `meta.rc` in `fetch_alarms()`**: after `data = await resp.json()`, check `data.get("meta", {}).get("rc") != "ok"` and raise `CannotConnectError(f"UniFi API error: {msg}")` if the API reports an error. Propagates through the coordinator's existing `CannotConnectError → UpdateFailed` path and surfaces in the HA UI.

### `config_flow.py` — validate alarm endpoint + store detected path

1. **Call `await client.fetch_alarms()`** immediately after `await client.authenticate()` in `async_step_user()`. The existing `except CannotConnectError` handler catches any API error and shows `"cannot_connect"` to the user before the entry is created.
2. **Store `client._is_unifi_os`** in `self._credentials` as `CONF_IS_UNIFI_OS`. This flows through to `self._entry_data` (step 2) and then to `entry.data` (step 3), ensuring the detected path is stable for the lifetime of the entry.
3. Added `CONF_IS_UNIFI_OS` to the import block.

### `UNIFI.md` — document error response envelope

Added an "Error responses" subsection to "Response structure" documenting the `meta.rc`/`meta.msg` pattern and noting that `fetch_alarms()` raises `CannotConnectError` on non-`"ok"` values.

### Tests

- `test_unifi_client.py`: updated all `fetch_alarms()` / `categorise_alarms()` test response bodies to include `"meta": {"rc": "ok"}`. Added `test_api_error_response_raises_cannot_connect` to `TestFetchAlarms`. Added `TestIsUnifiOsPersistence` class with five tests covering: `None` init when key absent, `True`/`False` pre-load from config, skip-detection when pre-loaded, and run-detection when `None`.
- `test_config_flow.py`: updated `test_unique_id_set_to_normalised_url` and `test_no_duplicate_proceeds_to_categories` to mock `fetch_alarms` (now called in step 1). Added `test_step_user_fetch_alarms_failure_shows_cannot_connect` and `test_conf_is_unifi_os_stored_in_credentials`.

## 2026-04-10 (session 7) — Release prep: ROADMAP/TODO tidy-up, version bump to 1.0.0-pre3

Prepared the repository for the `1.0.0-pre3` tag.

### `manifest.json` — version bumped to `1.0.0-pre3`

Changed `"version"` from `"1.0.0"` to `"1.0.0-pre3"` to reflect the pre-release nature of this build.

### `ROADMAP.md` — ticked off all completed items; restructured versions

- Ticked `[x]` all items completed in sessions 1–6 that were still shown as `[ ]`:
  - UCG-Ultra OS detection (two-stage fallback probe, session 3)
  - Config flow API key path instructions (sessions 3 & 4)
  - SSRF scheme validation (session 3)
  - Alarm endpoint pagination / `limit=200` (session 3)
  - Full integration tests with `hass` fixture (sessions 5 & 6)
- Removed the `v1.2.0` section — scope is not yet defined; its non-deferred items (repair flow, options re-auth, Lovelace example, automation example, service calls) promoted into `v1.1.0`.
- Added a `### QA` subsection to `v1.1.0` for the update-in-place verification task.
- Updated the "Current status" note from "v1pre2 ready to tag" to "v1.0.0-pre3 ready to tag".

### `TODO.md` — synced with ROADMAP

- Added two items that were in ROADMAP v1.1.0 but absent from TODO:
  - Unbounded webhook body stored in memory (`webhook_handler.py:86`)
  - Credentials leak risk via exception messages in logs (`unifi_client.py:105,181`)
- Added missing items promoted from v1.2.0: automation example in README; Lovelace/dashboard example already present.
- No items removed — all prior completed items were already cleaned up in sessions 3–6.

---

## 2026-04-10 (session 6) — Fix auto-clear race condition and lint cleanup (269 tests)

Addressed PR review feedback on the integration tests introduced in session 5.

### Auto-clear race condition fixed (`tests/integration/test_auto_clear.py`)

`_schedule_clear()` uses `hass.async_create_background_task`, which creates tasks intentionally **not** awaited by `hass.async_block_till_done()`. The original tests for `test_auto_clear_resets_sensor_to_off` and `test_auto_clear_also_resets_rollup_sensor` relied on a single `async_block_till_done()` call to complete the background task, making them racey/flaky.

Fix: call `await hass.async_block_till_done(wait_background_tasks=True)` so HA drains the background task queue, followed by a second `await hass.async_block_till_done()` to flush HA state-write callbacks the coordinator triggers. Updated the module docstring and `TESTING.md` to document this two-call pattern.

### Lint fixes (`tests/unit/` and `tests/integration/`)

Seven pre-existing lint errors were carried over when test files were moved from `tests/` to `tests/unit/` in session 5. Fixed with `ruff check --fix` + `ruff format`:

- Removed unused `get_coordinator` import from `test_lifecycle.py`
- Removed unused `aiohttp` import from `test_config_flow.py`
- Fixed import sort order in `conftest.py`, `test_config_flow.py`, `test_diagnostics.py`, `test_webhook.py`, `test_coordinator.py`, `test_init.py`

All 269 tests pass, all lint/typecheck/HACS checks clean.

---

## 2026-04-10 (session 5) — Integration tests with real `hass` fixture (269 tests)

Added a full integration test suite using `pytest_homeassistant_custom_component`'s `hass` fixture. Tests exercise the real HA setup lifecycle without hitting a real controller. All 269 tests pass.

### Test directory restructure

Moved all existing unit tests from `tests/` root into `tests/unit/` and added a peer `tests/integration/` directory. Each has its own `conftest.py`.

- `tests/unit/` — no `__init__.py` so pytest adds it to `sys.path`; bare `from conftest import` works unchanged. Moved all 9 existing test files here.
- `tests/integration/` — has `__init__.py` enabling relative imports (`from .conftest import ...`).
- Updated `pytest.ini` to add `markers = integration: ...`.

### `coordinator.py` — background task for auto-clear

Changed `_schedule_clear` to use `hass.async_create_background_task` instead of `hass.async_create_task`. Background tasks do **not** block `hass.async_block_till_done()`, preventing 30-second test timeouts caused by the 1800-second auto-clear sleep.

Consequence: updated all 10 occurrences of `hass.async_create_task = _create_task` in `tests/unit/test_coordinator.py` to also mock `hass.async_create_background_task = _create_task`.

### Integration tests — 16 new tests

**`tests/integration/conftest.py`**: `entry` fixture sets up HTTP/webhook infrastructure, instantiates the config entry, and unloads on teardown. `mock_unifi_client` patches `UniFiClient` so no HTTP calls escape. `_prime_pycares_shutdown_thread` (session-scoped) constructs `aiodns.DNSResolver(...)` to warm up the resolver stack before `verify_cleanup` captures its thread baseline; no-op when `aiodns` is absent.

**`tests/integration/test_lifecycle.py`** (6 tests):
- Binary sensors created for all categories
- Rollup binary sensor created
- Count sensors created for all categories
- Rollup count sensor created
- Clear buttons created
- Options flow disabling a category makes its sensor unavailable

**`tests/integration/test_auto_clear.py`** (4 tests):
- Push alert → binary sensor ON
- Auto-clear fires (asyncio.sleep patched to AsyncMock) → sensor OFF
- Auto-clear also resets rollup sensor
- Push without auto-clear → sensor stays ON

**`tests/integration/test_webhook.py`** (6 tests):
- Valid POST + correct `?token=` → binary sensor ON
- Valid POST also flips rollup sensor
- Missing token → 401, sensor stays OFF
- Wrong token → 401, sensor stays OFF
- GET request → no alert dispatched
- No-secret config → POST accepted without token

### Thread-1 / aiodns investigation

`Thread-1 (_run_safe_shutdown_loop)` is created by pycares internally when `aiohttp.TCPConnector` builds a `DefaultResolver` (aiodns → pycares). This happens when the `entry` fixture sets up the HTTP server, AFTER `verify_cleanup` captures its `threads_before` snapshot. The session-scoped `_prime_pycares_shutdown_thread` fixture constructs `aiodns.DNSResolver(...)` via the public API to warm up the resolver stack before any test runs, ensuring Thread-1 is already alive in `verify_cleanup`'s baseline. The fixture is a no-op when `aiodns` is not installed.

### `caplog` circular dependency fix

`pytest_homeassistant_custom_component` defines `@pytest.fixture(name="caplog")` without `override=True`, causing a circular-dependency error in pytest ≥ 8. The 3 affected tests (`test_push_to_unknown_category_logs_warning`, `test_ssl_disabled_logs_warning`, `test_ssl_enabled_no_warning`) were refactored to use `mock.patch` on `_LOGGER` instead of the `caplog` fixture.

### `TESTING.md` — fully updated

Documented the `tests/unit/` + `tests/integration/` structure, integration test fixtures, pycares thread behaviour, and how to run each suite.

### `TODO.md` — resolved items removed

Removed: "Integration tests with the `hass` fixture" and "Remaining test coverage gaps" (end-to-end integration tests).

---

## 2026-04-10 (session 4) — API key docs, test coverage gaps, multi-site support (253 tests)

Addressed three more high-priority items from `TODO.md`. All checks pass.

### `TODO.md` — stale item cleanup
- Removed four items already resolved in prior sessions whose removal was recorded in HISTORY.md but not actually applied to the file: "Config flow repopulates old username/password", "API key and password fields are plaintext", "Tighten bare except Exception in webhook handler", "Disabled category open_count is still updated by polling".

### API key instructions — config flow, README, UNIFI.md
- `strings.json` + `translations/en.json`: replaced the single hard-coded path ("Settings → Admins & Users → API Keys") with a version-agnostic instruction noting the path varies by firmware and listing both common paths ("Settings → Admins & Users → API Keys" or "Integrations → New API Key"). Links to README for device-specific instructions.
- `README.md`: updated setup step 2 to reference new "Generating an API key" section; added that section with a table of per-firmware navigation paths and a note to use a dedicated non-MFA account.
- `UNIFI.md`: removed two stale references to the now-resolved API key path bug in `TODO.md`.

### Missing test coverage — 9 new tests
- `test_config_flow.py`: added `test_categories_step_saves_poll_interval_and_clear_timeout`, `test_categories_step_accepts_boundary_poll_intervals` (parametrised: 10, 3600), `test_categories_step_accepts_boundary_clear_timeouts` (parametrised: 1, 1440), `test_options_flow_saves_submitted_values`, `test_options_flow_rejects_all_disabled`.
- These cover: poll_interval and clear_timeout are stored in `_entry_data`; vol.Range boundary values are accepted; options flow submits and persists selected values; options flow rejects all-disabled with correct error.

### Multi-site support — `CONF_SITE` / `DEFAULT_SITE`
- `const.py`: added `CONF_SITE = "site"` and `DEFAULT_SITE = "default"`.
- `config_flow.py`: added optional `site` field (default `"default"`) to both the categories step and the options flow init step; stored in `_entry_data` and options `data`.
- `coordinator.py`: reads `CONF_SITE` from config (falls back to `DEFAULT_SITE`); passes the site name to `categorise_alarms()` on every poll cycle.
- `strings.json` + `translations/en.json`: added `"site"` label to both the categories step and the options init step.
- `test_coordinator.py`: added `TestSiteConfig` (2 tests): coordinator passes configured site to `categorise_alarms`; defaults to `"default"` when absent.

### `TODO.md` — resolved items removed
- Removed: API key instructions, multi-site support.
- Updated: remaining test coverage gap now reduced to end-to-end integration tests only.

---

## 2026-04-10 (session 3) — 4 high-priority bugfixes: session ownership, SSRF, API key path, pagination (244 tests)

Addressed the top four items from `TODO.md`. All checks pass: lint, mypy, HACS preflight, translation drift, 244 tests.

### `config_flow.py` — Replace HA-managed session with raw `aiohttp.ClientSession`
- `async_create_clientsession(self.hass)` was creating an HA-managed session, then `await session.close()` in the `finally` block manually closed it. HA registers its own cleanup handler for sessions created this way, so the manual close triggered a deprecation warning from `homeassistant.helpers.frame`.
- Replaced with `async with aiohttp.ClientSession() as session:`. The context manager owns and closes the session; the `finally` block is gone. The session is only needed for the single auth check so a raw `ClientSession` is appropriate.
- Removed `async_create_clientsession` import (now unused). Added `import aiohttp`.

### `config_flow.py` — SSRF: validate controller URL scheme before connecting
- `async_step_user` previously passed the raw user-supplied URL directly to `UniFiClient` without validation. A misconfigured or malicious URL (e.g. `ftp://internal-host`) could cause the integration to probe arbitrary internal services.
- Added a `yarl.URL` scheme check before the unique-ID and session work: if the scheme is not `http` or `https`, a field-level error `invalid_url_scheme` is shown immediately and no network call is made.
- Added `"invalid_url_scheme"` to `strings.json` and `translations/en.json`.

### `unifi_client.py` — API key endpoint always uses `/proxy/network` prefix
- `_verify_api_key` called `self._network_path('/api/s/default/self')`, which returned the path unmodified when `_is_unifi_os` was `False`. API keys are UniFi OS-only, so the detection result is irrelevant — the correct path is always `/proxy/network/api/s/default/self`. Changed to hardcode the prefix via `UNIFI_OS_NETWORK_PREFIX`.
- Added 404 handling in `_verify_api_key`: a 404 now raises `CannotConnectError("API key endpoint not found — check the controller URL and that UniFi OS is accessible at this address")` instead of bubbling as an unhandled `ClientResponseError`.

### `unifi_client.py` — `_detect_unifi_os` two-stage fallback probe
- The primary heuristic (presence of `x-csrf-token` in the `/` response) is insufficient for UCG-Ultra firmware and reverse-proxy setups where the header is absent or stripped.
- Added a fallback: if `x-csrf-token` is absent, probe `GET /api/system`. That endpoint exists on all UniFi OS consoles and returns 200; classic controllers return 404. Returns `True` if the fallback returns 200, `False` otherwise. Both stages handle network errors gracefully.

### `unifi_client.py` — Pagination on `/alarm` endpoint (`limit=200`)
- `fetch_alarms` previously fetched the full unarchived alarm backlog in one request. On sites with thousands of alarms this could return a multi-megabyte payload and block the event loop.
- Added `params={"limit": 200}` to the GET request to cap each poll at the 200 most recent alarms.

### Tests — 10 new tests (244 total)
- `test_config_flow.py`: updated 4 tests that patched `async_create_clientsession` to patch `aiohttp.ClientSession` as an async context manager; added `test_invalid_url_scheme_shows_error` (SSRF); added `_make_session_mock()` helper.
- `test_unifi_client.py`: replaced `test_returns_false_when_csrf_token_absent` with `test_returns_false_when_csrf_token_absent_and_system_probe_fails` and added `test_returns_true_when_fallback_system_probe_200` for the new OS detection fallback; added `TestVerifyApiKey` (3 tests: always uses `/proxy/network` prefix, 404 raises `CannotConnectError`, 401 raises `InvalidAuthError`); added `test_sends_limit_param` in `TestFetchAlarms`.

### `TODO.md` — resolved items removed
- Removed: aiohttp session ownership, SSRF URL validation, OS detection / API key path bug, alarm endpoint pagination.

---

## 2026-04-10 (session 2) — Pre-release v1pre2 continued: 3 more fixes, lint cleanup, docs (238 tests)

Completed the remaining v1pre2 fixes: password field masking, repopulates bug, coordinator and webhook tightening. Also resolved 5 merge conflicts from origin/main and fixed 24 ruff lint issues in origin-merged test files.

### `config_flow.py` — Mask password/API key + fix repopulates bug
- `CONF_PASSWORD` and `CONF_API_KEY` now use `TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))` so HA renders them as masked inputs with a show/hide toggle.
- Error-recovery schema (shown after a failed auth attempt) omits `default=` for password and API key fields entirely — HA never pre-fills sensitive values on re-render.
- `CONF_USERNAME` now uses a conditional default: `default=` is omitted entirely when the submitted value is an empty string, so HA treats the field as genuinely blank rather than pre-filled. This fixes the "repopulates old username/password after switching to API key" bug.
- Updated `test_user_step_error_preserves_submitted_values` to assert that `CONF_PASSWORD` and `CONF_API_KEY` are absent from error-recovery schema defaults.

### `coordinator.py` — Skip disabled categories in polling loop
- Polling loop now skips categories where `state.enabled is False`: `open_count` is not updated, no auto-clear is scheduled, and the zeroise pass also skips disabled categories. Fixes inconsistency where disabled categories with controller-side open alarms had non-zero `open_count`.

### `webhook_handler.py` — Tighten bare `except Exception` in JSON parsing
- `except Exception` replaced with `except (json.JSONDecodeError, TypeError)` so unexpected errors during webhook body parsing are no longer silently swallowed.

### Origin/main merge + lint cleanup
- Merged 5 origin commits (new test files `test_entities.py`, `test_init.py`, `test_webhook_handler.py`, updated `conftest.py`, Makefile, CI, hooks). Resolved 5 merge conflicts.
- Fixed 24 ruff lint issues in origin-merged test files: unused imports, unused variables (`F841`), import ordering (`I001`), `SIM105` (try/except/pass → `contextlib.suppress`), `SIM117` (nested `with` → single `with`).

### `CLAUDE.md` — Pull-before-work reminder
- Added "Always pull `main` before starting work" to the Working style section to prevent future branch divergence.

### `TODO.md` — Resolved items removed
- Removed: API key/password plaintext, repopulates bug, session close, at-least-one-category, disabled category open_count, webhook exception tightening.
- Kept: UCG-Ultra OS detection (api key path), API key instructions, pagination, integration tests, multi-site.

---

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
