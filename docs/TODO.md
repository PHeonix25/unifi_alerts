# TODO.md

Outstanding work only — items are removed when they ship. The historical record of completed work lives in `docs/HISTORY.md`; per-release status is tracked in `docs/ROADMAP.md`.

Items are grouped by type. Work top-to-bottom within each group unless there's a dependency noted.

## 🔵 v1.4.0 — UniFi OS only

**Decision (2026-04-22):** officially support only UniFi OS controllers. Classic self-hosted controllers (Network Application on bare Linux/Windows) are excluded. See `ROADMAP.md § v1.4.0` for full rationale. (Was planned for v1.3.0; deferred to v1.4.0 to ship v1.3.0 bug fixes first.)

### Document the prerequisite (do first — ships ahead of code change)

**Add "Requires UniFi OS" to README.md and info.md** — opening paragraph + Prerequisites section; list tested models (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+); bold "⚠ Requires UniFi OS" callout in `info.md` first paragraph. This must land before the code change so any existing users on classic controllers get advance notice via the HACS update description.

### Remove legacy self-hosted code paths (do after docs)

**Strip `unifi_client.py` of non-UniFi-OS paths** — removes `_detect_unifi_os()`, the `_network_path()` method, login path ordering in `_login_userpass()`, logout branch in `close()`, and `CONF_IS_UNIFI_OS` persistence in config flow + `const.py`. Also remove/update tests that existed only to cover the legacy path. Expected reduction: ~30-40 lines. See `ROADMAP.md § v1.4.0` for the full list of touch points.

---

## 🟡 High-value improvements

### Expose `last_acknowledged_at` in diagnostics

The `last_cleared_at` watermark per category is not currently surfaced in the diagnostics platform. Add it to `diagnostics.py` alongside `open_count` and `is_alerting` so users can debug unexpected `open_count` values. Low-effort, diagnostic-only change.

### Verify update-in-place works without HA reboot

**Problem:** Unknown whether updating the integration (e.g. via HACS or copying files) requires a full Home Assistant restart, or whether reloading the config entry is sufficient. A reboot requirement would be a significant friction point for self-hosted users pushing frequent updates.
**Fix:** Test the update-in-place flow manually:

1. Install the integration and confirm it is working.
2. Update the integration files (e.g. simulate a HACS update by copying a newer version).
3. Reload the config entry via **Settings → Integrations → UniFi Alerts → ⋮ → Reload**.
4. Confirm all entities recover and no HA restart is required.
If a restart is required, investigate why (e.g. Python module caching, import-time side effects, platform registration) and fix so a config entry reload is sufficient. Document the expected update flow in `README.md`.

### Update all documentation and examples

**Update docs and README examples to reflect application changes** — remove references to self-hosted controllers, update screenshots if needed, adjust troubleshooting tips. This is mostly copyediting but should be done carefully to avoid leaving any legacy-controller references. Additionally, make sure that all examples line up with the code, for example: Home Assistants sensor names in the card & automation examples should match the new `unique_id` format, and the config flow screenshots should reflect any UI changes.

---

## 🟢 Nice-to-have

### HACS default repository submission

After the integration is stable and passes `hassfest`, submit a PR to <https://github.com/hacs/default> to be listed in the default HACS catalogue. Requirements: 2+ releases, passing CI, `hacs.json`, `info.md`, HA brand icon. Remaining work: real brand icon (replace placeholder), PR submission to hacs/default.

---

## 🔥 v1.4.0 — Hardening backlog (critical-review carry-overs)

Items from the post-v1.1 audit that were planned for v1.2.0 but carried forward. Now targeting v1.4.0. Full detail (with file:line anchors and suggested fixes) is in `ROADMAP.md § v1.4.0`. Grouped by impact:

### Reliability / correctness

- **SSL fail-open on missing key:** `ssl=self._config.get(CONF_VERIFY_SSL, False)` — change fallback to `DEFAULT_VERIFY_SSL` so a missing key fails closed (`unifi_client.py:106`).
- **SSL fail-open in 4 more call sites:** same `False` default in `_detect_unifi_os()` (`:156`), `_verify_api_key()` (`:202`), `_login_userpass()` (`:238`), and `close()` (`:139`).
- **Category state lost on reload:** `_category_states` is rebuilt from scratch on every options change; persist `alert_count` and `last_alert` across reloads (`coordinator.py:59-62`).
- **Epoch-ms timestamps silently dropped:** `from_api_alarm()` calls `datetime.fromisoformat()` on numeric timestamps, fails, falls back to `now(UTC)` — real alarm time lost (`models.py:52-57`). Add an epoch-ms branch before the ISO fallback; log at WARNING when neither matches.
- **`open_count` stale on webhook path:** `push_alert()` updates `is_alerting` and `alert_count` but `open_count` stays at whatever the last poll returned (`coordinator.py:123-143`).
- **`close()` swallows logout errors:** `unifi_client.py:142-143` (`except Exception: pass`). Log at WARNING with class name so operators see stuck sessions.
- **Silent JSON-parse failure during 400-error inspection:** `unifi_client.py:153-154` — `except Exception: pass` swallows any failure to parse the UniFi JSON error body, so the `api.err.InvalidObject` fallback is silently skipped if the body is malformed. Log at DEBUG (or WARNING) with the exception class name so future endpoint variations are diagnosable. Found in 2026-04-29 BEFORE-state audit.

### Security

