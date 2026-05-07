# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-05-07):** v1.4.0 released; v1.5.0 feature-complete on `dev` at `1.5.0-pre3` and pending field testing. Path to v2.0.0: v1.5.0 (security hardening II + field-confirmed reliability fixes), v1.6.0 (reliability + completeness), v1.7.0 (documentation + architecture), v2.0.0 (HACS default).

> **Branching model:** see `CLAUDE.md § Branching strategy and versioning`.

---

## v1.5.0: Security hardening II + field-confirmed reliability fixes

Closes the remaining auth/credential exposure paths, makes the options flow transactionally safe, and lands the two reliability bugs confirmed in field testing.

### Options-flow atomicity

- [x] **Stage credential changes** (`config_flow.py`): `async_step_credentials` no longer calls `async_update_entry()` eagerly; new credentials, rotated webhook secrets, and `verify_ssl` flips are staged in `self._pending_data` and persisted atomically by `async_step_finish`.
- [x] **`verify_ssl` toggle alone now persists**: change detection no longer filters out the SSL flag, so flipping the checkbox without any credential change is staged and committed.

### Reliability (pulled forward from v1.6.0; field-confirmed)

- [x] **Polling re-asserts `is_alerting` for alarms older than the watermark** ([#72]): `_async_update_data()` now uses the watermark-filtered list when deciding whether to flip `is_alerting`, so a stale pre-Clear alarm cannot re-assert Problem after auto-clear.
- [x] **`_auto_clear` watermark persistence** ([#72]): `_auto_clear()` now awaits `_async_persist_watermarks()` after `state.clear()`. Companion test `test_auto_clear_persists_watermark` added.
- [x] **`open_count` lags on webhook path** ([#72]): `push_alert()` now optimistically increments `open_count` when `alert.received_at > state.last_cleared_at`. Polling reconciles to the authoritative value on the next refresh. Root cause 2 (busy controllers, /list/alarm 3000-record cap) remains addressed by the v2 polling strategy switch in v1.6.0.

---

## v1.6.0: Reliability + completeness

Closes remaining correctness gaps and polishes testing. The watermark re-assertion, auto-clear persistence, and open_count webhook-path bugs were pulled forward into v1.5.0.

### Reliability

- [ ] **`_category_states` rebuild discards counters on reload**: `alert_count` and `last_alert` are lost on every reload. Persist alongside watermarks in the `Store`.
- [ ] **Epoch-ms timestamp parsing** (`models.py:54-63`): numeric strings silently fall back to `now(UTC)`. Add an epoch-ms branch + `test_from_api_alarm_epoch_ms`. Note: the v2 `system-log` API always returns epoch-ms in its `timestamp` field, so this fix is a prerequisite for the v2 polling strategy below.
- [ ] **Silent JSON-parse failure during 400-error inspection** (`unifi_client.py`): `except Exception: pass` masks malformed UniFi error bodies. Log at DEBUG with the exception class name.
- [ ] **Switch polling to v2 system-log API** (`unifi_client.py`): `/list/alarm` caps at ~3000 records oldest-first; on controllers with more than ~33 alarms/day, recent alarms are never in the polled response and `open_count` is always 0 via polling. The v2 `POST /proxy/network/v2/api/site/{site}/system-log/all` endpoint accepts `timestampFrom`/`timestampTo` (epoch ms) and `pageNumber`/`pageSize`; field-confirmed on Network 10.3.58. Implementation: probe `/system-log/count` on startup; if available, poll `system-log/all` with `timestampFrom = last_cleared_at or (now - 24h)` and page through results; fall back to legacy `/list/alarm` for older controllers. Requires `UniFiAlert.from_system_log_event()` (v2 schema uses `message_raw` + `parameters` templates, epoch-ms `timestamp`, `status: "NEW"`, and a new key format with no `EVT_` prefix) and a separate v2 key-to-category map. See `docs/UNIFI.md § v2 system-log API` and `docs/research/alert-endpoints.md`.

### Testing / tooling

- [ ] **`make lint` to cover `tests/`**: expand the Makefile target; resolve the six pre-existing `I001`/`F401` issues.
- [ ] **Webhook-mid-poll interleaving test** (`test_coordinator.py`): assert a webhook during `_async_update_data()` cannot regress `is_alerting`.

### Tech debt

- [ ] **Buttons inherit `CoordinatorEntity`** (`button.py`): add the mixin + `available` property tied to `state.enabled`, consistent with the other platforms.

---

## v1.7.0: Documentation + architecture

Closes the remaining documentation gaps and the largest architecture items.

### Architecture

- [ ] **`mypy strict = true`**: migrate `UniFiClient.config: dict[str, Any]` to a `TypedDict` or frozen dataclass; bump `pyproject.toml`.
- [ ] **`has_entity_name = True` + `_attr_translation_key`**: move display strings out of platform files into `strings.json`. Unlocks localisation.
- [ ] **Split `tests/unit/test_config_flow.py` into a package**: ~1405 lines, four independent classes. Convert to `tests/unit/config_flow/{__init__,conftest,test_setup,test_options,test_reauth}.py`.
- [ ] **Sensor `device_class` / `state_class`** (`sensor.py`): decide whether a class fits the open-count / rollup-count sensors.

### Documentation

- [ ] **Supported-firmware matrix**: README/info.md table of tested UDM-SE / UCG-Ultra / UCG-Max / Cloud Key Gen2+ models with firmware and known quirks.
- [ ] **Troubleshooting / FAQ section**: consolidate scattered notes.
- [ ] **Uninstall instructions**: Settings > Devices & Services > UniFi Alerts > ⋮ > Delete.
- [ ] **`info.md` local-network warning**: "⚠ Local network only: webhooks are not reachable over Nabu Casa remote access" in the first paragraph.
- [ ] **Setup-flow webhook copy warning**: `strings.json` note on the finish step.
- [ ] **Privacy / data-retention section** in README: which fields are stored, locally only, auto-clear timing.
- [ ] **Automation edge case**: disabling a category in options makes its event entity unavailable.
- [ ] **`unique_id` format**: document `{entry_id}_{category}_{sensor_type}`; UI renames preserve unique_id.

### QA

- [ ] **Verify update-in-place**: HACS file copy + config-entry reload sufficient; no HA restart required.
- [ ] **Optional: integration test for full rotation cycle**: options-flow > entry-update > reload > re-register, end-to-end.

---

## v2.0.0: HACS default catalogue

Prerequisites for submitting to <https://github.com/hacs/default>.

- [ ] All v1.x items above resolved.
- [ ] Submit PR to `hacs/default`.

---

## Deferred / low priority

- Extract `_device_info()` duplication into a shared `entity_base.py` mixin (only if maintenance burden grows).
- Configurable site per category (power-user feature).

[#72]: https://github.com/PHeonix25/unifi_alerts/pull/72
