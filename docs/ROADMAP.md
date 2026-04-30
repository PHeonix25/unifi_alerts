# Roadmap

This file maps TODO items to planned releases. Items within each release are ordered by priority — complete them top-to-bottom. Check off each item as it is merged to `main`.

> **Branching model:** all development happens on `dev` (pre-release versions: `X.Y.Z-preN`). Stable releases are tagged on `main` after a PR merge. See `CLAUDE.md § Branching strategy and versioning` for the full workflow.

> **Current status:** v1.0.0, v1.1.0, v1.2.0 released. v1.3.0 released (2026-04-29). Active development continues on `dev` at v1.4.0-pre2. Planned path to v2.0.0: v1.4.0 (UniFi OS only) → v1.5.0 (security hardening II) → v1.6.0 (reliability + completeness) → v1.7.0 (documentation + architecture) → v2.0.0 (HACS default).

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

- [x] Lovelace / dashboard YAML example in README
- [x] Automation example in README — verify correct `event_type` and `event_data` schema

### QA

- [ ] Verify update-in-place (HACS file copy → config entry reload) works without a full HA restart

### Tech debt

- [x] Pin CI action versions to commit SHAs instead of `@master` / `@main` (`ci.yml`)
- [x] Config entry repair flow — surface a HA repair notification when auth fails post-setup (`homeassistant.helpers.issue_registry`)
- [x] Options flow: allow credentials and controller URL to be updated without re-adding integration
- [x] Service calls: `unifi_alerts.clear_category` and `unifi_alerts.clear_all` (`services.py`, `services.yaml`)

---

## v1.2.0 — Critical-review hardening (pre-HACS-default)

A second-opinion pass after the v1.1 PRs landed surfaced a set of items that are not blocking for a stable release but should be closed before submitting to the HACS default catalogue.  These are the "what did we miss?" findings.  Ordered by impact.

### Reliability / correctness

- [ ] **Webhook ID collision on multi-entry (CRITICAL)** — `webhook_id_for_category()` returns `unifi_alerts_{category}` without including `entry_id` (`const.py:183-184`).  Two config entries (multi-controller households) will collide on webhook registration — the second entry silently overwrites the first's handlers.  This is the root cause behind the multi-entry isolation gap noted in the Testing section below.  Fix: include `entry_id` (or a short hash) in the webhook ID, update `WebhookManager` and the config-flow URL display.  Affects `const.py:183-184`, `webhook_handler.py:56`, `config_flow.py:200-205,462-465`.
- [x] `UniFiClient.fetch_alarms()` caps results at `limit=200` with no pagination loop — fixed in v1.3.0: `limit` param removed entirely.
- [ ] `fetch_alarms()` passes `ssl=self._config.get(CONF_VERIFY_SSL, False)` — if the key is somehow missing from `_config`, SSL verification silently turns OFF (`unifi_client.py:106`).  Change the fallback to `DEFAULT_VERIFY_SSL` (True) so a missing key fails closed, not open.
- [ ] **SSL fail-open in 4 additional call sites** — the same `self._config.get(CONF_VERIFY_SSL, False)` pattern with a `False` default exists in `_detect_unifi_os()` (`unifi_client.py:156`), `_verify_api_key()` (`unifi_client.py:202`), `_login_userpass()` (`unifi_client.py:238`), and `close()` (`unifi_client.py:139`).  All must be changed to `DEFAULT_VERIFY_SSL` alongside the `fetch_alarms()` fix above.
- [ ] `_category_states` is rebuilt from scratch on every config-entry reload — `alert_count` and `last_alert` are discarded whenever the user tweaks an option (`coordinator.py:59-62`).  Persist the last-seen state across reloads (e.g. via `hass.data[DOMAIN][entry.entry_id]["_last_states"]` saved in `async_unload_entry` and restored in `async_setup_entry`).
- [ ] `WebhookManager.register_all()` registers webhooks inside a loop with no try/finally — if one registration fails partway through, the already-registered ones are not tracked in `self._registered`, so `unregister_all()` cannot clean them up (`webhook_handler.py:47-73`).  Wrap per-iteration with `try: register; self._registered.append(...) except: ...` and/or a finally-driven rollback.
- [ ] **`datetime.fromisoformat()` called on epoch-millisecond input** (`models.py:52-57`) — the code comment says "UniFi stores timestamps as epoch milliseconds in some fields" but the code calls `datetime.fromisoformat(str(ts))`, which rejects numeric strings and silently falls through to `datetime.now(UTC)`. Every poll-sourced alert therefore has its `received_at` replaced with the poll time, breaking ordering and the "when did this actually fire?" attribute. Add an epoch-ms branch (`datetime.fromtimestamp(int(ts) / 1000, tz=UTC)`) before the ISO fallback; log at WARNING when neither matches.
- [ ] **`open_count` never updated on webhook path** — `push_alert()` updates `is_alerting` and `alert_count` but `open_count` stays at whatever the last poll returned until the next poll cycle (`coordinator.py:123-143`).  Users automating on the open-count sensor will see stale values between polls.  Consider incrementing `open_count` optimistically in `push_alert()` (and letting the next poll correct it).
- [ ] **`UniFiClient.close()` silently swallows logout errors** (`unifi_client.py:142-143`) — `except Exception: pass` in the logout path means a failed logout leaves session tokens valid on the controller indefinitely. Log at WARNING with `type(err).__name__` so operators can see the issue without leaking controller response bodies.
- [ ] **Webhook decode errors silently converted to empty payload** (`webhook_handler.py:105-107`) — `UnicodeDecodeError` and `JSONDecodeError` are both caught and replaced with `{}`, so a misconfigured controller sending non-UTF-8 or truncated JSON produces an alert with `"Unknown alert"` and no key, with nothing in logs. Log at WARNING with the exception class name and first 80 bytes of the raw body (not the full body, for size).

