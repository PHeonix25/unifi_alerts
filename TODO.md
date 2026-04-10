# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

## 🟡 High-value improvements

### [SECURITY] Unvalidated controller URL allows SSRF
**File:** `config_flow.py:53,57`
**Problem:** The controller URL field accepts any string and passes it directly to the HTTP client. A malicious or misconfigured user could supply an internal address (e.g. `http://localhost:8123/`) to probe internal services.
**Fix:** Validate that the URL scheme is `http` or `https`, and optionally reject loopback and link-local addresses using `yarl.URL`.

### [BUG] Config flow API key instructions are wrong / vary by UniFi OS version
**File:** `strings.json:6`, `translations/en.json` (same line)
**Problem:** The config flow description tells users to generate an API key via **Settings → Admins & Users → API Keys**. This path is incorrect on at least some versions of UniFi OS (e.g. it's **Integrations → New API Key** on some consoles), and the correct path varies across firmware versions. Users following the instructions will not find the option and give up.
**Fix:**
- Audit the actual navigation path for each major UniFi OS variant (UCG-Ultra, UDM Pro, Cloud Key Gen2, hosted controller) and document findings in `UNIFI.md`.
- Replace the single hard-coded path in the config flow description with a version-agnostic instruction such as: *"Generate an API key in the UniFi OS web UI — the exact location varies by firmware version. Common paths: **Settings → Admins & Users → API Keys** or **Integrations → New API Key**. Refer to the [integration README] for device-specific instructions."*
- Add a dedicated "Generating an API key" section to `README.md` with per-device navigation paths so users can find it outside the config flow UI.

### [BUG] Config flow repopulates old username/password after switching to API key
**File:** `config_flow.py:76-90`
**Problem:** On a failed submission, the schema is rebuilt with `default=user_input.get(...)` for each field. However, HA's config flow frontend can retain or pre-fill field values from a prior schema render. If the user first submits username + password (form repopulates both), then clears those fields and submits with only an API key, the re-displayed form shows all three values — the old username/password are restored even though the user blanked them.
**Root cause:** Setting `default=user_input.get(CONF_USERNAME, "")` when the user submitted an empty string may interact with HA's `suggested_value` mechanism or frontend caching in a way that restores prior values instead of showing the current empty submission.
**Fix:** Explicitly omit keys with empty-string values from the schema defaults (use `vol.UNDEFINED` or omit the `default` argument) so HA treats them as truly blank rather than pre-filled. Only pass a non-empty default if the submitted value is a non-empty string:
```python
vol.Optional(CONF_USERNAME, **({"default": v} if (v := user_input.get(CONF_USERNAME, "")) else {})): str
```
Alternatively, use `description={"suggested_value": ...}` instead of `default=` which gives the frontend a weaker hint that the user can override.

### [BUG] API key and password fields are plaintext — sensitive values visible on screen
**File:** `config_flow.py:83-84, 96-97`
**Problem:** Both `CONF_API_KEY` and `CONF_PASSWORD` are declared as plain `str` in the vol schema. HA renders them as unmasked text inputs, so credentials are visible to anyone who can see the screen. Neither field gets the browser's password-field treatment (masked input with an unmask toggle).
**Fix:** Replace the bare `str` type with `TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))` for both fields. HA's frontend renders password-type selectors as masked inputs with a built-in show/hide toggle, satisfying the requirement to let the user reveal the value to verify a paste. Import from `homeassistant.helpers.selector`:
```python
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

# In both schema branches:
vol.Optional(CONF_PASSWORD): _PASSWORD_SELECTOR,
vol.Optional(CONF_API_KEY): _PASSWORD_SELECTOR,
```
Apply in both the initial schema and the error-repopulation schema (lines 83-84 and 96-97).

### [BUG] UCG-Ultra: OS detection fails → API key verification hits wrong endpoint (404)
**File:** `unifi_client.py:133-170`
**Reported by:** User during installation on UCG-Ultra
**Error:** `ClientResponseError: 404, message='Not Found', url='.../api/s/default/self'`
**Root cause:** `_detect_unifi_os()` relies solely on the presence of `x-csrf-token` in the response headers for `/`. On the UCG-Ultra (and possibly other newer UniFi OS consoles), this header is absent or the request fails, causing `_is_unifi_os` to be `False`. As a result, `_network_path()` does not prepend `/proxy/network`, and `_verify_api_key()` calls `/api/s/default/self` — a legacy non-OS endpoint that returns 404 on UniFi OS hardware.
**Impact:** Setup is completely broken for any UniFi OS console where the detection heuristic fails. The 404 is not handled gracefully and bubbles up as `Unexpected error during auth`.
**Fix options (pick one or combine):**
1. After a 404 from `_verify_api_key`, retry with the OS path forced (`/proxy/network/api/s/default/self`) to auto-recover from a misdetected OS type.
2. Improve `_detect_unifi_os` to also check for additional UCG-Ultra / UniFi OS signals (e.g. specific response body fields, `x-csrf-token` on a redirect destination, or a known OS-only endpoint like `/api/system`).
3. Expose a manual "UniFi OS" toggle in the config flow so users can override detection when the heuristic fails.
**Note:** The 404 should also be caught and re-raised as `InvalidAuthError` or `CannotConnectError` with a user-facing message instead of surfacing as a raw `ClientResponseError`.

### [BUG] No pagination on `/alarm` endpoint — large backlogs block event loop
**File:** `unifi_client.py:92-103`
**Problem:** On sites with thousands of unarchived alarms, the API returns a multi-megabyte response in a single call, which may exceed the 10-second timeout and blocks the event loop budget during parsing.
**Fix:** Add a `?limit=200` query parameter (or equivalent) and document the constraint. Fetch only the most recent N alarms per poll cycle.

### Integration tests with the `hass` fixture
**Problem:** The current test suite uses plain mocks and does not exercise the HA setup lifecycle. Config flow, entity creation, coordinator wiring, and webhook dispatch are all untested end-to-end.
**Fix:** Set up `pytest_homeassistant_custom_component` properly in `conftest.py` and add tests for:
- Webhook POST → binary sensor flips to `on`
- Auto-clear timeout → binary sensor returns to `off`
- Options flow → categories change → entities update
- GET health-check → no spurious alert dispatched
**Reference:** See `TESTING.md` for fixture pattern.

### Remaining test coverage gaps (plain-mock layer now complete — see HISTORY.md 2026-04-09)
All source modules now have plain-mock unit test coverage (234 tests). Remaining gaps:
- **Options flow form submission** — only the init form display is tested; saving updated values is not.
- **Config flow categories step submission** — poll interval / clear timeout validation and edge values (10, 3600, 1, 1440) not covered.
- **End-to-end integration tests** — still require full `hass` fixture setup (see item above).

### Multi-site support
**Problem:** `UniFiClient.fetch_alarms()` hardcodes `site="default"`. Users with multi-site UniFi deployments cannot monitor secondary sites. Currently a silent failure with no user-facing explanation.
**Fix:** Add a `CONF_SITE` config entry key, defaulting to `"default"`. Expose it as an optional field in the config flow. Pass it through to `fetch_alarms()`. Add a README note: "Currently only the default UniFi site is supported. Multi-site support is planned."

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

### Disabled category `open_count` is still updated by polling
`categorise_alarms()` returns all categories regardless of enabled/disabled state, and the coordinator updates `open_count` for all of them. A disabled category with open alarms on the controller will have a non-zero `open_count` internally, which is inconsistent.

### CI action versions are floating (`@master`, `@main`)
`home-assistant/actions/hassfest@master` and `hacs/action@main` are not pinned to a SHA. A breaking upstream change or supply-chain compromise would silently affect CI. Pin to commit SHAs and update periodically.

### Tighten bare `except Exception` in webhook handler
`webhook_handler.py:96` catches bare `except Exception` where only `json.JSONDecodeError` and `TypeError` are expected. Replace with `except (json.JSONDecodeError, TypeError):` to avoid masking unexpected errors.
