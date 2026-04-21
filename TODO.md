# TODO.md

Prioritised backlog. Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

## 🟡 High-value improvements

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

### Replace placeholder `brand/icon.png` with a real 256×256 icon
The current brand asset is a minimal placeholder PNG. Replace with a proper UniFi-themed icon before submitting to the HACS default catalogue.

### HACS default repository submission
After the integration is stable and passes `hassfest`, submit a PR to https://github.com/hacs/default to be listed in the default HACS catalogue. Requirements: 2+ releases, passing CI, `hacs.json`, `info.md`, HA brand icon.
- `info.md` is now present (added session 11).
- Remaining: 2+ tagged releases, real brand icon (replace placeholder), PR submission to hacs/default.

---

## 🔥 v1.2 critical-review findings (pre-HACS-default hardening)

A comprehensive audit after the v1.1 PRs landed surfaced these items. Full detail (with file:line anchors and suggested fixes) is in `ROADMAP.md § v1.2.0`. Grouped by impact:

### Reliability / correctness
- **🔴 Webhook ID collision on multi-entry (CRITICAL):** `webhook_id_for_category()` returns `unifi_alerts_{category}` without `entry_id` — two config entries silently overwrite each other's webhook handlers (`const.py:183-184`). This is the root cause of the multi-entry isolation gap.
- **Unbounded alarm list:** `UniFiClient.fetch_alarms()` silently caps at `limit=200`. Remove the `limit` param (`unifi_client.py:104`).
- **SSL fail-open on missing key:** `ssl=self._config.get(CONF_VERIFY_SSL, False)` — change fallback to `DEFAULT_VERIFY_SSL` so a missing key fails closed (`unifi_client.py:106`).
- **SSL fail-open in 4 more call sites:** same `False` default in `_detect_unifi_os()` (`:156`), `_verify_api_key()` (`:202`), `_login_userpass()` (`:238`), and `close()` (`:139`).
- **Category state lost on reload:** `_category_states` is rebuilt from scratch on every options change; persist `alert_count` and `last_alert` across reloads (`coordinator.py:59-62`).
- **Partial webhook registration leak:** `WebhookManager.register_all()` has no try/finally — a failure mid-loop leaves registered hooks untracked (`webhook_handler.py:47-73`).
- **Epoch-ms timestamps silently dropped:** `from_api_alarm()` tries `fromisoformat()` on numeric timestamps, fails, falls back to `now(UTC)` — real alarm time lost (`models.py:54-57`).
- **`open_count` stale on webhook path:** `push_alert()` updates `is_alerting` and `alert_count` but `open_count` stays at whatever the last poll returned (`coordinator.py:123-143`).

### Security
- **Webhook secret cannot be rotated:** add a "Regenerate webhook secret" action to the options flow (reuses `secrets.token_urlsafe(32)`, updates `entry.data`, re-registers webhooks) (`config_flow.py:84`).
- **Config flow creates bare `aiohttp.ClientSession`:** bypasses HA's proxy config, connection pool, and SSL settings. Should use `async_get_clientsession(self.hass, verify_ssl=...)` (`config_flow.py:80,234,343`).
- **Credential fragments in `__init__.py` exception messages:** `err` is passed into `ConfigEntryAuthFailed`/`ConfigEntryNotReady`, may expose URL fragments or auth details in logs (`__init__.py:53-57`).
- **No webhook rate limiting / debounce:** a noisy category or misconfigured sender can flood the webhook endpoint with no cooldown, generating unbounded state updates and event fires (`coordinator.py:123`).

### Type safety / tech debt
- **`mypy strict = false`:** migrate `UniFiClient.config: dict[str, Any]` to a TypedDict / frozen dataclass, then bump `pyproject.toml` to `strict = true`.
- **Ad-hoc entity naming:** adopt `has_entity_name = True` + `_attr_translation_key` pattern across `binary_sensor.py`, `sensor.py`, `event.py`, `button.py` so names live in `strings.json`.
- **No sensor `device_class`:** consider what fits on the open-count / rollup-count sensors (`sensor.py:96,128`).
- **Config flow accesses private `client._is_unifi_os`:** expose as a public `@property` on `UniFiClient` (`config_flow.py:99,253,372`).
- **`EventDeviceClass.BUTTON` wrong for alert events:** remove the device_class or set to `None` (`event.py:51`).
- **Clear buttons lack `entity_category`:** set `_attr_entity_category = EntityCategory.CONFIG` on `UniFiClearCategoryButton` and `UniFiClearAllButton` (`button.py:37,63`).

### Testing
- **No multi-entry integration test:** verify two UniFi Alerts entries don't cross-contaminate coordinator/webhook state. Note: the webhook ID collision above means this test will fail until the code is fixed — write it first as a red-green pair.
- **No interleaving test:** assert that a webhook arriving mid-poll doesn't regress `is_alerting` (guard at `coordinator.py:92` should prevent it, but is untested).
- **No test for epoch-ms timestamp parsing:** add `test_from_api_alarm_epoch_ms` to `test_models.py`.
- **No test for dedup/rate limiting:** once the webhook debounce is implemented, add tests verifying cooldown behaviour.

### Release process / repo hygiene
- **No `CHANGELOG.md`:** add Keep-a-Changelog file, back-fill from v1.0.
- **Pinned SHAs need a refresh mechanism:** add Renovate or Dependabot config for `github-actions` updates.
- **Missing repo-hygiene files:** `SECURITY.md`, `CODEOWNERS`, GitHub issue templates.

### Documentation
- **No supported-firmware matrix:** small table of tested UDM-SE / UCG / UX / CloudKey Gen2 models with any known quirks.
- **No troubleshooting / FAQ section:** consolidate scattered notes (local_only webhooks, self-signed certs, UniFi OS vs legacy, API-key paths).

### Split `tests/unit/test_config_flow.py` into a package
**Problem:** `test_config_flow.py` is ~1060 lines with four logically independent test classes (`TestConfigFlowSteps`, `TestOptionsFlowSteps`, `TestOptionsFlowCredentials`, `TestReauthFlow`). The file is hard to load into context in full, and rebase chains that touch multiple classes (as with PR #19 + PR #20) produce interleaved merge conflicts that are tedious to reconstruct.
**Fix:** Convert to a package:
```
tests/unit/config_flow/
  __init__.py
  conftest.py           # shared fixtures + _make_options_flow / _make_reauth_flow helpers
  test_setup.py         # TestConfigFlowSteps (credentials → categories → done)
  test_options.py       # TestOptionsFlowSteps + TestOptionsFlowCredentials
  test_reauth.py        # TestReauthFlow
```
Move `_make_options_flow`, `_make_reauth_flow`, and any shared `MOCK_*` constants into the new `conftest.py`. Do not split the other test files — they are all under 500 lines and healthy. Target: a `v1.1.0-preN` checkpoint on `dev`.

---

## 🐛 Known issues / technical debt

### `_device_info` duplication
The `_device_info()` helper function is duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, and `button.py`. Intentional for platform isolation but could be extracted to a shared `entity_base.py` mixin if it becomes a maintenance burden.

