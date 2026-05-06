# Architecture

## Overview

The integration has three layers: **data ingestion** (webhook + polling), **state management** (coordinator), and **HA entity projection** (platforms). These are kept separate; no entity holds its own state.

> **Scope:** UniFi Network alerts only (System Logs / SIEM events). UniFi Protect is out of scope (different API, different event taxonomy).

> **Controller scope:** UniFi OS consoles only (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+). Classic self-hosted Network Application is not supported as of v1.4.0.

```
UniFi Controller
    |
    |--- HTTP POST --> WebhookManager --> coordinator.push_alert()
    |    (real-time)                              |
    |                                             v
    |--- HTTP GET  --> UniFiClient   --> coordinator._async_update_data()
         (polling)     (aiohttp)                  |
                                                  v
                                    UniFiAlertsCoordinator
                                    +--------------------+
                                    | _category_states   |
                                    |   {category: State}|
                                    | any_alerting       |
                                    | rollup_*           |
                                    +---------+----------+
                                              | async_set_updated_data()
                                              v
                          +-------------------------------+
                          |  CoordinatorEntity subclasses |
                          |  binary_sensor / sensor /     |
                          |  event / button               |
                          +-------------------------------+
```

## Module responsibilities

### `models.py`

Pure data; no HA dependencies. Three dataclasses:

- **`UniFiAlert`**: immutable snapshot of a single alert event. Built from either a webhook payload (`from_webhook_payload`) or a polled alarm record (`from_api_alarm`). Both constructors normalise field names across the inconsistent UniFi API surface.
- **`CategoryState`**: mutable runtime state for one category. Owned exclusively by the coordinator. Tracks `enabled`, `is_alerting`, `last_alert`, `alert_count` (webhook-incremented), `open_count` (poll-set), `last_cleared_at`. The `last_cleared_at` field doubles as the **acknowledgement watermark**: `open_count` only counts polled alarms newer than this timestamp, so pressing Clear bounds the counter to "since last acknowledged" rather than a lifetime total.
- **`RuntimeData`**: container stored on `entry.runtime_data`. Holds the coordinator, generated webhook URLs, the unregister callable, and the `UniFiClient` instance.

### `const.py`

Single source of truth for:

- Category identifiers (`CATEGORY_*` string constants), `ALL_CATEGORIES` ordered list (defines display order), `CATEGORY_LABELS`, `CATEGORY_ICONS`, `CATEGORY_ICONS_OK` UI metadata.
- `UNIFI_KEY_TO_CATEGORY`: maps UniFi event-key prefixes to category identifiers. Community-sourced and deliberately incomplete; unrecognised keys are logged at DEBUG and skipped.
- Config entry key names (`CONF_*`).
- `webhook_id_for_category(category, suffix="")`: deterministic webhook ID generator. With a per-entry suffix it returns `unifi_alerts_{suffix}_{category}`; without one (legacy single-entry installs) it returns `unifi_alerts_{category}`.

### `unifi_client.py`

Stateful async HTTP client. Always uses the UniFi OS API surface:

- `/proxy/network/api/...` for the alarm endpoint.
- `/api/auth/login` and `/api/auth/logout` for username/password auth.
- API-key auth verifies against `/proxy/network/api/s/default/self`.

Auto-detects auth method: tries API key first if present, falls back to username/password session cookies. Auth state is held on the client instance; on `InvalidAuthError` during a poll, the coordinator re-authenticates once and retries.

`fetch_alarms()` walks the alarm-endpoint probe chain `[/list/alarm, /alarm, /stat/alarm]` (newest UniFi Network firmware first); 404 / 400 falls through to the next path, only surfacing an error after every path is exhausted.

`_classify()` is a static method (pure function, easily testable) mapping raw alarm dicts to categories.

### `coordinator.py`

The integration's single source of truth at runtime. Key design decisions:

- **`_category_states` is long-lived**: not re-created on each poll. Polling updates `open_count` and may apply an alert if the category is not already alerting. Webhook pushes update `is_alerting` and `alert_count` immediately.
- **Auto-clear**: each `push_alert()` cancels any existing `asyncio.Task` for that category and schedules a new one via `hass.async_create_background_task`. Repeated alerts reset the timer rather than stacking.
- **`async_set_updated_data()`** is called on webhook push to bypass the polling interval and notify entities immediately.
- **Polling does not clear `is_alerting`**: only the auto-clear timeout or a button press does. Prevents a polling race where a momentarily empty alarm list falsely clears an active alert.
- **Acknowledgement watermarks**: `last_cleared_at` on each `CategoryState` is the per-category watermark. Polling counts only alarms newer than the watermark (`open_count` = "alarms since last Clear"). Watermarks persist via `homeassistant.helpers.storage.Store` (keyed per entry) so they survive HA restarts. `async_clear_category()` and `async_clear_all()` are the sole entry points for clearing: cancel auto-clear tasks, call `state.clear()` (advances the watermark), persist, notify. Buttons and services delegate to these methods.
- **Webhook debounce**: `push_alert()` keeps `_last_push_at` per `(category, alert_key)` and drops repeats inside `WEBHOOK_DEDUP_WINDOW_SECONDS = 5.0`. Stale entries are pruned opportunistically so the dict is bounded by "distinct (category, key) pairs within the window", not the controller's lifetime vocabulary.

