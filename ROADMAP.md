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

- [ ] **Webhook ID collision on multi-entry (CRITICAL)** — `webhook_id_for_category()` returns `unifi_alerts_{category}` without including `entry_id` (`const.py:183-184`).  Two config entries (multi-controller households) will collide on webhook registration — the second entry silently overwrites the first's handlers.  This is the root cause behind the multi-entry isolation gap noted in the Testing section below.  Fix: include `entry_id` (or a short hash) in the webhook ID, update `WebhookManager` and the config-flow URL display.  Affects `const.py:183`, `webhook_handler.py:56`, `config_flow.py:200-205,462-465`.
- [ ] `UniFiClient.fetch_alarms()` caps results at `limit=200` with no pagination loop — controllers with >200 open alarms silently drop the rest (`unifi_client.py:104`).  Remove the `limit` param so the controller returns the full set.
- [ ] `fetch_alarms()` passes `ssl=self._config.get(CONF_VERIFY_SSL, False)` — if the key is somehow missing from `_config`, SSL verification silently turns OFF (`unifi_client.py:106`).  Change the fallback to `DEFAULT_VERIFY_SSL` (True) so a missing key fails closed, not open.
- [ ] **SSL fail-open in 4 additional call sites** — the same `self._config.get(CONF_VERIFY_SSL, False)` pattern with a `False` default exists in `_detect_unifi_os()` (`unifi_client.py:156`), `_verify_api_key()` (`unifi_client.py:202`), `_login_userpass()` (`unifi_client.py:238`), and `close()` (`unifi_client.py:139`).  All must be changed to `DEFAULT_VERIFY_SSL` alongside the `fetch_alarms()` fix above.
- [ ] `_category_states` is rebuilt from scratch on every config-entry reload — `alert_count` and `last_alert` are discarded whenever the user tweaks an option (`coordinator.py:59-62`).  Persist the last-seen state across reloads (e.g. via `hass.data[DOMAIN][entry.entry_id]["_last_states"]` saved in `async_unload_entry` and restored in `async_setup_entry`).
- [ ] `WebhookManager.register_all()` registers webhooks inside a loop with no try/finally — if one registration fails partway through, the already-registered ones are not tracked in `self._registered`, so `unregister_all()` cannot clean them up (`webhook_handler.py:47-73`).  Wrap per-iteration with `try: register; self._registered.append(...) except: ...` and/or a finally-driven rollback.
- [ ] **`from_api_alarm` silently drops epoch-millisecond timestamps** — `models.py:53` comment says "UniFi stores timestamps as epoch milliseconds" but `fromisoformat()` cannot parse numeric values, so it falls back to `datetime.now(UTC)`, silently losing the real alarm time (`models.py:54-57`).  Fix: detect numeric timestamps and convert via `datetime.fromtimestamp(ts / 1000, tz=UTC)` before trying `fromisoformat`.
- [ ] **`open_count` never updated on webhook path** — `push_alert()` updates `is_alerting` and `alert_count` but `open_count` stays at whatever the last poll returned until the next poll cycle (`coordinator.py:123-143`).  Users automating on the open-count sensor will see stale values between polls.  Consider incrementing `open_count` optimistically in `push_alert()` (and letting the next poll correct it).

### Security

- [ ] Webhook secret cannot be rotated post-setup — it is generated once in `config_flow.py:84` and stored immutably.  If a user believes the token was leaked, the only recovery is delete-and-re-add.  Add a "Regenerate webhook secret" action to the options flow (reuses the `secrets.token_urlsafe(32)` call, updates `entry.data[CONF_WEBHOOK_SECRET]`, re-registers webhooks, shows new URLs).
- [ ] **Config flow creates bare `aiohttp.ClientSession` instead of HA's `async_get_clientsession`** — `config_flow.py:80,234,343` use `async with aiohttp.ClientSession()` which bypasses HA's proxy configuration, connection pooling, and the `verify_ssl` setting from the form.  Fix: use `async_get_clientsession(self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))`.
- [ ] **Credential fragments may leak in `__init__.py` exception messages** — Lines 53-57 pass `err` into `ConfigEntryAuthFailed` and `ConfigEntryNotReady` messages.  If the underlying exception includes URL fragments or auth details, they will appear in HA logs.  The v1.1 fix in `unifi_client.py` logs `type(err).__name__` only; apply the same pattern here (`__init__.py:53-57`).
- [ ] **No webhook rate limiting / debounce** — a misconfigured UniFi Alarm Manager or noisy category can flood the webhook endpoint, generating a coordinator state update + event entity fire for every POST.  No cooldown exists.  Fix: add a configurable per-category cooldown (e.g. 5s default) in `push_alert()` that skips duplicate `(category, key)` pairs within the window (`coordinator.py:123`).

### Type safety / tech debt

