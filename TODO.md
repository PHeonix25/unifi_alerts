# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

---

## 🟡 High-value improvements

### Integration tests with the `hass` fixture
**Problem:** The current test suite uses plain mocks and does not exercise the HA setup lifecycle. Config flow, entity creation, coordinator wiring, and webhook dispatch are all untested end-to-end.
**Fix:** Set up `pytest_homeassistant_custom_component` properly in `conftest.py` and add tests for:
- `async_setup_entry` → entities appear in HA state machine
- Webhook POST → binary sensor flips to `on`
- Auto-clear timeout → binary sensor returns to `off`
- Options flow → categories change → entities update
- `async_unload_entry` → entities removed, webhooks unregistered
**Reference:** See `TESTING.md` for fixture pattern.

### Multi-site support
**Problem:** `UniFiClient.fetch_alarms()` hardcodes `site="default"`. Users with multi-site UniFi deployments cannot monitor secondary sites.
**Fix:** Add a `CONF_SITE` config entry key, defaulting to `"default"`. Expose it as an optional field in the config flow (advanced section or a separate step). Pass it through to `fetch_alarms()` and `categorise_alarms()`.

---

## 🟢 Nice-to-have

### Config entry repair flow
If authentication fails after setup (e.g. password changed), HA should surface a repair notification prompting the user to re-enter credentials rather than just showing the entry as unavailable.
**Reference:** `homeassistant.helpers.issue_registry` and `async_create_issue`.

### Lovelace card / dashboard example in README
Add a simple Lovelace YAML snippet showing how to build a network health card using the binary sensors and count sensors. This reduces friction for new users.

### Service calls
Expose `unifi_alerts.clear_category` and `unifi_alerts.clear_all` as HA services in addition to the button entities. This allows clearing alerts from automations without needing a button press.
**File to create:** `services.py` (register with `hass.services.async_register`), `services.yaml` (service descriptions).

### Configurable site per category
Currently all categories poll the same site. Power users may want some categories monitored on a secondary site. Low priority — most home users have one site.

### HACS default repository submission
After the integration is stable and passes `hassfest`, submit a PR to https://github.com/hacs/default to be listed in the default HACS catalogue (as opposed to a custom repo). Requirements: 2+ releases, passing CI, `hacs.json`, `info.md`, HA brand icon.

---

## 🐛 Known issues / technical debt

### `_device_info` duplication
The `_device_info()` helper function is duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, and `button.py`. This is intentional for platform isolation but could be extracted to a shared `entity_base.py` module with a `UniFiAlertsEntity` mixin if the duplication becomes a maintenance burden.

### Polling re-auth is fire-and-forget
In `coordinator._async_update_data`, if `InvalidAuthError` is raised, the re-auth attempt happens inline. If both the initial call and re-auth fail, `UpdateFailed` is raised correctly. However, if re-auth succeeds but the second `categorise_alarms()` call fails for a different reason, the error path is the generic `CannotConnectError` branch which may give a misleading log message.

### Webhook GET body assumption
`webhook_handler.py` catches all exceptions on `request.json()` and falls back to `{}`. A malformed POST body (not a parse error but invalid content) may silently produce an empty alert. This is acceptable for now but worth tightening with a more specific `JSONDecodeError` catch.

### `strings.json` and `translations/en.json` are manually kept in sync
HA's tooling expects them to match. A pre-commit hook or CI check that diffs the two files would prevent drift.