### Security

- [ ] Webhook secret cannot be rotated post-setup — it is generated once in `config_flow.py:84` and stored immutably.  If a user believes the token was leaked, the only recovery is delete-and-re-add.  Add a "Regenerate webhook secret" action to the options flow (reuses the `secrets.token_urlsafe(32)` call, updates `entry.data[CONF_WEBHOOK_SECRET]`, re-registers webhooks, shows new URLs).
- [ ] **Non-constant-time webhook token comparison** (`webhook_handler.py:89`) — `request.query.get("token") != secret` is vulnerable to a timing side-channel that leaks the secret byte-by-byte. Replace with `hmac.compare_digest(request.query.get("token", ""), secret)`.
- [ ] **Webhook URLs containing `?token=<secret>` logged at DEBUG** (`__init__.py:92-95`) — users who enable DEBUG logging (commonly requested for troubleshooting) will see tokens in plain text in logs, which they then paste into GitHub issues. Redact `?token=...` from the logged URL, or log only the category→webhook-id mapping.
- [ ] **Full webhook payload logged at DEBUG** (`webhook_handler.py:109`) — the entire controller payload is echoed to logs. Narrow to `{category, alert_key, severity, device_name}` to avoid accidentally surfacing sensitive fields from future UniFi firmware versions.
- [ ] **`allow_redirects=True` on unauthenticated probes** (`unifi_client.py:162,178`) — the UniFi-OS detection calls follow redirects without validating the final host matches the configured controller URL. A compromised DNS or on-path attacker could redirect the probe to an attacker-controlled host that returns headers that complete "detection". Set `allow_redirects=False` on probes, or assert `final_url.host == configured_host` before trusting the response.
- [ ] **Config flow creates bare `aiohttp.ClientSession` instead of HA's `async_get_clientsession`** — `config_flow.py:80,234,343` use `async with aiohttp.ClientSession()` which bypasses HA's proxy configuration, connection pooling, and the `verify_ssl` setting from the form.  Fix: use `async_get_clientsession(self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))`.
- [ ] **Credential fragments may leak in `__init__.py` exception messages** — Lines 53-57 pass `err` into `ConfigEntryAuthFailed` and `ConfigEntryNotReady` messages.  If the underlying exception includes URL fragments or auth details, they will appear in HA logs.  The v1.1 fix in `unifi_client.py` logs `type(err).__name__` only; apply the same pattern here (`__init__.py:53-57`).
- [ ] **No webhook rate limiting / debounce** — a misconfigured UniFi Alarm Manager or noisy category can flood the webhook endpoint, generating a coordinator state update + event entity fire for every POST.  No cooldown exists.  Fix: add a configurable per-category cooldown (e.g. 5s default) in `push_alert()` that skips duplicate `(category, key)` pairs within the window (`coordinator.py:123`).

### Type safety / tech debt

