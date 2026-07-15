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
    |--- HTTP GET/POST --> UniFiClient --> coordinator._async_update_data()
         (polling; GET=legacy, POST=v2) --> coordinator._fetch_categorised()
                                                  |
                              probe_system_log_endpoint() (once per client,
                              cached with backoff on repeated failure)
                                       /                        \
                              v2 available                v2 unavailable / older firmware
                                       |                          |
                    fetch_system_log_alarms()          categorise_alarms()
                    (timestampFrom watermark,           (legacy /list/alarm,
                     pagination, status="NEW")           /alarm, /stat/alarm
                                       |                  probe chain)
                                       v                          |
                        UniFiAlert.from_system_log_event()       /
                                        \                       /
                                         v                     v
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

The v2 system-log path (Network 9.x+) is the primary polling path on current firmware; it supports `timestampFrom`-based filtering and real pagination, avoiding the legacy endpoint's ~3000-record cap. `_fetch_categorised()` probes for it once per client instance and falls back to the legacy `/list/alarm` probe chain (`categorise_alarms()`) on 404, on a run of transient probe failures, or on older controllers. See `docs/UNIFI.md` for the full endpoint reference.

## Module responsibilities

### `models.py`

Pure data; no HA dependencies. Three dataclasses:

- **`UniFiAlert`**: immutable snapshot of a single alert event. Built from either a webhook payload (`from_webhook_payload`) or a polled alarm record (`from_api_alarm`). Both constructors normalise field names across the inconsistent UniFi API surface.
- **`CategoryState`**: mutable runtime state for one category. Owned exclusively by the coordinator. Tracks `enabled`, `is_alerting`, `last_alert`, `alert_count` (webhook-incremented), `open_count` (poll-set), `last_cleared_at`, and `last_webhook_at`. The `last_cleared_at` field doubles as the **acknowledgement watermark**: `open_count` only counts polled alarms newer than this timestamp, so pressing Clear bounds the counter to "since last acknowledged" rather than a lifetime total. `last_webhook_at` is set only on the push path (never by polling) and feeds `webhook_health()`, which classifies delivery as `never_received` / `healthy` / `stale` (stale after `WEBHOOK_STALE_AFTER_SECONDS`, 7 days) - the basis for the per-category webhook health sensor.
- **`RuntimeData`**: container stored on `entry.runtime_data`. Holds the coordinator, generated webhook URLs, the unregister callable, and the `UniFiClient` instance.

### `const.py`

Single source of truth for:

- Category identifiers (`CATEGORY_*` string constants), `ALL_CATEGORIES` ordered list (defines display order), `CATEGORY_ICONS`, `CATEGORY_ICONS_OK` UI metadata. Entity display labels live in `strings.json` / `translations/en.json` under per-category translation keys, not in `const.py`.
- `UNIFI_KEY_TO_CATEGORY`: maps UniFi event-key prefixes to category identifiers. Community-sourced and deliberately incomplete; unrecognised keys are logged at DEBUG and skipped.
- Config entry key names (`CONF_*`).
- `webhook_id_for_category(category, suffix="")`: deterministic webhook ID generator. With a per-entry suffix it returns `unifi_alerts_{suffix}_{category}`; without one (legacy single-entry installs) it returns `unifi_alerts_{category}`.

### `unifi_client.py`

Stateful async HTTP client. Always uses the UniFi OS API surface:

- `/proxy/network/api/...` for the alarm endpoint.
- API-key auth verifies against `/proxy/network/api/s/default/self` and is sent as an `X-API-Key` header on every request.

