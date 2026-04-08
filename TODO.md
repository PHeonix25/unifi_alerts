# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

---

## 🔴 Must-fix (found in v1.0 real-world testing)

### [BUG] strings.json `user` step description incorrectly warns SSL is disabled by default
**File:** `strings.json` (and `translations/en.json`)
**Problem:** The `user` step description contains `⚠️ SSL verification is disabled by default — appropriate for controllers with self-signed certificates. Enable it if your controller has a trusted certificate.` This was accurate when `DEFAULT_VERIFY_SSL = False` but is now wrong since the default was flipped to `True`. Users see a warning that doesn't apply to their configuration.
**Fix:** Remove the `⚠️` SSL sentence from the `user` step description in both `strings.json` and `translations/en.json`. Update to reflect that SSL is **on** by default and should only be disabled for self-signed certificates.

### [BUG] Config flow user step resets all fields to defaults on validation error
**File:** `config_flow.py:76–90`
**Problem:** When `async_step_user` hits a validation error (invalid auth, cannot connect), it rebuilds `data_schema` with hardcoded defaults (`default="https://192.168.1.1"`, etc.) instead of pre-filling with the submitted values. The user must re-enter every field.
**Fix:** On the error path, pass `user_input` values as `default=` when reconstructing each schema field. Apply the same pattern to any other config flow step that rebuilds a schema on error.

### [BUG] Auth errors with local IP surface generic "invalid credentials" — poor diagnostics for UCG-Ultra and similar
**File:** `unifi_client.py:133–181`, `config_flow.py:63–69`, `strings.json`
**Problem:** Multiple distinct failure modes collapse into the same unhelpful error:
1. **HTTP to UCG-Ultra**: `_detect_unifi_os` uses `allow_redirects=False`, so an HTTP→HTTPS redirect returns a 3xx with no `x-csrf-token` → `_is_unifi_os = False` → login POSTs to the wrong endpoint (`/api/login` instead of `/api/auth/login`) → 404 or redirect loop → re-raised as `CannotConnectError`, sometimes misreported as auth failure.
2. **UCG-Ultra returns HTTP 400**: The `_login_userpass` code treats HTTP 400 the same as 401/403 (`raise InvalidAuthError`). UCG-Ultra returns 400 for structurally valid but rejected requests (e.g. missing `remember` field), so 400 ≠ bad credentials.
3. **No diagnostic detail in the UI**: The user sees `"Invalid credentials. Check your username/password or API key."` regardless of the underlying cause — wrong URL, wrong endpoint, SSL failure, or actual bad password.
**Fix:**
- In `_detect_unifi_os`: allow redirects and re-check the final response (or follow the redirect URL to HTTPS and re-test). Log the detection result with the final URL and status at `DEBUG`.
- In `_login_userpass`: separate HTTP 400 from 401/403. Raise a new `BadRequestError` (or a descriptive `CannotConnectError`) for 400 with a message indicating the request was rejected (likely wrong endpoint or malformed payload).
- In `config_flow.py`: catch the new error type and show a more prescriptive message — e.g. `"Controller rejected the login request (HTTP 400). Check the controller URL format and that it includes the correct port."` Log the endpoint URL and response status at `WARNING` on every auth failure so users can find it in HA logs.
- Add a new `strings.json` error key `invalid_auth_detail` (or expand `invalid_auth`) with placeholder for the diagnostic message.

### [UX] Webhook URLs in finish step are not selectable — hard to copy/paste
**File:** `config_flow.py:138–147`, `strings.json` (finish + options init steps), `translations/en.json`
**Problem:** Webhook URLs are embedded as markdown inside `description_placeholders`. HA config flow dialogs do not allow easy text selection within description blocks, so users cannot reliably copy individual URLs.
**Fix:** In `async_step_finish`, add each enabled category's webhook URL as a `vol.Optional` string field pre-filled with the URL value in `data_schema`. On submit, ignore those field values (proceed with `async_create_entry` using `self._entry_data` regardless of what the user typed). Apply the same pattern to the options flow `init` step so the URLs there are also copyable. Remove the URL list from `description_placeholders` once the fields are in place (or keep a short header line).

---

## 🟡 High-value improvements

