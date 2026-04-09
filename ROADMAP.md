# Roadmap

This file maps TODO items to planned releases. Items within each release are ordered by priority — complete them top-to-bottom. Check off each item as it is merged to `main`.

> **Current status:** v1.0.0 ready. All blocking bugs, security issues, and UX gaps are resolved. CI is green (hassfest + HACS + lint + tests). Ready to tag v1.0.0.

---

## v1.0.0 — First stable release

All blocking bugs, security issues, and UX gaps that will immediately affect new users.

### Bugs

- [x] Webhook GET health-checks fire spurious alerts (`webhook_handler.py:80`)
- [x] Options flow reads `entry.data` instead of `entry.options` — saved settings lost (`config_flow.py:170`)
- [x] Manual clear button does not cancel pending auto-clear task (`button.py:55`, `coordinator.py:155`)
- [x] First-refresh failure gives no `ConfigEntryNotReady` — entry fails permanently with no retry (`__init__.py:43`)
- [x] Polling increments `alert_count` on existing open alarms — event entity misfires every cycle (`coordinator.py:87`)
- [x] `datetime.now()` produces timezone-naive datetimes — breaks HA automation time comparisons (`models.py:36,57,90`)

### Security

- [x] SSL verification disabled by default — silent MITM risk (`const.py:25`)
- [x] No webhook authentication — any LAN device can inject alert state (`webhook_handler.py:61`)

### UX / Documentation

- [x] Credential form gives no guidance on API key vs username/password (`config_flow.py`, `strings.json`)
- [x] Local-only webhook constraint is undocumented — cloud console users get silent failure (`README.md`)
- [x] All 7 categories default ON — client/device events will flood busy home networks (`config_flow.py`)
- [x] README setup buries the "copy webhook URLs" step — make it a numbered step (`README.md`)

### Quick wins (one-liners, no reason to defer)

- [x] `str(payload)` fallback stores raw payload in alert message — replace with `"Unknown alert"` (`models.py:33`)
- [x] Username not redacted in diagnostics output — add `CONF_USERNAME` to `_TO_REDACT` (`diagnostics.py:21`)
- [x] `CONF_VERIFY_SSL` raw string in `__init__.py:36` — use the constant
- [x] `hacs.json` contradicts itself: `zip_release: false` but `filename` set — remove `filename`
- [x] `diagnostics.py` uses `__import__("logging")` — replace with standard `import logging`

---

## v1.1.0 — Security hardening + reliability

Issues that are non-blocking for a first release but important for production quality.

### Security

- [ ] Unvalidated controller URL allows SSRF — validate scheme and optionally reject loopback/link-local (`config_flow.py:53`)
- [x] Webhook URLs logged at INFO level on every startup — demote to DEBUG (`__init__.py:71`)
- [ ] Unbounded webhook body stored in memory — apply `max_bytes` cap on `request.json()` (`webhook_handler.py:86`)
- [ ] Credentials leak risk via exception messages in logs — log class name only, not `str(err)` (`unifi_client.py:105,181`)
- [x] Overly broad UniFi OS detection — remove `or resp.status == 200` fallback (`unifi_client.py:142`)

### Bugs

- [ ] Config flow creates session via `async_create_clientsession` and never closes it (`config_flow.py:56`)
- [ ] No pagination on `/alarm` endpoint — large backlogs block event loop (`unifi_client.py:92`)
- [ ] No validation that at least one category is enabled (`config_flow.py:94`)
- [ ] Disabled category `open_count` still updated by polling — skip disabled categories in loop (`coordinator.py:81`)

### Tests

- [x] Add `tests/test_webhook_handler.py` — valid POST, GET health-check no-op, invalid JSON, unregister
- [x] Add lifecycle tests: `async_setup_entry` populates state, `async_unload_entry` tears down cleanly

### Tech debt

- [ ] Pin CI action versions to commit SHAs instead of `@master` / `@main` (`ci.yml`)
- [~] Add `"dependencies": ["webhook"]` to `manifest.json` — HACS validator rejects HA-core built-ins in this field; reverted
- [ ] Add CI diff check between `strings.json` and `translations/en.json` to prevent drift
- [ ] Tighten `JSONDecodeError` catch in webhook handler instead of bare `except Exception`

---

## v1.2.0 — UX polish + multi-site

Quality-of-life improvements and the most-requested missing feature.

- [ ] Multi-site support — add `CONF_SITE` defaulting to `"default"`, expose in config flow (`unifi_client.py`, `config_flow.py`)
- [ ] Config entry repair flow — surface a HA repair notification when auth fails post-setup (`homeassistant.helpers.issue_registry`)
- [ ] Options flow: allow credentials and controller URL to be updated without re-adding integration
- [ ] Lovelace / dashboard YAML example in README
- [ ] Automation example in README — verify correct `event_type` and `event_data` schema
- [ ] Service calls: `unifi_alerts.clear_category` and `unifi_alerts.clear_all` (`services.py`, `services.yaml`)
- [ ] Full integration tests with the `hass` fixture (`pytest_homeassistant_custom_component`)

---

## v2.0.0 — HACS default catalogue

Prerequisites for submitting to https://github.com/hacs/default.

- [ ] Replace placeholder `brand/icon.png` with a real 256×256 icon
- [ ] At least 2 tagged releases with passing CI
- [ ] Create `info.md` (HACS display page)
- [ ] All v1.x issues resolved
- [ ] Submit PR to `hacs/default`

---

## Deferred / low priority

Items tracked in `TODO.md` under known issues that have no planned release yet.

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (if it becomes a maintenance burden)
- Fix misleading log message when re-auth succeeds but second poll call fails for a different reason
- Configurable site per category (power-user feature)