- **`allow_redirects=True` on probes:** `unifi_client.py:162,178` — disable redirects or assert final-URL host matches configured host.
- **Config flow creates bare `aiohttp.ClientSession`:** bypasses HA's proxy config, connection pool, and SSL settings. Should use `async_get_clientsession(self.hass, verify_ssl=...)` (`config_flow.py:80,234,343`).
- **Credential fragments in `__init__.py` exception messages:** `err` is passed into `ConfigEntryAuthFailed`/`ConfigEntryNotReady`, may expose URL fragments or auth details in logs (`__init__.py:53-57`).
- **Document that secret rotation rotates the bearer token but reuses the webhook ID:** AFTER audit (2026-04-29) noted that rotation changes the `?token=` query parameter but not the URL path. An attacker who captured the old token still hits a live endpoint; the token check rejects them. If true revocation is ever required, the suffix would also need to rotate. Add a paragraph to `SECURITY.md` and a `# WHY:` comment in `config_flow.py` near the rotation branch.
- **Options-flow credential changes persist before the user submits the flow:** raised by Copilot review on PR #50. `UniFiAlertsOptionsFlow.async_step_credentials` calls `async_update_entry()` for both the credential-validation branch and (after PR #50) the rotate-only branch. If the user advances past credentials but then abandons the flow on categories/finish, the new values are already persisted and the entry-reload listener may have fired. Pre-existing pattern, not introduced by cluster A — but worth fixing. Refactor: stage credentials/secret in flow state (`self._pending_data`) and persist atomically inside `async_step_finish` alongside the options. Touches the credentials and rotation branches together.
- **`verify_ssl` toggle alone does not persist in the options flow:** raised by Copilot review on PR #50. `credentials_changed` only checks URL/username/password/api_key — flipping the verify-SSL checkbox without changing any credential short-circuits to the categories step and the new `verify_ssl` value is never written to `entry.data`. Pre-existing, not introduced by cluster A. Fix: include `new_verify_ssl != self._config_entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)` in the `credentials_changed` predicate, or treat verify-SSL as its own change trigger. Best landed alongside the staging refactor above.

### Type safety / tech debt

- **`mypy strict = false`:** migrate `UniFiClient.config: dict[str, Any]` to a TypedDict / frozen dataclass, then bump `pyproject.toml` to `strict = true`.
- **Ad-hoc entity naming:** adopt `has_entity_name = True` + `_attr_translation_key` pattern across `binary_sensor.py`, `sensor.py`, `event.py`, `button.py` so names live in `strings.json`.
- **No sensor `device_class`:** consider what fits on the open-count / rollup-count sensors (`sensor.py:96,128`).
- **Config flow accesses private `client._is_unifi_os`:** expose as a public `@property` on `UniFiClient` (`config_flow.py:99,253,372`).

### Testing

- **No interleaving test:** assert that a webhook arriving mid-poll doesn't regress `is_alerting` (guard at `coordinator.py:92` should prevent it, but is untested).
- **No test for epoch-ms timestamp parsing:** add `test_from_api_alarm_epoch_ms` to `test_models.py`.
- **`make lint` does not cover `tests/`:** the Makefile's `lint` target only runs ruff against `custom_components/`. AFTER audit (2026-04-29) found 6 pre-existing `I001` / `F401` issues in `tests/unit/test_services.py` and `tests/unit/test_config_flow.py` (mid-function imports, unused imports) that escaped local validation. None were introduced by clusters A or D. Expand the lint target to include `tests/` and either fix or `# noqa` the existing issues.
- **Optional follow-up:** integration test for the full options-flow → entry-update → reload → re-register cycle after secret rotation. The unit-level rotation tests cover each step in isolation; an end-to-end test would be an extra guard. Lower priority since each step is already covered.

### Documentation

- **No supported-firmware matrix:** small table of tested UDM-SE / UCG / UX / CloudKey Gen2 models with any known quirks.
- **No troubleshooting / FAQ section:** consolidate scattered notes (local_only webhooks, self-signed certs, UniFi OS vs legacy, API-key paths).
- **No uninstall instructions** in README / info.md.
- **`info.md` missing upfront local-network warning** — remote-access / Nabu Casa users hit silent failure.
- **Setup flow doesn't warn "copy URLs before Submit"** — the URLs screen is the final step; users close the dialog without copying.
- **No privacy / data-retention section** in README explaining which UniFi payload fields are stored in HA state.
- **Automation README example** doesn't document that disabling a category in options makes its event entity unavailable, breaking dependent automations.
- **`unique_id` format is undocumented** — users wiring into long-lived automations don't know if UI renames are safe.

### Split `tests/unit/test_config_flow.py` into a package

**Problem:** `test_config_flow.py` is ~1060 lines with four logically independent test classes (`TestConfigFlowSteps`, `TestOptionsFlowSteps`, `TestOptionsFlowCredentials`, `TestReauthFlow`). The file is hard to load into context in full, and rebase chains that touch multiple classes (as with PR #19 + PR #20) produce interleaved merge conflicts that are tedious to reconstruct.
**Fix:** Convert to a package:

```plain
tests/unit/config_flow/
  __init__.py
  conftest.py           # shared fixtures + _make_options_flow / _make_reauth_flow helpers
  test_setup.py         # TestConfigFlowSteps (credentials → categories → done)
  test_options.py       # TestOptionsFlowSteps + TestOptionsFlowCredentials
  test_reauth.py        # TestReauthFlow
```

Move `_make_options_flow`, `_make_reauth_flow`, and any shared `MOCK_*` constants into the new `conftest.py`. Do not split the other test files — they are all under 500 lines and healthy.

---

## 🐛 Known issues / technical debt

### `_device_info` duplication

The `_device_info()` helper function is duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, and `button.py`. Intentional for platform isolation but could be extracted to a shared `entity_base.py` mixin if it becomes a maintenance burden.
