# Roadmap

What's planned next. Items ship from `dev` under `X.Y.Z-preN`, then promote to `main` as `X.Y.Z`. Completed work is removed from this file; the historical record lives in `docs/HISTORY.md`, and the user-visible release summary lives in `CHANGELOG.md`.

> **Status (2026-05-07):** v1.5.0 released; active development on `dev` at `1.6.0-pre1`. Path to v2.0.0: v1.6.0 (reliability + completeness), v1.7.0 (documentation + architecture), v2.0.0 (HACS default).

> **Branching model:** see `CLAUDE.md § Branching strategy and versioning`.

---

## v1.6.0: Reliability + completeness

Closes remaining correctness gaps and polishes testing. The watermark re-assertion, auto-clear persistence, and open_count webhook-path bugs were pulled forward into v1.5.0.

### Reliability

- [ ] **`_category_states` rebuild discards counters on reload**: `alert_count` and `last_alert` are lost on every reload. Persist alongside watermarks in the `Store`.
- [ ] **Switch polling to v2 system-log API** (`unifi_client.py`): `/list/alarm` caps at ~3000 records oldest-first; on controllers with more than ~33 alarms/day, recent alarms are never in the polled response and `open_count` is always 0 via polling. The v2 `POST /proxy/network/v2/api/site/{site}/system-log/all` endpoint accepts `timestampFrom`/`timestampTo` (epoch ms) and `pageNumber`/`pageSize`; field-confirmed on Network 10.3.58. Implementation: probe `/system-log/count` on startup; if available, poll `system-log/all` with `timestampFrom = last_cleared_at or (now - 24h)` and page through results; fall back to legacy `/list/alarm` for older controllers. Requires `UniFiAlert.from_system_log_event()` (v2 schema uses `message_raw` + `parameters` templates, epoch-ms `timestamp`, `status: "NEW"`, and a new key format with no `EVT_` prefix) and a separate v2 key-to-category map. See `docs/UNIFI.md § v2 system-log API` and `docs/research/alert-endpoints.md`.

### Testing / tooling

- [ ] **Webhook-mid-poll interleaving test** (`test_coordinator.py`): assert a webhook during `_async_update_data()` cannot regress `is_alerting`.

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
