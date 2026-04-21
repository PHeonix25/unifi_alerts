# Roadmap

This file maps TODO items to planned releases. Items within each release are ordered by priority — complete them top-to-bottom. Check off each item as it is merged to `main`.

> **Branching model:** all development happens on `dev` (pre-release versions: `X.Y.Z-preN`). Stable releases are tagged on `main` after a PR merge. See `CLAUDE.md § Branching strategy and versioning` for the full workflow.

> **Current status:** v1.0.0 released. Branch model + CI versioning enforcement in place. Active development continues on `dev` targeting v1.1.0.

---

## v1.0.0 — First stable release ✓

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

### Blockers found during v1pre1 / v1pre2 installation testing

- [x] UCG-Ultra: OS detection fails → two-stage fallback probe added (x-csrf-token header + `/api/system` probe) (`unifi_client.py`)
- [x] Config flow API key path instructions are wrong — replaced with version-agnostic text listing both firmware paths (`strings.json`, `translations/en.json`, `README.md`)
- [x] Config flow repopulates old username/password after user clears them and switches to API key (`config_flow.py:76-90`)
- [x] API key and password fields are plaintext — sensitive values visible on screen; use `TextSelectorType.PASSWORD` (`config_flow.py:83-84,96-97`)

### Quick wins (one-liners, no reason to defer)

- [x] `str(payload)` fallback stores raw payload in alert message — replace with `"Unknown alert"` (`models.py:33`)
- [x] Username not redacted in diagnostics output — add `CONF_USERNAME` to `_TO_REDACT` (`diagnostics.py:21`)
- [x] `CONF_VERIFY_SSL` raw string in `__init__.py:36` — use the constant
- [x] `hacs.json` contradicts itself: `zip_release: false` but `filename` set — remove `filename`
- [x] `diagnostics.py` uses `__import__("logging")` — replace with standard `import logging`

---

## v1.1.0 — Security hardening + reliability

Issues that are non-blocking for a first release but important for production quality. Development for this release happens on `dev` under version `1.1.0-preN`.

### Infrastructure (completed as part of v1.0.0 → v1.1.0 transition)

- [x] Move to two-branch model (`main` = stable, `dev` = pre-release)
- [x] Add `version-check.yml` CI: enforce `X.Y.Z` on `main`, `X.Y.Z-preN` on `dev`
- [x] Update `release.yml` CI: trigger on tags, auto-detect pre-release, validate tag vs manifest

### Security

- [x] Unvalidated controller URL allows SSRF — scheme validation added (`config_flow.py`); loopback/link-local rejection remains optional
- [x] Unbounded webhook body stored in memory — apply `max_bytes` cap on `request.json()` (`webhook_handler.py:86`)
- [x] Credentials leak risk via exception messages in logs — log class name only, not `str(err)` (`unifi_client.py:105,181`)

### Bugs / reliability

- [x] No pagination on `/alarm` endpoint — `limit=200` added (`unifi_client.py:92`)
- [x] Polling re-auth is fire-and-forget — misleading log message when re-auth succeeds but second poll fails for a different reason (`coordinator.py`)

### UX / Documentation

- [ ] Lovelace / dashboard YAML example in README
- [ ] Automation example in README — verify correct `event_type` and `event_data` schema

### QA

- [ ] Verify update-in-place (HACS file copy → config entry reload) works without a full HA restart

### Tech debt

- [ ] Pin CI action versions to commit SHAs instead of `@master` / `@main` (`ci.yml`)
- [ ] Config entry repair flow — surface a HA repair notification when auth fails post-setup (`homeassistant.helpers.issue_registry`)
- [ ] Options flow: allow credentials and controller URL to be updated without re-adding integration
- [ ] Service calls: `unifi_alerts.clear_category` and `unifi_alerts.clear_all` (`services.py`, `services.yaml`)

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
- Configurable site per category (power-user feature)
