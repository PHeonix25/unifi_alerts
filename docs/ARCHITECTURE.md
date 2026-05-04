# ARCHITECTURE.md

## Overview

The integration has three layers: **data ingestion** (webhook + polling), **state management** (coordinator), and **HA entity projection** (platforms). These are deliberately kept separate — no entity holds its own state.

> **Scope:** UniFi Network alerts only (System Logs / SIEM). UniFi Protect is out of scope — different API, different event taxonomy, not implemented.

```
UniFi Controller
    │
    ├─── HTTP POST ──► WebhookManager ──► coordinator.push_alert()
    │    (real-time)                              │
    │                                             ▼
    └─── HTTP GET ────► UniFiClient ──────► coordinator._async_update_data()
         (polling)      (aiohttp)                 │
                                                  ▼
                                    UniFiAlertsCoordinator
                                    ┌─────────────────────┐
                                    │ _category_states     │
                                    │   {category: State}  │
                                    │                     │
                                    │ any_alerting         │
                                    │ rollup_*             │
                                    └─────────┬───────────┘
                                              │ async_set_updated_data()
                                              ▼
                          ┌───────────────────────────────┐
                          │  CoordinatorEntity subclasses │
                          │  binary_sensor / sensor /     │
                          │  event / button               │
                          └───────────────────────────────┘
```

## Module responsibilities

### `models.py`
Pure data — no HA dependencies. Two dataclasses:

- **`UniFiAlert`** — immutable snapshot of a single alert event. Built from either a webhook payload (`from_webhook_payload`) or a polled alarm record (`from_api_alarm`). Both constructors normalise field names across the inconsistent UniFi API surface.
- **`CategoryState`** — mutable runtime state for one category. Owned exclusively by the coordinator. Tracks `is_alerting`, `last_alert`, `alert_count` (webhook-incremented), `open_count` (poll-set), and `last_cleared_at`. The `last_cleared_at` field doubles as the **acknowledgement watermark**: `open_count` only counts polled alarms newer than this timestamp, so pressing Clear bounds the counter to "since last acknowledged" rather than a lifetime total.

### `const.py`
Single source of truth for:
- Category identifiers (`CATEGORY_*` string constants)
- `ALL_CATEGORIES` ordered list (defines display order)
- `CATEGORY_LABELS`, `CATEGORY_ICONS`, `CATEGORY_ICONS_OK` — UI metadata per category
- `UNIFI_KEY_TO_CATEGORY` — maps UniFi event key prefixes to category identifiers. This is community-sourced and deliberately incomplete; unrecognised keys are silently skipped.
- Config entry key names (`CONF_*`)
- Runtime data keys (`DATA_*`) used in `hass.data[DOMAIN][entry_id]`

### `unifi_client.py`
Stateful async HTTP client. Responsible for:
- Detecting whether the controller is UniFi OS (UDM/UCG) or legacy self-hosted, and adjusting API paths accordingly (`/proxy/network` prefix on UniFi OS)
- Auto-detecting auth: tries API key first, falls back to username/password session cookies
- Fetching and filtering unarchived alarms from `/api/s/{site}/alarm`
- Classifying raw alarm dicts into categories via `_classify()` (static method, pure function, easily testable)

**Auth state is held in the client instance.** On `InvalidAuthError` during a poll, the coordinator re-authenticates once and retries.

### `coordinator.py`
The integration's single source of truth at runtime. Key design decisions:

- **`_category_states` is long-lived** — it is not re-created on each poll. Polling only updates `open_count` and may apply an alert if the category is not already alerting. Webhook pushes update `is_alerting` and `alert_count` immediately.
- **Auto-clear** — each `push_alert()` cancels any existing `asyncio.Task` for that category and schedules a new one. This means repeated alerts from the same category reset the clear timer rather than stacking.
- **`async_set_updated_data()`** is called on webhook push to bypass the polling interval and notify entities immediately.
- **Polling does not clear `is_alerting`** — only the auto-clear timeout or a button press does. This prevents a polling race where a momentarily empty alarm list falsely clears an active alert.
- **Acknowledgement watermarks** — `last_cleared_at` on each `CategoryState` acts as a per-category watermark. Polling counts only alarms newer than the watermark (`open_count` = alarms since last Clear). Watermarks are persisted via `homeassistant.helpers.storage.Store` (keyed per entry) so they survive HA restarts. `async_clear_category()` and `async_clear_all()` are the sole entry points for clearing — they cancel auto-clear tasks, call `state.clear()` (which advances the watermark), persist to storage, and notify entities. Buttons and services delegate to these methods rather than mutating state directly.

