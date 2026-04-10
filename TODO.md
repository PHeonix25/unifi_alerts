# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

## 🟡 High-value improvements

### [BUG] Config flow API key instructions are wrong / vary by UniFi OS version
**File:** `strings.json:6`, `translations/en.json` (same line)
**Problem:** The config flow description tells users to generate an API key via **Settings → Admins & Users → API Keys**. This path is incorrect on at least some versions of UniFi OS (e.g. it's **Integrations → New API Key** on some consoles), and the correct path varies across firmware versions. Users following the instructions will not find the option and give up.
**Fix:**
- Audit the actual navigation path for each major UniFi OS variant (UCG-Ultra, UDM Pro, Cloud Key Gen2, hosted controller) and document findings in `UNIFI.md`.
- Replace the single hard-coded path in the config flow description with a version-agnostic instruction such as: *"Generate an API key in the UniFi OS web UI — the exact location varies by firmware version. Common paths: **Settings → Admins & Users → API Keys** or **Integrations → New API Key**. Refer to the [integration README] for device-specific instructions."*
- Add a dedicated "Generating an API key" section to `README.md` with per-device navigation paths so users can find it outside the config flow UI.

### Integration tests with the `hass` fixture
**Problem:** The current test suite uses plain mocks and does not exercise the HA setup lifecycle. Config flow, entity creation, coordinator wiring, and webhook dispatch are all untested end-to-end.
**Fix:** Set up `pytest_homeassistant_custom_component` properly in `conftest.py` and add tests for:
- Webhook POST → binary sensor flips to `on`
- Auto-clear timeout → binary sensor returns to `off`
- Options flow → categories change → entities update
- GET health-check → no spurious alert dispatched
**Reference:** See `TESTING.md` for fixture pattern.

### Remaining test coverage gaps
Plain-mock unit layer is complete (253 tests). Remaining gap:
- **End-to-end integration tests** — still require full `hass` fixture setup (see item above).

### Verify update-in-place works without HA reboot
**Problem:** Unknown whether updating the integration (e.g. via HACS or copying files) requires a full Home Assistant restart, or whether reloading the config entry is sufficient. A reboot requirement would be a significant friction point for self-hosted users pushing frequent updates.
**Fix:** Test the update-in-place flow manually:
1. Install the integration and confirm it is working.
2. Update the integration files (e.g. simulate a HACS update by copying a newer version).
3. Reload the config entry via **Settings → Integrations → UniFi Alerts → ⋮ → Reload**.
4. Confirm all entities recover and no HA restart is required.
If a restart is required, investigate why (e.g. Python module caching, import-time side effects, platform registration) and fix so a config entry reload is sufficient. Document the expected update flow in `README.md`.

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

### CI action versions are floating (`@master`, `@main`)
`home-assistant/actions/hassfest@master` and `hacs/action@main` are not pinned to a SHA. A breaking upstream change or supply-chain compromise would silently affect CI. Pin to commit SHAs and update periodically.

### CI action versions are floating (`@master`, `@main`)
`home-assistant/actions/hassfest@master` and `hacs/action@main` are not pinned to a SHA. A breaking upstream change or supply-chain compromise would silently affect CI. Pin to commit SHAs and update periodically.