- [ ] `pyproject.toml` has `strict = false` for mypy — `UniFiClient.config` flows as `dict[str, Any]` throughout, hiding type errors.  Migrate `config: dict[str, Any]` to a `TypedDict` or frozen dataclass so `CONF_*` keys are checked, then bump to `strict = true` (or a stricter subset).
- [ ] Entity naming is ad-hoc — each platform file hard-codes `_attr_name = f"{CATEGORY_LABELS[cat]} Foo"`.  Adopt the `has_entity_name = True` + `_attr_translation_key = "..."` pattern so the strings live in `strings.json` (`binary_sensor.py:60`, `sensor.py:56,109`, `event.py:63`, `button.py`).  Unlocks localisation and cleaner registry IDs.
- [ ] No sensor `device_class` on the open-count or rollup-count sensors (`sensor.py:96,128`) — add a device_class where one fits (none of HA's built-ins map cleanly to "open alert count"; consider `None` + richer `state_class`).
- [ ] **Config flow accesses private `client._is_unifi_os`** — `config_flow.py:99,253,372` read a private attribute directly.  If the client internals change, this breaks silently.  Fix: expose `is_unifi_os` as a public `@property` on `UniFiClient` (`unifi_client.py`).
- [x] **`EventDeviceClass.BUTTON` is semantically incorrect for alert events** — resolved in v1.3.0 post-install fix PR.
- [x] **Clear buttons and diagnostic entities lack `entity_category`** — resolved in v1.3.0 post-install fix PR.

### Testing

- [ ] No integration-level test covers two UniFi Alerts config entries active at once — services, webhooks, and coordinator state could leak between them.  Add a multi-entry fixture in `tests/unit/test_init.py` and assert coordinator isolation.  **Note:** the webhook ID collision above (`const.py:183`) means this test will _fail_ until the code is fixed — write the test first as a red-green pair.
- [ ] No test asserts that a webhook arriving while `_async_update_data()` is mid-await does not produce a regressed `is_alerting` state.  The guard at `coordinator.py:92` (`if alerts and not state.is_alerting`) should prevent it, but there is no test that verifies the interleaving.  Add one in `test_coordinator.py`.
- [ ] **No test for `from_api_alarm` with numeric (epoch-millisecond) timestamp** — the timestamp parsing code at `models.py:54-57` has an untested edge case where numeric values silently fall back to `now()`.  Add a `test_from_api_alarm_epoch_ms` test (`test_models.py`).
- [ ] **No test for alert deduplication or rate limiting** — once the webhook debounce is implemented (see Security section), add tests verifying that rapid-fire duplicate alerts within the cooldown window are suppressed.

### Release process / repo hygiene

- [ ] No `CHANGELOG.md` at repo root — the GH release workflow auto-writes release notes but a committed CHANGELOG is what HACS-default reviewers typically look for.  Add `CHANGELOG.md` following Keep-a-Changelog and populate retrospectively from v1.0 onwards.
- [ ] With GitHub Actions now pinned to SHAs (v1.1), nothing keeps them fresh.  Add Renovate or Dependabot config targeting `github-actions` so pinned SHAs are proposed as PRs on upstream updates.
- [ ] No `SECURITY.md`, `CODEOWNERS`, or GitHub issue templates.  Adds reviewer signal for HACS-default approval and channels bug reports away from general issues.
- [ ] **Release notes are auto-generated from all commits and `release.yml` relies on a third-party action** — replace `softprops/action-gh-release` with `gh release create` (GitHub CLI, pre-installed on runners). Pass `--generate-notes` so notes are scoped between the previous tag and the current one. Upload the asset with `--attach unifi_alerts.zip`, mark pre-releases with `--prerelease`. Add a `.github/release.yml` categories file to group PR titles into labelled sections. Eliminates the only third-party action in `release.yml`.

### Documentation

- [ ] No supported-firmware matrix in README/info.md — users don't know if their UDM-SE / UCG / UX / CloudKey Gen2 model is expected to work.  Add a small table of tested controller models / firmware versions with any known quirks.
- [ ] No troubleshooting / FAQ section — common issues (local_only webhooks, self-signed certs, UniFi OS vs legacy, API-key generation paths) are scattered across the README prose.  Consolidate into a Troubleshooting section.
- [ ] **No uninstall instructions** (README / info.md) — a first-time user who decides to remove the integration has no guidance. Add a one-line "To remove: Settings → Devices & Services → UniFi Alerts → ⋮ → Delete" under Setup.
- [ ] **`info.md` doesn't warn about the local-network requirement up front** — remote-access (Nabu Casa, reverse-proxy) users install it, configure webhook URLs pointing at their cloud HA, and get silent failure. Add a bold "⚠ Local network only" banner to the first paragraph.
- [ ] **Setup flow doesn't warn that webhook URLs must be copied before submitting** — URLs are only shown on the final step of the config flow; clicking Submit closes the dialog and users don't realise they missed the copy step. Add a `strings.json` note on the webhook-URLs step: "Copy all URLs into UniFi Network → Settings → Notifications → Alarm Manager **before** clicking Submit."
- [ ] **No privacy / data retention section in README** — users don't know which UniFi payload fields end up in HA state (message, device_name, site, severity, raw) or how long they persist. Add a short "Data handling" section: what fields are stored, that nothing leaves the local network, and that auto-clear removes `is_alerting`/`last_alert` after the configured timeout.
- [ ] **Automation example doesn't document the "category disabled → event entity unavailable" edge case** — if a user disables the `security_threat` category via options after wiring up an automation, the event entity becomes unavailable and the automation silently stops firing. Add a one-liner caveat to the README automation section.
- [ ] **`unique_id` format is undocumented** (README) — power users wiring entities into long-lived automations don't know whether renaming entities in the UI is safe. Document the `{entry_id}_{category}_{sensor_type}` pattern and explicitly note that UI renames preserve `unique_id`, so automations are safe.

---

## v1.3.0 — Post-install hardening ✓

Released 2026-04-29. Five pre-release checkpoints (`pre1`–`pre5`) on `dev`.

### Bug fixes

- [x] **Options flow loop** — `UniFiAlertsOptionsFlow` restructured to mirror 3-step initial-setup (credentials → categories → webhook URLs). (`config_flow.py`, `strings.json`, `translations/en.json`)
- [x] **No device/service parent** — proactive device registration via `dr.async_get_or_create` in `async_setup_entry`; `configuration_url` added to all `_device_info()` helpers. (`__init__.py`, all platform files)
- [x] **Blank / unclickable entities** — message sensor defaults to `"No alerts yet"` instead of `None`; `EntityCategory.DIAGNOSTIC` on message sensors; `EntityCategory.CONFIG` on clear buttons; removed wrong `EventDeviceClass.BUTTON` from event entities. (`sensor.py`, `button.py`, `event.py`)
- [x] **`_is_unifi_os` misdetected on API-key auth** — coerced to `True` on successful API-key verification so subsequent API calls use the correct `/proxy/network` path prefix. (`unifi_client.py`)
- [x] **HTTP status codes missing from connection errors** — surfaced in `CannotConnectError` messages for easier troubleshooting. (`unifi_client.py`)

### Alarm endpoint improvements

- [x] **Extended probe chain for UniFi Network 9.x+** — `fetch_alarms()` now walks `[/list/alarm, /alarm, /stat/alarm]` newest-to-oldest. Modern firmware succeeds in one call; legacy firmware falls back. (`unifi_client.py`)
- [x] **Removed invalid `limit=200` param** — controllers with >200 open alarms no longer silently drop results. (`unifi_client.py`)

### CI / infrastructure

- [x] **Pre-release grep regex** — added `--` terminator to prevent `grep` from parsing `-pre[0-9]+` as CLI flags; every `vX.Y.Z-preN` tag was incorrectly publishing as a stable release. (`.github/workflows/release.yml`)
- [x] **`action-gh-release` bumped to v3 (Node 24)** — ahead of the 2026-06-02 Node 20 EOL on GitHub-hosted runners. (`.github/workflows/release.yml`)

---

## v1.4.0 — UniFi OS only + open-count watermark + hardening

### UniFi OS only

**Decision (2026-04-22):** the integration will officially support only UniFi OS controllers (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+). Classic self-hosted controllers (Network Application running on bare Linux/Windows) are excluded. Rationale: the userbase is almost entirely on UniFi OS hardware, API keys (the preferred auth method) are UniFi OS-only, and the dual-path detection code is a persistent source of bugs. Supporting both paths adds fragile detection logic that has already caused two known production incidents.

#### Documentation (do first — ships ahead of code change)

- [ ] **Add UniFi OS prerequisite to README** — opening paragraph + Prerequisites section; list tested console models (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+); state explicitly that classic Network Application (self-hosted) is not supported. (`README.md`)
- [ ] **Add UniFi OS prerequisite to info.md** — same message, first paragraph, with a bold "⚠ Requires UniFi OS" callout. (`info.md`)

#### Code simplification (do after docs)

- [ ] **Remove legacy self-hosted code paths from `unifi_client.py`** — once docs land, remove:
  - `_detect_unifi_os()` entirely — detection is only needed for the legacy/OS branch
  - `_network_path()` — always prefix with `/proxy/network`; make it a constant or inline it
  - Login path ordering in `_login_userpass()` — always try `/api/auth/login` first (UniFi OS path); remove the second fallback path
  - Logout path branch in `close()` — always use `/api/auth/logout`
  - `CONF_IS_UNIFI_OS` persistence in config flow — no longer needed; remove from `config_flow.py`, `const.py`, and stored `entry.data`
  - This removes ~30-40 lines and eliminates the root cause of the v1.2 API-key/detection mismatch bug
- [ ] **Add `async_migrate_entry` for `CONF_IS_UNIFI_OS` removal** — bump `ConfigFlow.VERSION` from `1` to `2`; implement `async_migrate_entry` that strips `CONF_IS_UNIFI_OS` from `entry.data` for version-1 entries. Without this, existing installs carry a stale key; after the removal, any code that reads it would silently get `None`. Ships in the same PR as the code simplification.
- [ ] **Update tests** — remove tests that only exist to cover the legacy path (detection returning False, path without `/proxy/network`, classic controller login ordering); update remaining tests to not set `_is_unifi_os` explicitly.

### Open-count watermark (PR #44)

- [x] **Per-category acknowledgement watermark for `open_count`** — shipped 2026-04-29 (before v1.4.0-pre1). `coordinator.py` has `async_restore_watermarks()`, `_async_persist_watermarks()`, `async_clear_category()`, and `async_clear_all()`. The `_async_update_data()` polling path filters alarms newer than `last_cleared_at`. Watermarks stored via `Store` and survive HA restarts. **Bug noted during 2026-04-30 audit:** `_auto_clear()` does NOT call `_async_persist_watermarks()` — auto-clear-triggered watermarks are lost on restart. Fix tracked in v1.6.0 Reliability / correctness.

### Hardening carry-overs (from v1.2.0 audit)

The items below were identified in the post-v1.1.0 critical review, planned for v1.2.0, and carried forward. Now targeting v1.4.0.

#### Reliability / correctness

- [x] **Webhook ID collision on multi-entry (CRITICAL)** — fixed 2026-04-29 in cluster A (PR #50): `CONF_WEBHOOK_ID_SUFFIX` (8-char hex, generated per entry by config flow); `webhook_id_for_category(category, suffix="")` returns `unifi_alerts_{suffix}_{category}` when present and falls back to legacy `unifi_alerts_{category}` when absent so existing single-entry users don't have to re-paste URLs. Multi-entry isolation integration test (`tests/integration/test_multi_entry.py`) added as the red-green pair.
- [ ] **SSL fail-open on missing key (5 call sites)** — `ssl=self._config.get(CONF_VERIFY_SSL, False)`. If the key is somehow absent, SSL verification silently turns OFF. Change all five fallbacks to `DEFAULT_VERIFY_SSL`. Affected: `_try_fetch_alarms` (`unifi_client.py:134`), `close()` (`:197`), `_detect_unifi_os()` (`:214`), `_verify_api_key()` (`:260`), `_login_userpass()` (`:296`).
- [ ] `_category_states` is rebuilt from scratch on every config-entry reload — `alert_count` and `last_alert` are discarded whenever the user tweaks an option (`coordinator.py:70-73`). Persist the last-seen state across reloads (alongside the existing watermarks in the `Store`).
- [x] `WebhookManager.register_all()` partial-failure leak — fixed 2026-04-29 in cluster A (PR #50): each iteration wrapped in try/except; only successful registrations append to `_registered`; `tests/unit/test_webhook_handler.py::TestRegisterAllRollback` covers behaviour.
- [ ] **`datetime.fromisoformat()` called on epoch-millisecond input** (`models.py:52-57`) — numeric timestamps silently fall through to `datetime.now(UTC)`, losing the real alarm time. Add an epoch-ms branch before the ISO fallback; log at WARNING when neither matches.
- [ ] **`_auto_clear` does not persist the watermark** (`coordinator.py:298-304`) — `_auto_clear()` calls `state.clear()` but never awaits `_async_persist_watermarks()`. If HA restarts after a timer-triggered auto-clear, the watermark is lost and `open_count` jumps back to the lifetime total. Fix: add `await self._async_persist_watermarks()` after `state.clear()`. Also add `test_auto_clear_persists_watermark` to `test_coordinator.py`. Found 2026-04-30 audit.
- [ ] **`UniFiClient.close()` silently swallows logout errors** (`unifi_client.py:200-201`) — `except Exception: pass` leaves session tokens valid on the controller indefinitely. Log at WARNING with `type(err).__name__`.
- [x] **Webhook decode errors silently converted to empty payload** — fixed 2026-04-29 in cluster A: `UnicodeDecodeError` / `JSONDecodeError` / `TypeError` now log at WARNING with exception class name and first 80 bytes of raw body.
- [ ] **Silent JSON-parse failure during 400-error inspection** (`unifi_client.py:153-154`) — `except Exception: pass` swallows any failure to parse the UniFi JSON error body. The `api.err.InvalidObject` fallback is silently skipped if the body is malformed. Log at DEBUG with exception class name. Surfaced by 2026-04-29 BEFORE-state audit.

#### Security

- [x] Webhook secret cannot be rotated post-setup — fixed 2026-04-29 in cluster A: "Regenerate webhook secret" checkbox in options-flow credentials step. Works alone or alongside credential changes; persists a fresh `token_urlsafe(32)`.
- [x] **Non-constant-time webhook token comparison** — fixed 2026-04-29 in cluster A: `hmac.compare_digest`; regression test asserts the function is called.
- [x] **Webhook URLs containing `?token=<secret>` logged at DEBUG** — fixed 2026-04-29 in cluster A: `_redact_webhook_token()` scrubs `?token=` to `?token=***` in `__init__.py`.
- [x] **Full webhook payload logged at DEBUG** — fixed 2026-04-29 in cluster A: `_SAFE_DEBUG_FIELDS` allow-list narrows the DEBUG log to `{category, alert_key, key, severity, device_name}`.
- [ ] **`allow_redirects=True` on unauthenticated detection probes** (`unifi_client.py:220,233`) — the `_detect_unifi_os()` probes follow redirects without validating the final host. A compromised DNS or on-path attacker could redirect the probe to an attacker-controlled host. Set `allow_redirects=False` and handle HTTP→HTTPS redirects explicitly, or assert `final_url.host == configured_host` before trusting the response.
- [ ] **Config flow creates bare `aiohttp.ClientSession`** (`config_flow.py:82,243,366`) — use `async_get_clientsession(self.hass, verify_ssl=...)`.
- [ ] **Credential fragments may leak in `__init__.py` exception messages** (`__init__.py:57,60`) — `ConfigEntryAuthFailed` and `ConfigEntryNotReady` include `str(err)`. If the exception contains URL fragments or auth details, they appear in HA logs. Log `type(err).__name__` only (same pattern as `unifi_client.py`).
- [x] **No webhook rate limiting / debounce** — fixed 2026-04-29 in cluster A: per-(category, alert_key) 5s `WEBHOOK_DEDUP_WINDOW_SECONDS` window in `coordinator.push_alert()`. `TestPushDedup` covers same/distinct keys, distinct categories, window expiry, empty-key edge case.
- [ ] **Document that secret rotation rotates the bearer token but reuses the webhook ID** (added by 2026-04-29 AFTER audit). Rotation changes the `?token=` query parameter but not the URL path; an attacker who captured the old token still hits a live endpoint, the token check rejects them. If true revocation (URL path change) is ever required, the suffix would also need to rotate. Add a paragraph to `SECURITY.md` and a `# WHY:` comment in `config_flow.py` near the rotation branch so the threat model is explicit.
- [ ] **Options-flow credential changes persist before the user submits the flow** (raised by Copilot review on PR #50). `UniFiAlertsOptionsFlow.async_step_credentials` calls `async_update_entry()` for both the credential-validation branch and (after PR #50) the rotate-only branch. Abandoning the flow on a later step still leaves the change persisted. Refactor: stage credentials and secret in `self._pending_data` and persist atomically inside `async_step_finish`. Pre-existing on `dev`, not introduced by cluster A.
- [ ] **`verify_ssl` toggle alone does not persist in the options flow** (raised by Copilot review on PR #50). `credentials_changed` only checks URL/username/password/api_key, so flipping the verify-SSL checkbox without other changes silently does nothing. Pre-existing on `dev`. Fix: include `verify_ssl` in the `credentials_changed` predicate, or treat it as its own change trigger. Best landed alongside the staging refactor above.

#### Type safety / tech debt

- [ ] `pyproject.toml` has `strict = false` for mypy — migrate `UniFiClient.config: dict[str, Any]` to a `TypedDict` / frozen dataclass, then bump to `strict = true`.
- [ ] Entity naming is ad-hoc — adopt `has_entity_name = True` + `_attr_translation_key` pattern so strings live in `strings.json`.
- [ ] No sensor `device_class` on the open-count or rollup-count sensors (`sensor.py:96,128`).
- [ ] **Config flow accesses private `client._is_unifi_os`** (`config_flow.py:106,261,395`) — expose as a public `@property`.
- [ ] **Button entities don't inherit from `CoordinatorEntity`** (`button.py`) — `UniFiClearCategoryButton` and `UniFiClearAllButton` extend `ButtonEntity` directly. They have no `available` property checking coordinator state, so they always appear available even when their category is disabled. Add `CoordinatorEntity[UniFiAlertsCoordinator]` as a mixin and an `available` property. Found 2026-04-30 audit.

#### Testing

- [x] Multi-entry isolation integration test — added 2026-04-29 in cluster A: `tests/integration/test_multi_entry.py` exercises two real config entries with distinct suffixes; POSTing to entry A's URL only flips entry A's coordinator (red-green pair).
- [ ] No test for webhook-arrives-mid-poll interleaving.
- [ ] **No test for `from_api_alarm` with epoch-millisecond timestamp** (`models.py:54-57`).
- [x] Webhook deduplication / rate-limiting test — added 2026-04-29 in cluster A: `TestPushDedup` covers same/distinct keys, distinct categories, window expiry, empty-key edge case.
- [ ] **No test for `_auto_clear` watermark persistence** — add `test_auto_clear_persists_watermark` to `test_coordinator.py` verifying that `_store.async_save` is called when the auto-clear timer fires. Found 2026-04-30 audit.
- [ ] **`make lint` does not cover `tests/`** (added by 2026-04-29 AFTER audit). Six pre-existing `I001` / `F401` issues in `tests/unit/test_services.py` and `tests/unit/test_config_flow.py` (mid-function imports, unused imports) escape local validation. None were introduced by clusters A or D. Expand the `lint` Makefile target to run ruff against `tests/` and either fix the existing issues or `# noqa` them with a one-line justification.
- [ ] **Optional: integration test for full options-flow → entry-update → reload → re-register cycle after secret rotation.** Unit-level rotation tests cover each step in isolation; an end-to-end test would be an extra guard. Lower priority since each step is already covered.

#### Release process / repo hygiene

- [x] No `CHANGELOG.md` at repo root — added 2026-04-29 in cluster D: Keep-a-Changelog file, back-filled v1.0.0 → v1.3.0; `[Unreleased]` section captures cluster A and D content.
- [x] Pinned SHAs need a refresh mechanism — added 2026-04-29 in cluster D: `.github/dependabot.yml` for `github-actions` ecosystem (weekly Monday cadence; minor + patch grouped, major individual).
- [x] No `SECURITY.md`, `CODEOWNERS`, or GitHub issue templates — added 2026-04-29 in cluster D: `SECURITY.md`, `CODEOWNERS`, `bug_report.yml`, `feature_request.yml`, `config.yml`.
- [x] Replace `softprops/action-gh-release` with `gh release create` — fixed 2026-04-29 in cluster D: migrated to `gh release create --generate-notes`; `.github/release.yml` categories file groups merged PRs by label; `fetch-depth: 0` added to checkout for previous-tag boundary; pre-release detection logic preserved verbatim. Eliminates the only third-party action in the release pipeline.

#### Documentation

- [ ] No supported-firmware matrix in README/info.md.
- [ ] No troubleshooting / FAQ section.
- [ ] No uninstall instructions (README / info.md).
- [ ] **`info.md` doesn't warn about the local-network requirement up front**.
- [ ] **Setup flow doesn't warn that webhook URLs must be copied before submitting**.
- [ ] No privacy / data-retention section in README.
- [ ] Automation example doesn't document the "category disabled → event entity unavailable" edge case.
- [ ] `unique_id` format is undocumented.

---

## v1.5.0 — Security hardening II (pre-HACS-default)

Closes the remaining security gaps from the v1.4.0 hardening backlog that are not blocking for a v1.4.0 release but must be resolved before HACS-default submission. Themed: **eliminate authentication-data exposure paths** and **make the options flow transactionally safe**.

### Authentication / credential safety

- [ ] **Config flow bare `aiohttp.ClientSession` → `async_get_clientsession`** (`config_flow.py:82,243,366`) — three places (`async_step_user`, `async_step_reauth_confirm`, `async_step_credentials`) create a raw `aiohttp.ClientSession` that bypasses HA's proxy config, connection pool limits, and the user's SSL setting. Replace with `async_get_clientsession(self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))`.
- [ ] **Credential fragments in `__init__.py` exception messages** (`__init__.py:57,60`) — `ConfigEntryAuthFailed(f"...: {err}")` and `ConfigEntryNotReady(f"...: {err}")` include `str(err)`. If the exception contains URL fragments or auth details, they appear in HA logs and the repair UI. Use `type(err).__name__` only, matching the `unifi_client.py` pattern.
- [ ] **`allow_redirects=True` on unauthenticated detection probes** (`unifi_client.py:220,233`) — the `_detect_unifi_os()` probes follow redirects without validating the final host. On a compromised LAN segment, DNS spoofing could redirect the probe to an attacker-controlled host. Set `allow_redirects=False` and handle HTTP→HTTPS redirects explicitly, or assert `final_url.host == configured_host` before trusting the response. Note: UCG-Ultra redirects HTTP→HTTPS; test both cases.

### Options flow atomicity

- [ ] **Options-flow staging refactor** (`config_flow.py`) — `async_step_credentials` calls `async_update_entry()` eagerly for both the validate-credentials branch and the rotate-only branch. If the user abandons the flow after credentials but before submitting, the new values are already persisted. Refactor: accumulate credential changes into `self._pending_data` (existing field) and persist atomically at the start of `async_step_finish`. This also naturally fixes the `verify_ssl` persistence gap below since the pending dict can carry the toggle value.
- [ ] **`verify_ssl` toggle alone does not persist** (`config_flow.py:325`) — `credentials_changed` only checks URL/username/password/api_key. Flipping verify-SSL alone short-circuits to categories without saving. Include `verify_ssl` in the predicate, or handle it inside the new staging refactor above.

### Documentation

- [ ] **Document secret rotation threat model in `SECURITY.md`** — rotation changes the `?token=` query parameter but not the URL path (the webhook ID suffix is unchanged). An attacker who captured the old token can still POST to the endpoint; the token check rejects them. If URL revocation is ever required, the suffix would also need to rotate. Add a paragraph to `SECURITY.md` explaining this and a `# WHY:` comment near the rotation branch in `config_flow.py`.
- [ ] **Close() logout errors** (`unifi_client.py:200-201`) — `except Exception: pass` leaves session tokens valid on the controller. Log at WARNING with `type(err).__name__`. Small but makes logout failures diagnosable.

---

## v1.6.0 — Reliability + completeness

Closes correctness gaps and polishes testing/tooling. Themed: **ensure every state-changing path is correct and covered**.

### Reliability / correctness

- [ ] **`_auto_clear` watermark persistence** (`coordinator.py:298-304`) — add `await self._async_persist_watermarks()` after `state.clear()` so timer-triggered clears survive HA restarts.
- [ ] **`open_count` stale on webhook path** (`coordinator.py:123-143`) — `push_alert()` does not update `open_count`. Consider optimistically incrementing it in `push_alert()` and letting the next poll correct the value.
- [ ] **`_category_states` rebuild discards counters on reload** (`coordinator.py:70-73`) — `alert_count` and `last_alert` are lost on every config-entry reload (options change, HA restart). Persist them alongside the existing watermarks in the `Store`.
- [ ] **Epoch-ms timestamp parsing** (`models.py:52-57`) — `datetime.fromisoformat(str(ts))` rejects numeric strings. Add an `int(ts) / 1000` epoch-ms branch before the ISO fallback; log at WARNING when neither matches.
- [ ] **Silent JSON-parse failure during 400-error inspection** (`unifi_client.py:153-154`) — `except Exception: pass` silently skips the `api.err.InvalidObject` fallback. Log at DEBUG with the exception class name.

### Testing / tooling

- [ ] **`make lint` to cover `tests/`** — expand the Makefile `lint` target to run ruff against `tests/` and fix/noqa the 6 pre-existing `I001`/`F401` issues in `test_services.py` and `test_config_flow.py`.
- [ ] **`test_auto_clear_persists_watermark`** in `test_coordinator.py` — mock `_store.async_save` and assert it is called when `_auto_clear` fires.
- [ ] **`test_from_api_alarm_epoch_ms`** in `test_models.py` — verify that a numeric epoch-ms timestamp produces the correct UTC `datetime`.
- [ ] **Interleaving test** in `test_coordinator.py` — assert that a webhook arriving while `_async_update_data()` is mid-await does not regress `is_alerting` (tests the guard at `coordinator.py:127`).

### Tech debt

- [ ] **Button entities `CoordinatorEntity` mixin** (`button.py`) — add `CoordinatorEntity[UniFiAlertsCoordinator]` as a mixin to both button classes and an `available` property checking `state.enabled`, consistent with the other platforms.
- [ ] **Config flow `_is_unifi_os` public property** (`unifi_client.py`) — expose `_is_unifi_os` as a public `@property is_unifi_os` on `UniFiClient`; update the three config-flow access sites (`config_flow.py:106,261,395`).

---

## v1.7.0 — Documentation + architecture

Closes all remaining documentation gaps and the largest architecture items. Themed: **make the integration production-ready for new users and contributors**.

### Architecture

- [ ] **`mypy strict = true`** — migrate `UniFiClient.config: dict[str, Any]` to a `TypedDict` or frozen dataclass; update all access sites; bump `pyproject.toml` to `strict = true`. Expected: catches latent type errors across coordinator, config flow, and entities.
- [ ] **`has_entity_name = True` + `_attr_translation_key` migration** — all four platform files use `_attr_name = f"{CATEGORY_LABELS[category]} — ..."`. Move the display strings to `strings.json` under `entity.binary_sensor.*`, `entity.sensor.*`, etc. and use `_attr_translation_key`. Unlocks localisation and cleaner entity registry IDs.
- [ ] **Split `test_config_flow.py` into a package** — 1405 lines with four logically independent classes. Convert to `tests/unit/config_flow/{__init__,conftest,test_setup,test_options,test_reauth}.py` as specified in `TODO.md`.
- [ ] **No sensor `device_class`** (`sensor.py:96,128`) — determine whether a `device_class` or richer `state_class` fits the open-count / rollup-count sensors.

### Documentation (8 items)

- [ ] **Supported-firmware matrix** — small table in README/info.md: tested UDM-SE / UCG-Ultra / UCG-Max / Cloud Key Gen2+ models with firmware versions and any known quirks.
- [ ] **Troubleshooting / FAQ section** — consolidate scattered notes: local-only webhooks, self-signed certs, "why is open_count so high?", API-key generation paths, Nabu Casa / cloud access fails.
- [ ] **Uninstall instructions** — one-liner in README/info.md: **Settings → Devices & Services → UniFi Alerts → ⋮ → Delete**.
- [ ] **`info.md` local-network warning** — add a bold "⚠ Local network only: webhooks are not reachable over Nabu Casa remote access" to the first paragraph.
- [ ] **Setup flow webhook copy warning** — add a note in `strings.json` on the `finish` step: "Copy all URLs into UniFi Network → Settings → Notifications → Alarm Manager **before** clicking Submit."
- [ ] **Privacy / data-retention section** in README — which payload fields are stored, that nothing leaves the local network, that auto-clear removes `is_alerting`/`last_alert` after the configured timeout.
- [ ] **Automation edge case** — document in README that disabling a category in options makes its event entity unavailable, breaking dependent automations.
- [ ] **`unique_id` format** in README — document the `{entry_id}_{category}_{sensor_type}` pattern; explicitly note that UI renames preserve `unique_id` so automations are safe.

### QA

- [ ] **Verify update-in-place** (carried from v1.1.0 QA) — test that a HACS file copy followed by **Settings → Integrations → UniFi Alerts → ⋮ → Reload** is sufficient; no HA restart required. If restart is required, investigate Python module caching and fix.
- [ ] **Optional: integration test for full rotation cycle** — options-flow → credential update → entry-update → reload → webhook re-registration, end-to-end. Unit steps are already covered; this is an extra guard.

---

## v2.0.0 — HACS default catalogue

Prerequisites for submitting to https://github.com/hacs/default.

- [x] `brand/icon.png` is a real 256×256 RGBA PNG (confirmed 2026-04-30 audit)
- [x] At least 2 tagged releases with passing CI
- [x] Create `info.md` (HACS display page)
- [ ] All v1.x issues resolved
- [ ] Submit PR to `hacs/default`

---

## Deferred / low priority

Items tracked in `TODO.md` under known issues that have no planned release yet.

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (if it becomes a maintenance burden)
- Configurable site per category (power-user feature)