### `webhook_handler.py`

Registers one HA webhook per enabled category using `homeassistant.components.webhook`. Webhooks are:

- Scoped to `local_only=True` (LAN only).
- Accepted on POST only; GET requests are rejected with HTTP 405. UniFi Alarm Manager must be configured to send POST.
- Bearer-token authenticated: `?token=` query parameter compared against `CONF_WEBHOOK_SECRET` via `hmac.compare_digest`.
- Body-capped at `WEBHOOK_MAX_BODY_BYTES`; oversized bodies return HTTP 413.
- Parsed as JSON; decode failures log at WARNING with class name and 80-byte body preview, then fall back to `{}`.
- DEBUG-payload narrowed to `{category, alert_key, severity, device_name, key}` to avoid surfacing future-firmware fields.

The webhook ID format is `unifi_alerts_{suffix}_{category}` when a per-entry `CONF_WEBHOOK_ID_SUFFIX` is present (always set on new entries from v1.4.0 onwards), or `unifi_alerts_{category}` for legacy single-entry installs. IDs are deterministic so they survive HA restarts without re-registration. Multi-entry isolation is the suffix's whole purpose.

### `config_flow.py`

Three-step setup flow:

1. **`async_step_user`**: URL + credentials. Calls `UniFiClient.authenticate()` for validation. Generates `CONF_WEBHOOK_SECRET` (`secrets.token_urlsafe(32)`) and `CONF_WEBHOOK_ID_SUFFIX` (`secrets.token_hex(4)`) on success.
2. **`async_step_categories`**: per-category boolean toggles plus `poll_interval`, `clear_timeout`, and `site`.
3. **`async_step_finish`**: displays generated webhook URLs (with bearer token) for the user to copy into UniFi Alarm Manager.

`UniFiAlertsOptionsFlow` mirrors all three steps, allowing credentials, categories, and timing to be reconfigured in place. The credentials step also offers a "Regenerate webhook secret" checkbox. Option changes trigger an entry reload via `_async_update_listener`.

`async_step_reauth` / `async_step_reauth_confirm` implement HA's reauth convention; an `issue_registry` repair card surfaces in Settings > Repairs on auth failure.

### Platform files (`binary_sensor.py`, `sensor.py`, `event.py`, `button.py`)

All entity classes extend `CoordinatorEntity[UniFiAlertsCoordinator]` (except `ButtonEntity`, which currently does not subscribe to coordinator updates; see TODO). They read exclusively from `self.coordinator.get_category_state(category)`; no local caching.

**Event entities** (`event.py`) detect new alerts by comparing `state.alert_count` to `self._last_seen_count` in `_handle_coordinator_update`. Event entities fire on change, not on state. Polling does not increment `alert_count`, so events fire only on real webhook pushes.

**Device grouping**: all entities share the same `_device_info` dict (`identifiers={(DOMAIN, entry.entry_id)}`); HA groups them under a single "UniFi Alerts" device with `entry_type=DeviceEntryType.SERVICE` and `configuration_url` pointing at the controller.

## Config entry data structure

After setup, `entry.data` contains:

```python
{
    "controller_url": "https://192.168.1.1",
    "username": "admin",                    # absent if API key used
    "password": "...",                      # absent if API key used
    "api_key": "...",                       # absent if user/pass used
    "auth_method": "userpass",              # or "apikey"; detected at setup
    "verify_ssl": True,
    "webhook_secret": "...",                # token_urlsafe(32)
    "webhook_id_suffix": "...",             # token_hex(4); per-entry
    "enabled_categories": ["network_device", "network_wan", ...],
    "poll_interval": 60,
    "clear_timeout": 30,
    "site": "default",
}
```

`entry.options` carries the reconfigurable subset (categories, poll_interval, clear_timeout, site); `entry.data | entry.options` is computed at coordinator setup so options always win.

Runtime state lives on `entry.runtime_data` (`RuntimeData` dataclass): coordinator, webhook URLs, unregister callable, client. Not in `hass.data`.

`ConfigFlow.VERSION = 2`. `async_migrate_entry` strips the legacy `is_unifi_os` key from version-1 entries on first load.

## Tooling and validation

- **`scripts/validate_hacs.py`**: pure-Python HACS manifest pre-flight. Required fields, valid `iot_class`, version format, and the no-core-built-ins guard on `dependencies` (the HACS action rejects what hassfest accepts). Run via `make validate` or by the pre-push hook and CI's `hacs-preflight` job.
- **`Makefile`**: convenience targets (`make check`, `make lint`, `make typecheck`, `make validate`, `make test`).
- **`requirements-dev.txt`**: single source of truth for dev dependencies; used by `make setup` and both CI jobs so local and CI environments are identical.

## Key invariants

- `CategoryState` instances are created once at coordinator init and mutated in place; never replaced.
- `open_count` is authoritative from polling. `is_alerting` is authoritative from webhooks (or polling as fallback when the category was not already alerting).
- Entities never call `hass.data` directly; they hold a `self.coordinator` reference.
- Webhook URLs are generated by HA from its `base_url`; not stored in the config entry, re-generated at runtime.