### [SECURITY] Unvalidated controller URL allows SSRF
**File:** `config_flow.py:53,57`
**Problem:** The controller URL field accepts any string and passes it directly to the HTTP client. A malicious or misconfigured user could supply an internal address (e.g. `http://localhost:8123/`) to probe internal services.
**Fix:** Validate that the URL scheme is `http` or `https`, and optionally reject loopback and link-local addresses using `yarl.URL`.

### [SECURITY] `str(payload)` fallback stores raw webhook payload in alert message
**File:** `models.py:33`
**Problem:** When no recognised message field is present in a webhook payload, `from_webhook_payload` falls back to `str(payload)` — the entire payload repr, truncated to 255 chars. This leaks internal payload structure into the message field and into event entity attributes.
**Fix:** Replace `str(payload)` with a static sentinel `"Unknown alert"`, matching the behaviour of `from_api_alarm`.

### [SECURITY] Webhook URLs logged at INFO level on every startup
**File:** `__init__.py:71-74`
**Problem:** Full webhook URLs are written to HA logs at INFO level. Log files are routinely shared in bug reports, exposing the URLs even though they're local-only.
**Fix:** Demote to `DEBUG` level. Log only the count of registered webhooks at INFO.

### [BUG] Config flow uses `async_create_clientsession` — session is never properly closed
**File:** `config_flow.py:56`
**Problem:** `async_create_clientsession` creates a new session per config flow run. The `client.close()` call issues a logout HTTP request but does not close the underlying session. The correct pattern is to use `async_create_clientsession`, store a reference, and call `session.close()` explicitly in a try/finally after the auth check.
**Fix:** Create a dedicated temporary session for config flow auth, close it in a try/finally, and do not attempt a logout on the shared session.

### [BUG] No pagination on `/alarm` endpoint — large backlogs block event loop
**File:** `unifi_client.py:92-103`
**Problem:** On sites with thousands of unarchived alarms, the API returns a multi-megabyte response in a single call, which may exceed the 10-second timeout and blocks the event loop budget during parsing.
**Fix:** Add a `?limit=200` query parameter (or equivalent) and document the constraint. Fetch only the most recent N alarms per poll cycle.

### [BUG] UniFi OS detection triggers on any HTTP 200 — wrong path on non-UniFi hosts
**File:** `unifi_client.py:142`
**Problem:** `is_os = resp.headers.get("x-csrf-token") is not None or resp.status == 200`. Any HTTP server returning 200 on `/` is misclassified as UniFi OS, causing all API calls to use the wrong path prefix.
**Fix:** Remove `or resp.status == 200`. The `x-csrf-token` check alone is the correct heuristic.

### [BUG] No validation that at least one category is enabled
**File:** `config_flow.py:94-95`
**Problem:** If the user unchecks every category, setup proceeds with zero per-category entities. The integration silently does nothing.
**Fix:** Validate that `enabled` is non-empty in the categories step and return an error (`at_least_one_category`) if not.

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

### `CONF_VERIFY_SSL` raw string in `__init__.py:36`
`entry.data.get("verify_ssl", False)` uses a raw string instead of the `CONF_VERIFY_SSL` constant. If the constant's value ever changed, this reference would silently fall back to `False`.

### `diagnostics.py` uses `__import__` for logging instead of `import logging`
Line 19 uses `_LOGGER = __import__("logging").getLogger(__name__)`. Inconsistent with the stated coding convention and harder to read. No functional impact.

### `manifest.json` does not declare `webhook` as a dependency
The integration depends on `homeassistant.components.webhook`. HA loads it early by default so this rarely matters in practice, but explicit declaration via `"dependencies": ["webhook"]` would make the dependency visible to hassfest.

### Disabled category `open_count` is still updated by polling
`categorise_alarms()` returns all categories regardless of enabled/disabled state, and the coordinator updates `open_count` for all of them. A disabled category with open alarms on the controller will have a non-zero `open_count` internally, which is inconsistent.

### CI action versions are floating (`@master`, `@main`)
`home-assistant/actions/hassfest@master` and `hacs/action@main` are not pinned to a SHA. A breaking upstream change or supply-chain compromise would silently affect CI. Pin to commit SHAs and update periodically.

### `hacs.json` has contradictory `zip_release: false` and `filename` set
`"zip_release": false` causes HACS to ignore the `"filename"` field. Either remove `filename` or align both fields to use zip releases (which `release.yml` already generates).