### `webhook_handler.py`
Registers one HA webhook per enabled category using `homeassistant.components.webhook`. Webhooks are:
- Scoped to `local_only=True` (LAN only)
- Accepted on POST only — GET requests are rejected with HTTP 405. UniFi Alarm Manager must be configured to send POST.
- Parsed as JSON; gracefully falls back to `{}` on parse failure

The webhook ID format is `unifi_alerts_{category}`. IDs are deterministic so they survive HA restarts without re-registration.

### `config_flow.py`
Three-step setup flow:
1. **`async_step_user`** — URL + credentials. Calls `UniFiClient.authenticate()` as a validation step. On success, stores credentials and the detected auth method in `self.context`.
2. **`async_step_categories`** — one boolean toggle per category, plus `poll_interval` and `clear_timeout`.
3. **`async_step_finish`** — displays the generated webhook URLs (with bearer token) for the user to copy into UniFi Alarm Manager.

An `OptionsFlow` (`UniFiAlertsOptionsFlow`) mirrors step 2 and allows reconfiguring categories and timing without re-entering credentials. Option changes trigger an entry reload via `_async_update_listener`.

### Platform files (`binary_sensor.py`, `sensor.py`, `event.py`, `button.py`)
All entity classes extend `CoordinatorEntity[UniFiAlertsCoordinator]` (except `ButtonEntity`, which doesn't need coordinator updates). They read exclusively from `self.coordinator.get_category_state(category)` — no local caching.

**Event entities** (`event.py`) detect new alerts by comparing `state.alert_count` to `self._last_seen_count` in `_handle_coordinator_update`. This is the correct pattern — event entities fire on change, not on state.

**Device grouping** — all entities share the same `_device_info` dict (`identifiers={(DOMAIN, entry.entry_id)}`), so HA groups them under a single "UniFi Alerts" device in the device registry.

## Config entry data structure

After setup, `entry.data` contains:

```python
{
    "controller_url": "https://192.168.1.1",
    "username": "admin",           # may be absent if API key used
    "password": "...",             # may be absent if API key used
    "api_key": "...",              # may be absent if user/pass used
    "auth_method": "userpass",     # or "apikey" — detected at setup time
    "verify_ssl": False,
    "enabled_categories": ["network_device", "network_wan", ...],
    "poll_interval": 60,
    "clear_timeout": 30,
}
```

`entry.options` contains only the reconfigurable subset: `enabled_categories`, `poll_interval`, `clear_timeout`. In `__init__.py`, these are merged: `dict(entry.data) | dict(entry.options)` so options always win.

## Tooling and validation

The `scripts/` directory contains project-level tooling that is not part of the integration itself:

- **`scripts/validate_hacs.py`** — pure-Python HACS manifest pre-flight. Checks `manifest.json` for required fields, valid `iot_class`, correct version format, and that `dependencies` contains no HA core built-ins (which the HACS action rejects). Run via `make validate` or automatically by the pre-push hook and CI's `hacs-preflight` job.

The `Makefile` provides convenience targets (`make check`, `make lint`, `make test`, etc.) that wrap the venv commands. `requirements-dev.txt` is the single source of truth for dev dependencies — used by `make setup` and both CI jobs.

## Key invariants

- `CategoryState` instances are created once at coordinator init and mutated in place — never replaced.
- `open_count` is authoritative from polling only. `is_alerting` is authoritative from webhooks (or polling as fallback if the category wasn't already alerting).
- Entities must never call `hass.data` directly — always go through the coordinator reference held in `self.coordinator`.
- Webhook URLs are generated by HA and depend on the `base_url` configured in HA's network settings. They are not stored in the config entry — they are re-generated at runtime.
