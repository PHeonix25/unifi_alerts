# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

## 🟡 High-value improvements

### [SECURITY] Unvalidated controller URL allows SSRF
**File:** `config_flow.py:53,57`
**Problem:** The controller URL field accepts any string and passes it directly to the HTTP client. A malicious or misconfigured user could supply an internal address (e.g. `http://localhost:8123/`) to probe internal services.
**Fix:** Validate that the URL scheme is `http` or `https`, and optionally reject loopback and link-local addresses using `yarl.URL`.

### [BUG] No pagination on `/alarm` endpoint — large backlogs block event loop
**File:** `unifi_client.py:92-103`
**Problem:** On sites with thousands of unarchived alarms, the API returns a multi-megabyte response in a single call, which may exceed the 10-second timeout and blocks the event loop budget during parsing.
**Fix:** Add a `?limit=200` query parameter (or equivalent) and document the constraint. Fetch only the most recent N alarms per poll cycle.

### Integration tests with the `hass` fixture
**Problem:** The current test suite uses plain mocks and does not exercise the HA setup lifecycle. Config flow, entity creation, coordinator wiring, and webhook dispatch are all untested end-to-end.
**Fix:** Set up `pytest_homeassistant_custom_component` properly in `conftest.py` and add tests for:
- `async_setup_entry` → entities appear in HA state machine
- Webhook POST → binary sensor flips to `on`
- Auto-clear timeout → binary sensor returns to `off`
- Options flow → categories change → entities update
- `async_unload_entry` → entities removed, webhooks unregistered
- GET health-check → no spurious alert dispatched
**Reference:** See `TESTING.md` for fixture pattern.

### Multi-site support
**Problem:** `UniFiClient.fetch_alarms()` hardcodes `site="default"`. Users with multi-site UniFi deployments cannot monitor secondary sites. Currently a silent failure with no user-facing explanation.
**Fix:** Add a `CONF_SITE` config entry key, defaulting to `"default"`. Expose it as an optional field in the config flow. Pass it through to `fetch_alarms()`. Add a README note: "Currently only the default UniFi site is supported. Multi-site support is planned."

---

## 🟢 Nice-to-have

### Config entry repair flow
If authentication fails after setup (e.g. password changed), HA should surface a repair notification prompting the user to re-enter credentials rather than just showing the entry as unavailable.
**Reference:** `homeassistant.helpers.issue_registry` and `async_create_issue`.

### Options flow: allow credentials to be updated without re-adding integration
Currently the only way to change the controller URL or credentials is to delete and re-add the integration. Add a re-auth step to the options flow. Document the current limitation in the README as a workaround.

### Lovelace card / dashboard example in README
Add a simple Lovelace YAML snippet showing how to build a network health card using the binary sensors and count sensors. Reduces friction for new users.

### Service calls
Expose `unifi_alerts.clear_category` and `unifi_alerts.clear_all` as HA services in addition to the button entities. This allows clearing alerts from automations without needing a button press.
**File to create:** `services.py` (register with `hass.services.async_register`), `services.yaml` (service descriptions).

### Replace placeholder `brand/icon.png` with a real 256×256 icon
The current brand asset is a minimal placeholder PNG. Replace with a proper UniFi-themed icon before submitting to the HACS default catalogue.

### HACS default repository submission
After the integration is stable and passes `hassfest`, submit a PR to https://github.com/hacs/default to be listed in the default HACS catalogue. Requirements: 2+ releases, passing CI, `hacs.json`, `info.md`, HA brand icon.

---

## 🐛 Known issues / technical debt

### `_device_info` duplication
The `_device_info()` helper function is duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, and `button.py`. Intentional for platform isolation but could be extracted to a shared `entity_base.py` mixin if it becomes a maintenance burden.

### Polling re-auth is fire-and-forget
In `coordinator._async_update_data`, if re-auth succeeds but the second `categorise_alarms()` call fails for a different reason, the error path is the generic `CannotConnectError` branch which may give a misleading log message.

### `strings.json` and `translations/en.json` are manually kept in sync
HA's tooling expects them to match. A pre-commit hook or CI check that diffs the two files would prevent drift.

### `manifest.json` does not declare `webhook` as a dependency
The integration depends on `homeassistant.components.webhook`. HA loads it early by default so this rarely matters in practice, but explicit declaration via `"dependencies": ["webhook"]` would make the dependency visible to hassfest.

### Disabled category `open_count` is still updated by polling
`categorise_alarms()` returns all categories regardless of enabled/disabled state, and the coordinator updates `open_count` for all of them. A disabled category with open alarms on the controller will have a non-zero `open_count` internally, which is inconsistent.

### CI action versions are floating (`@master`, `@main`)
`home-assistant/actions/hassfest@master` and `hacs/action@main` are not pinned to a SHA. A breaking upstream change or supply-chain compromise would silently affect CI. Pin to commit SHAs and update periodically.

