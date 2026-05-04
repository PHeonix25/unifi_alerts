# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-05-04):** v1.4.0 released. Active development on `dev` at `1.5.0-pre1`. Path to v2.0.0: v1.5.0 (security hardening II), v1.6.0 (reliability + completeness), v1.7.0 (documentation + architecture), v2.0.0 (HACS default).

> **Branching model:** see `CLAUDE.md § Branching strategy and versioning`.

---

## v1.5.0: Security hardening II

Closes the remaining auth/credential exposure paths and makes the options flow transactionally safe.

### Options-flow atomicity

- [ ] **Stage credential changes** (`config_flow.py`): `async_step_credentials` calls `async_update_entry()` eagerly. Abandoning the flow after credentials but before finish leaves the change persisted. Stage into `self._pending_data`, persist atomically in `async_step_finish`.
- [ ] **`verify_ssl` toggle alone must persist**: `credentials_changed` ignores the SSL flag. Roll into the staging refactor above.

---

## v1.6.0: Reliability + completeness

Closes correctness gaps and polishes testing.

### Reliability

- [ ] **Polling re-asserts `is_alerting` for alarms older than the watermark** (`coordinator.py:127-134`): `_async_update_data()` filters by `last_cleared_at` when computing `open_count` but uses the unfiltered list when deciding whether to flip `is_alerting` and update `last_alert`. After Clear, `open_count` zeroes but the next poll re-asserts `is_alerting` from the same pre-watermark alarm — UI shows status=Problem with a stale message + Open Count=0. Field-confirmed via screenshots from a real install. Fix: apply the watermark filter to the `is_alerting` branch too. Pair with a regression test in `test_coordinator.py`.
- [ ] **`_auto_clear` watermark persistence** (`coordinator.py:298-304`): `state.clear()` advances `last_cleared_at` in memory but `_async_persist_watermarks()` is never awaited. Fix + `test_auto_clear_persists_watermark`.
- [ ] **`open_count` stale on webhook path** (`coordinator.py`): `push_alert()` does not update `open_count`. Optimistic increment + poll-time correction.
- [ ] **`_category_states` rebuild discards counters on reload**: `alert_count` and `last_alert` are lost on every reload. Persist alongside watermarks in the `Store`.
- [ ] **Epoch-ms timestamp parsing** (`models.py:54-63`): numeric strings silently fall back to `now(UTC)`. Add an epoch-ms branch + `test_from_api_alarm_epoch_ms`.
- [ ] **Silent JSON-parse failure during 400-error inspection** (`unifi_client.py`): `except Exception: pass` masks malformed UniFi error bodies. Log at DEBUG with the exception class name.

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