API-key authentication is the only supported method (username/password auth was removed, epic #277; see `docs/UNIFI.md` for the historical note and CSRF rationale). API keys are stateless: no session, cookie, or login/logout to manage, so the client holds no auth state. On `InvalidAuthError` during a poll, the coordinator re-authenticates once (re-verifies the key) and retries.

`fetch_alarms()` uses a per-site cached endpoint URL once one has been discovered. On the first call for a site (or again later if the cached URL stops resolving, e.g. after a firmware upgrade) it delegates to `_discover_alarm_url()`, which walks the legacy alarm-endpoint probe chain `[/list/alarm, /alarm, /stat/alarm]` (newest UniFi Network firmware first); 404 / 400 falls through to the next path, only surfacing an error after every path is exhausted. Endpoint discovery (the fallback iteration and `api.err.InvalidObject` detection) is kept separate from the core fetch/parse loop in `_try_fetch_alarms()`, so steady-state polling issues a single request with no fallback parsing (#239). `categorise_alarms()` calls `fetch_alarms()` and groups the results by category via `_classify()`.

`probe_system_log_endpoint()` checks whether the v2 `/v2/api/site/{site}/system-log/count` endpoint is available (200 = yes, 404 = no, cached until re-auth; a run of transient failures triggers a timed backoff before re-probing). `fetch_system_log_alarms()` pages through `/v2/api/site/{site}/system-log/all` using a `timestampFrom` watermark, filtering to `status == "NEW"` events, up to `MAX_SYSTEM_LOG_PAGES`.

`_classify()` is a static method (pure function, easily testable) mapping raw legacy alarm dicts to categories. `UniFiAlert.from_system_log_event()` is the equivalent parser for the v2 event schema (`message_raw` + `parameters` templating, no `EVT_` prefix on keys).

### `coordinator.py`

The integration's single source of truth at runtime. Key design decisions:

- **`_category_states` is long-lived**: not re-created on each poll. Polling updates `open_count` and may set `is_alerting` directly (without incrementing `alert_count`) if the category is not already alerting. Webhook pushes update `is_alerting` and `alert_count` immediately via `apply_alert()`.
- **Polling path dispatch**: `_fetch_categorised()` probes for the v2 system-log endpoint once per client instance and prefers it when available, computing a `timestampFrom` watermark as the oldest `last_cleared_at` across enabled categories (clamped to `DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS` so an uncleared category cannot grow the fetch window without bound). Falls back to the legacy `categorise_alarms()` path when the probe returns unavailable or fails. Both paths feed `unrecognised_keys` (exposed via diagnostics) for keys that cannot be mapped to a category.
- **Auto-clear**: each `push_alert()` cancels any existing `asyncio.Task` for that category and schedules a new one via `hass.async_create_background_task` (or `async_create_task` / `asyncio.ensure_future` as fallbacks). Repeated alerts reset the timer rather than stacking. Background task failures are logged via a done-callback instead of being silently swallowed.
- **`async_set_updated_data()`** is called on webhook push to bypass the polling interval and notify entities immediately.
- **Polling does not clear `is_alerting`**: only the auto-clear timeout or a button press does. Prevents a polling race where a momentarily empty alarm list falsely clears an active alert.
- **Acknowledgement watermarks**: `last_cleared_at` on each `CategoryState` is the per-category watermark. Polling counts only alarms newer than the watermark (`open_count` = "alarms since last Clear"). `push_alert()` also optimistically increments `open_count` for alerts newer than the watermark so the count sensor doesn't lag a full poll interval; the next poll reconciles it to the authoritative value. Watermarks (plus `alert_count`, `last_alert`, and `last_webhook_at`) persist via `homeassistant.helpers.storage.Store` (keyed per entry) so they survive HA restarts - bursts of webhook pushes are debounced through `Store.async_delay_save`, while clears persist immediately and raise a `watermark_persist_failed` repair issue on write failure. `async_clear_category()` and `async_clear_all()` are the sole entry points for clearing: cancel auto-clear tasks, call `state.clear()` (advances the watermark), persist, notify. Buttons and services delegate to these methods.
- **Webhook debounce**: `push_alert()` keeps `_last_push_at` per `(category, alert.key)` and drops repeats inside `WEBHOOK_DEDUP_WINDOW_SECONDS = 5.0` (keyless alerts, e.g. the empty-body ping, are never deduplicated against each other). Stale entries are pruned opportunistically so the dict is bounded by "distinct (category, key) pairs within the window", not the controller's lifetime vocabulary.

### `webhook_handler.py`

Registers one HA webhook per enabled category using `homeassistant.components.webhook`. Webhooks are:

- Scoped to `local_only=True` (LAN only).
- Accepted on POST only; GET requests are rejected with HTTP 405. UniFi Alarm Manager must be configured to send POST.
- Fail-closed if no secret is configured: HTTP 500 with an error log pointing the user at Configure to re-save the entry. Never skips the token check.
- Bearer-token authenticated: `?token=` query parameter compared against `CONF_WEBHOOK_SECRET` via `hmac.compare_digest`; missing or wrong token returns HTTP 401.
- Body-capped at `WEBHOOK_MAX_BODY_BYTES`; oversized bodies return HTTP 413.
- Parsed as JSON; a body that fails JSON or UTF-8 decoding is rejected with HTTP 400 (logged at WARNING with class name and 80-byte body preview) rather than falling back to `{}`. An empty body (`{}`) or a body with no recognised fields is accepted and yields `UniFiAlert.from_webhook_payload()`'s "Unknown alert" fallback - only genuine parse failures return 400.
- DEBUG-payload narrowed to `{category, alert_key, severity, device_name, key}` to avoid surfacing future-firmware fields.
- The first valid webhook received after a secret rotation clears the `webhook_secret_rotated` repair issue, confirming Alarm Manager was updated with the new token.

The webhook ID format is `unifi_alerts_{suffix}_{category}` when a per-entry `CONF_WEBHOOK_ID_SUFFIX` is present (always set on new entries from v1.4.0 onwards), or `unifi_alerts_{category}` for legacy single-entry installs. IDs are deterministic so they survive HA restarts without re-registration. Multi-entry isolation is the suffix's whole purpose.

### `config_flow.py`

Three-step setup flow:

1. **`async_step_user`**: URL + credentials (with SSDP discovery pre-filling the URL via `async_step_ssdp`). Calls `UniFiClient.authenticate()` for validation. Generates `CONF_WEBHOOK_SECRET` (`secrets.token_urlsafe(32)`) and `CONF_WEBHOOK_ID_SUFFIX` (`secrets.token_hex(4)`) on success.
2. **`async_step_categories`**: per-category boolean toggles plus `poll_interval`, `clear_timeout`, and `site`.
3. **`async_step_finish`**: displays generated webhook URLs (with bearer token) for the user to copy into UniFi Alarm Manager.

`UniFiAlertsOptionsFlow` mirrors all three steps, allowing credentials, categories, and timing to be reconfigured in place. The credentials step also offers a "Regenerate webhook secret" checkbox. Option changes trigger an entry reload via `_async_update_listener`.

`async_step_reauth` / `async_step_reauth_confirm` implement HA's reauth convention; an `issue_registry` repair card surfaces in Settings > Repairs on auth failure.

### Platform files (`binary_sensor.py`, `sensor.py`, `event.py`, `button.py`)

All entity classes extend `CoordinatorEntity[UniFiAlertsCoordinator]` and override `_handle_coordinator_update()` to call `self.async_write_ha_state()`. They read exclusively from `self.coordinator.get_category_state(category)`; no local caching.

**Event entities** (`event.py`) detect new alerts by comparing `state.alert_count` to `self._last_seen_count` in `_handle_coordinator_update`. Event entities fire on change, not on state. Polling does not increment `alert_count`, so events fire only on real webhook pushes.

**Device grouping**: all entities share the same `_device_info` dict (`identifiers={(DOMAIN, entry.entry_id)}`); HA groups them under a single "UniFi Alerts" device with `entry_type=DeviceEntryType.SERVICE` and `configuration_url` pointing at the controller.

## Config entry data structure

After setup, `entry.data` contains:

```python
{
    "controller_url": "https://192.168.1.1",
    "api_key": "...",                       # required; the only supported credential
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

`ConfigFlow.VERSION = 4`. `async_migrate_entry` runs migrations sequentially in `__init__.py`:

- **v1 -> v2**: strips the legacy `is_unifi_os` key.
- **v2 -> v3**: backfills `webhook_secret` and/or `webhook_id_suffix` on entries that predate v1.4.0 and were never reconfigured via the options flow. If `webhook_id_suffix` was backfilled (changing every webhook URL for that entry), raises a `webhook_urls_changed` repair issue prompting the user to re-paste URLs into Alarm Manager.
- **v3 -> v4**: drops the legacy `username`, `password`, and `auth_method` keys (epic #277). Entries that already carry an API key migrate silently. Entries with only username/password lose their credentials here, so `async_setup_entry` raises `ConfigEntryAuthFailed` and Home Assistant launches the reauth flow, which asks for a single API key and raises an explanatory repair issue. `entry_id`, `unique_id`, the webhook secret, and the webhook id suffix are untouched, so entities, history, and Alarm Manager webhook URLs survive the migration.

## Tooling and validation

- **`scripts/validate_hacs.py`**: pure-Python HACS manifest pre-flight. Required fields, valid `iot_class`, version format, and the no-core-built-ins guard on `dependencies` (the HACS action rejects what hassfest accepts). Run via `make validate` or by the pre-push hook and CI's `hacs-preflight` job.
- **`scripts/validate_docs.py`**: pure-Python docs prose linter (bans em-dash, unicode arrows, "bundle/cluster/track/session N" framing; enforces `docs/HISTORY.md` heading format). Run via `make validate`, `make doc-check`, the pre-push hook, and CI.
- **`scripts/check_translations.py`**: byte-identical check between `strings.json` and `translations/en.json`, cross-platform. Run via `make doc-check` and the CI lint job.
- **`scripts/bump_version.py`**: release-prep helper for the pre-release / stable / next-cycle version bumps described in `docs/RELEASING.md`.
- **`Makefile`**: convenience targets (`make check`, `make lint`, `make typecheck`, `make validate`, `make doc-check`, `make test`).
- **`requirements-dev.txt`**: single source of truth for dev dependencies; used by `make setup` and both CI jobs so local and CI environments are identical.

## Key invariants

- `CategoryState` instances are created once at coordinator init and mutated in place; never replaced.
- `open_count` is authoritative from polling. `is_alerting` is authoritative from webhooks (or polling as fallback when the category was not already alerting).
- Entities never call `hass.data` directly; they hold a `self.coordinator` reference.
- Webhook URLs are generated by HA from its `base_url`; not stored in the config entry, re-generated at runtime.
