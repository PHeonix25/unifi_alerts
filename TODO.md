# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

---

## 🔴 Must-fix before first publish

### 1. Establish development instructions & a contributing guide
**Problem:** The README currently lacks any developer instructions. This creates friction for contributors and may lead to issues and PRs that don't meet the project's standards.
**Fix:** Create a `DEVELOPING.md` file with:
- Local development setup (Python version, venv, installing dependencies)
- Running the test suite
- Code style guidelines (e.g. black, isort)
- Branching and PR process (e.g. feature branches, commit message format)
- How to run `hassfest` and interpret results
- How to test the config flow and webhook handling manually in HA
- Any other project-specific conventions (e.g. how to update `strings.json` and `translations/en.json` together)
**Reference:** See contributing guides of popular HA integrations for examples

### 2. Webhook URL display in UI
**Problem:** After setup, the user has no way to find the generated webhook URLs inside HA's UI. They are logged at INFO level but that's not user-friendly.
**Fix:** Add a diagnostics platform (`diagnostics.py`) that exposes the webhook URLs, or use a `persistent_notification` during `async_setup_entry` to surface them. The diagnostics approach is preferred for HACS.
**Reference:** https://developers.home-assistant.io/docs/integration_diagnostics

### 3. `hassfest` validation
**Problem:** The CI `hassfest` action validates the integration against HA's integration quality rules. It may flag issues not caught locally — run it on the first push and fix any failures before tagging a release.
**Common failures:** missing `quality_scale` in `manifest.json`, incorrect `iot_class`, missing `icon.png`.

### 4. Add `icon.png`
HACS and HA both expect `custom_components/unifi_alerts/icon.png` (256×256 PNG). Without it, the integration shows a generic icon in the UI and HACS browser.

---

## 🟡 High-value improvements

### 5. Integration tests with the `hass` fixture
**Problem:** The current test suite uses plain mocks and does not exercise the HA setup lifecycle. Config flow, entity creation, coordinator wiring, and webhook dispatch are all untested end-to-end.
**Fix:** Set up `pytest_homeassistant_custom_component` properly in `conftest.py` and add tests for:
- `async_setup_entry` → entities appear in HA state machine
- Webhook POST → binary sensor flips to `on`
- Auto-clear timeout → binary sensor returns to `off`
- Options flow → categories change → entities update
- `async_unload_entry` → entities removed, webhooks unregistered
**Reference:** See `TESTING.md` for fixture pattern.

### 6. Config flow: duplicate entry guard
**Problem:** If the user tries to add the same controller URL twice, a second entry is created. `ConfigFlow` has an `async_set_unique_id` mechanism to prevent this.
**Fix:** In `async_step_user`, call:
```python
await self.async_set_unique_id(controller_url)
self._abort_if_unique_id_configured()
```
Use the normalised controller URL as the unique ID.

### 7. Config flow: webhook URL display post-setup
**Problem:** Users need to know their webhook URLs to configure UniFi Alarm Manager. These are only visible in logs currently.
**Fix:** After `async_create_entry`, consider a `async_step_finish` step or a re-auth flow that displays the URLs. Alternatively, surface them via the diagnostics platform (see item 2).

### 8. Expand `UNIFI_KEY_TO_CATEGORY` map
**Problem:** The current event key map in `const.py` is based on community sources and is incomplete. Users with different controller configurations or firmware versions will see unclassified alerts.
**Fix:**
- Add debug logging that prints unclassified keys at `_LOGGER.debug` level (already done in `unifi_client.py` — verify this is working)
- Create a GitHub issue template asking users to report their key values
- Add keys as they're reported, with a test case each time
- Consult: https://ubntwiki.com/products/software/unifi-controller/api

### 9. Multi-site support
**Problem:** `UniFiClient.fetch_alarms()` hardcodes `site="default"`. Users with multi-site UniFi deployments cannot monitor secondary sites.
**Fix:** Add a `CONF_SITE` config entry key, defaulting to `"default"`. Expose it as an optional field in the config flow (advanced section or a separate step). Pass it through to `fetch_alarms()` and `categorise_alarms()`.

### 10. Coordinator: handle `HA_stop` gracefully
**Problem:** When HA stops, in-flight auto-clear `asyncio.Task` objects may log cancellation errors.
**Fix:** In `async_unload_entry` (or a coordinator `async_shutdown` method), cancel all pending tasks in `_clear_tasks` before teardown.

---

## 🟢 Nice-to-have

### 11. Config entry repair flow
If authentication fails after setup (e.g. password changed), HA should surface a repair notification prompting the user to re-enter credentials rather than just showing the entry as unavailable.
**Reference:** `homeassistant.helpers.issue_registry` and `async_create_issue`.

### 12. Lovelace card / dashboard example in README
Add a simple Lovelace YAML snippet showing how to build a network health card using the binary sensors and count sensors. This reduces friction for new users.

### 13. Service calls
Expose `unifi_alerts.clear_category` and `unifi_alerts.clear_all` as HA services in addition to the button entities. This allows clearing alerts from automations without needing a button press.
**File to create:** `services.py` (register with `hass.services.async_register`), `services.yaml` (service descriptions).

### 14. Configurable site per category
Currently all categories poll the same site. Power users may want some categories monitored on a secondary site. Low priority — most home users have one site.

### 15. HACS default repository submission
After the integration is stable and passes `hassfest`, submit a PR to https://github.com/hacs/default to be listed in the default HACS catalogue (as opposed to a custom repo). Requirements: 2+ releases, passing CI, `hacs.json`, `info.md`, HA brand icon.

---

## 🐛 Known issues / technical debt

### TD-1: `_device_info` duplication
The `_device_info()` helper function is duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, and `button.py`. This is intentional for platform isolation but could be extracted to a shared `entity_base.py` module with a `UniFiAlertsEntity` mixin if the duplication becomes a maintenance burden.

### TD-2: Polling re-auth is fire-and-forget
In `coordinator._async_update_data`, if `InvalidAuthError` is raised, the re-auth attempt happens inline. If both the initial call and re-auth fail, `UpdateFailed` is raised correctly. However, if re-auth succeeds but the second `categorise_alarms()` call fails for a different reason, the error path is the generic `CannotConnectError` branch which may give a misleading log message.

### TD-3: Webhook GET body assumption
`webhook_handler.py` catches all exceptions on `request.json()` and falls back to `{}`. A malformed POST body (not a parse error but invalid content) may silently produce an empty alert. This is acceptable for now but worth tightening with a more specific `JSONDecodeError` catch.

### TD-4: `strings.json` and `translations/en.json` are manually kept in sync
HA's tooling expects them to match. A pre-commit hook or CI check that diffs the two files would prevent drift.