- [ ] `pyproject.toml` has `strict = false` for mypy — `UniFiClient.config` flows as `dict[str, Any]` throughout, hiding type errors.  Migrate `config: dict[str, Any]` to a `TypedDict` or frozen dataclass so `CONF_*` keys are checked, then bump to `strict = true` (or a stricter subset).
- [ ] Entity naming is ad-hoc — each platform file hard-codes `_attr_name = f"{CATEGORY_LABELS[cat]} Foo"`.  Adopt the `has_entity_name = True` + `_attr_translation_key = "..."` pattern so the strings live in `strings.json` (`binary_sensor.py:60`, `sensor.py:56,109`, `event.py:63`, `button.py`).  Unlocks localisation and cleaner registry IDs.
- [ ] No sensor `device_class` on the open-count or rollup-count sensors (`sensor.py:96,128`) — add a device_class where one fits (none of HA's built-ins map cleanly to "open alert count"; consider `None` + richer `state_class`).
- [ ] **Config flow accesses private `client._is_unifi_os`** — `config_flow.py:99,253,372` read a private attribute directly.  If the client internals change, this breaks silently.  Fix: expose `is_unifi_os` as a public `@property` on `UniFiClient` (`unifi_client.py`).
- [ ] **`EventDeviceClass.BUTTON` is semantically incorrect for alert events** — `event.py:51` uses `BUTTON` as "closest semantic match" but this is misleading in device-class-based automation UIs.  Fix: remove `_attr_device_class` entirely (or set to `None`); no built-in class fits "alert received" (`event.py:51`).
- [ ] **Clear buttons and diagnostic entities lack `entity_category`** — `UniFiClearCategoryButton` and `UniFiClearAllButton` don't set `_attr_entity_category = EntityCategory.CONFIG` (`button.py:37,63`).  Without this, they appear on the default dashboard and in voice assistant entity lists, which is confusing.  Similarly, message sensors could use `EntityCategory.DIAGNOSTIC`.

### Testing

- [ ] No integration-level test covers two UniFi Alerts config entries active at once — services, webhooks, and coordinator state could leak between them.  Add a multi-entry fixture in `tests/unit/test_init.py` and assert coordinator isolation.  **Note:** the webhook ID collision above (`const.py:183`) means this test will _fail_ until the code is fixed — write the test first as a red-green pair.
- [ ] No test asserts that a webhook arriving while `_async_update_data()` is mid-await does not produce a regressed `is_alerting` state.  The guard at `coordinator.py:92` (`if alerts and not state.is_alerting`) should prevent it, but there is no test that verifies the interleaving.  Add one in `test_coordinator.py`.
- [ ] **No test for `from_api_alarm` with numeric (epoch-millisecond) timestamp** — the timestamp parsing code at `models.py:54-57` has an untested edge case where numeric values silently fall back to `now()`.  Add a `test_from_api_alarm_epoch_ms` test (`test_models.py`).
- [ ] **No test for alert deduplication or rate limiting** — once the webhook debounce is implemented (see Security section), add tests verifying that rapid-fire duplicate alerts within the cooldown window are suppressed.

### Release process / repo hygiene

- [ ] No `CHANGELOG.md` at repo root — the GH release workflow auto-writes release notes but a committed CHANGELOG is what HACS-default reviewers typically look for.  Add `CHANGELOG.md` following Keep-a-Changelog and populate retrospectively from v1.0 onwards.
- [ ] With GitHub Actions now pinned to SHAs (v1.1), nothing keeps them fresh.  Add Renovate or Dependabot config targeting `github-actions` so pinned SHAs are proposed as PRs on upstream updates.
- [ ] No `SECURITY.md`, `CODEOWNERS`, or GitHub issue templates.  Adds reviewer signal for HACS-default approval and channels bug reports away from general issues.

### Documentation

- [ ] No supported-firmware matrix in README/info.md — users don't know if their UDM-SE / UCG / UX / CloudKey Gen2 model is expected to work.  Add a small table of tested controller models / firmware versions with any known quirks.
- [ ] No troubleshooting / FAQ section — common issues (local_only webhooks, self-signed certs, UniFi OS vs legacy, API-key generation paths) are scattered across the README prose.  Consolidate into a Troubleshooting section.

---

## v2.0.0 — HACS default catalogue

Prerequisites for submitting to https://github.com/hacs/default.

- [ ] Replace placeholder `brand/icon.png` with a real 256×256 icon
- [ ] At least 2 tagged releases with passing CI
- [x] Create `info.md` (HACS display page)
- [ ] All v1.x issues resolved
- [ ] Submit PR to `hacs/default`

---

## Deferred / low priority

Items tracked in `TODO.md` under known issues that have no planned release yet.

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (if it becomes a maintenance burden)
- Configurable site per category (power-user feature)
