# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

---

## 🔴 Must-fix before V1 tag

### [BUG] Webhook GET health-checks fire spurious alerts
**File:** `webhook_handler.py:80-93`
**Problem:** The handler registers `allowed_methods=["GET", "POST"]` and unconditionally dispatches a `UniFiAlert` for every request regardless of method. A GET with no body produces `payload = {}`, which becomes `message = "{}"` via the `str(payload)` fallback, incrementing `alert_count` and flipping binary sensors ON. UniFi Alarm Manager uses GET as a connectivity check — every probe triggers a false alert.
**Fix:** Remove `"GET"` from `allowed_methods`, or return early without dispatching when `request.method == "GET"`.

### [BUG] Options flow reads `entry.data` instead of `entry.options` — settings lost after first save
**File:** `config_flow.py:170-174`
**Problem:** `async_step_init` reads `current_enabled`, `current_poll`, and `current_clear` exclusively from `self._config_entry.data`. After the first options save, values are stored in `entry.options`. On any subsequent visit to the options screen, the user sees the original setup values, not their last saved options.
**Fix:** Check `entry.options` first, fall back to `entry.data`: `entry.options.get(KEY, entry.data.get(KEY, DEFAULT))`.

### [BUG] Manual clear button does not cancel the pending auto-clear task
**File:** `button.py:55-59`, `coordinator.py:155-162`
**Problem:** `async_press` calls `state.clear()` directly, but the scheduled `_auto_clear` task still runs. If a new alert arrives after the manual clear but before the timeout, the auto-clear fires and incorrectly clears the new active alert.
**Fix:** Add a `cancel_clear(category)` method to the coordinator and call it from `async_press` before mutating state.

### [BUG] First-refresh failure silently fails — no `ConfigEntryNotReady` / no HA retry
**File:** `__init__.py:43-48`
**Problem:** An authentication failure before the first refresh returns `False`, causing HA to mark the entry as permanently failed with no retry. A poll failure during `async_config_entry_first_refresh` raises an uncaught exception with no useful message. HA should be given a `ConfigEntryNotReady` with context so it retries on the standard back-off schedule.
**Fix:** Wrap `async_config_entry_first_refresh` in a try/except and re-raise as `ConfigEntryNotReady("Could not connect to controller: ...")`.

### [BUG] Polling increments `alert_count` on every cycle for existing open alarms — event entities misfire
**File:** `coordinator.py:87-90`
**Problem:** When polling finds an open alarm in a non-alerting category, it calls `apply_alert()` which increments `alert_count`. Event entities detect new alerts by comparing against `_last_seen_count`. On a system with persistent unarchived alarms, this fires a spurious automation trigger every poll cycle after the auto-clear timeout.
**Fix:** Deduplicate polled alarms by ID before calling `apply_alert()`, or give the polling path its own code path that sets `open_count` and `last_alert` without incrementing `alert_count`.

### [BUG] `datetime.now()` produces timezone-naive datetimes throughout
**File:** `models.py:36,57,90`
**Problem:** HA stores and compares datetimes in UTC. Attributes containing `.isoformat()` of a naive datetime are inconsistent with HA's own timestamps and break time-based comparisons in automations.
**Fix:** Replace all `datetime.now()` calls with `datetime.now(UTC)` (`from datetime import UTC`, valid Python 3.11+).

### [SECURITY] SSL verification disabled by default — silent MITM risk
**File:** `const.py:25`, `unifi_client.py:95,125,140,156,171`, `__init__.py:36`
**Problem:** `DEFAULT_VERIFY_SSL = False` means every outbound request ships with TLS verification disabled. Any attacker on the LAN path can silently intercept session cookies, API keys, or plaintext credentials.
**Fix:** Change `DEFAULT_VERIFY_SSL = True`. Add UI copy warning that disabling SSL is a security tradeoff only appropriate for controllers with self-signed certs. Update README with guidance on importing certs into HA's CA store.

### [SECURITY] No webhook authentication — any LAN device can inject arbitrary alert state
**File:** `webhook_handler.py:61`, `webhook_handler.py:86-89`
**Problem:** Webhooks have no authentication. While `local_only=True` limits exposure to the LAN, any device on the local network can trigger arbitrary alert state changes. The webhook URLs are deterministic and displayed in the UI and diagnostics.
**Fix:** Implement a shared secret (HMAC signature or a per-entry bearer token). Generate the secret on first setup, include it in the displayed webhook URLs, and verify it on every inbound request before processing the payload.

### [UX] Credential form is confusing — no guidance on when to use API key vs username/password
**File:** `config_flow.py`, `strings.json`
**Problem:** Four credential fields are shown simultaneously with no explanation of which authentication method to choose or where to find an API key. The `{docs_url}` placeholder resolves to the repo homepage, not a documentation page.
**Fix:** Split into a radio-button auth-method step, or add concrete help text: "API keys are available in UniFi OS consoles (UDM Pro, UCG Ultra) under Settings → Admins → API Keys." Add a README section covering both auth methods.

### [UX] Local-only webhook constraint is completely undocumented
**File:** `README.md`, `strings.json`
**Problem:** Webhooks are registered with `local_only=True`. Users on cloud-hosted UniFi consoles or accessing HA via Nabu Casa will silently receive no push alerts and assume the integration is broken.
**Fix:** Add a callout in the README setup section: "Important: Webhook URLs are local-network only. Your UniFi controller must be on the same local network as Home Assistant."

### [UX] All categories default ON — causes alert fatigue on busy home networks
**File:** `config_flow.py`, `const.py`
**Problem:** "Client connect/disconnect" and "Device offline/online" will fire on every phone joining Wi-Fi or device restart. New users who accept defaults will be flooded immediately.
**Fix:** Default only the exceptional-event categories (security threat, firewall, IDS/IPS) to ON. Or add a warning in the categories step noting that client/device events are very chatty.

### [UX] README setup buries the critical webhook URL step as an afterthought paragraph
**File:** `README.md`
**Problem:** The numbered setup steps end at "Configure polling interval" — the most critical post-setup action (copying webhook URLs into Alarm Manager) is a paragraph below the list that many users will miss.
**Fix:** Add an explicit step 5: "After setup, open Settings → Devices & Services → UniFi Alerts → Configure to find your webhook URLs. Copy each into UniFi Alarm Manager."

---

## 🟡 High-value improvements

### [SECURITY] Unvalidated controller URL allows SSRF
**File:** `config_flow.py:53,57`
**Problem:** The controller URL field accepts any string and passes it directly to the HTTP client. A malicious or misconfigured user could supply an internal address (e.g. `http://localhost:8123/`) to probe internal services.
**Fix:** Validate that the URL scheme is `http` or `https`, and optionally reject loopback and link-local addresses using `yarl.URL`.

### [SECURITY] Username not redacted in diagnostics output — PII leak in bug reports
**File:** `diagnostics.py:21`
**Problem:** `_TO_REDACT` covers password and API key but not username. For many UniFi deployments the username is an email address. Users sharing diagnostics in GitHub issues will expose PII.
**Fix:** Add `CONF_USERNAME` to `_TO_REDACT`. Update `test_diagnostics.py` accordingly.

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
