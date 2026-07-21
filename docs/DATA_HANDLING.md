# Data handling and retention

This page is the authoritative statement of what this integration stores, where, and for how long. It is written for self-hosters auditing their Home Assistant install and for HACS default-catalogue reviewers.

> **No data leaves your HA host.** This integration only talks to your local UniFi controller: the controller pushes alerts to HA via webhook, and HA polls the controller's REST API for open-alarm counts. There is no cloud relay, no third-party telemetry, and no external service of any kind in either direction.

## What's persisted to disk

Each config entry (one per UniFi controller/site) gets its own `Store` file at:

```
.storage/unifi_alerts_watermarks_<entry_id>
```

`<entry_id>` is the config entry's internal HA identifier, not anything UniFi-supplied. The file is created and written by `coordinator.py` (`_build_persist_data()`) via `homeassistant.helpers.storage.Store`.

Per enabled alert category, the following fields are written:

| Field | Type | Meaning |
|---|---|---|
| `last_cleared_at` | ISO timestamp | Watermark: when the category was last cleared (manually or by auto-clear) |
| `alert_count` | int | Running count of alerts applied to this category |
| `last_alert` | object or `null` | The most recent alert for this category, see field list below |
| `last_webhook_at` | ISO timestamp | When the last webhook was received for this category (powers the webhook-health signal) |

`last_alert`, when present, is a `UniFiAlert` serialised via `UniFiAlert.to_dict()` (`models.py`). Only these scalar fields are written:

- `category`
- `message` (truncated to 255 characters)
- `received_at` (ISO timestamp)
- `key` (the UniFi event key, e.g. `EVT_WU_Disconnected`)
- `device_name` (truncated to 255 characters)
- `site`
- `severity`

**The raw controller payload is never persisted.** `UniFiAlert.raw` (the full webhook body or poll-API alarm object, which can carry client MACs, IPs, and hostnames) is deliberately excluded from `to_dict()`. This was a deliberate decision (tracked historically as decision #115) and the exclusion is documented inline in `models.py` next to `to_dict()`.

Credentials (`CONF_API_KEY`) and the webhook bearer secret (`CONF_WEBHOOK_SECRET`) live in HA's own config entry storage (`.storage/core.config_entries`), governed by HA core, not by this integration's watermark file. (Username/password authentication was removed; `CONF_USERNAME`/`CONF_PASSWORD` no longer exist.)

### Deletion

Removing the config entry (Settings > Devices & Services > UniFi Alerts > three-dot menu > Delete) deletes the watermark file entirely. `async_remove_entry` in `__init__.py` calls `Store.async_remove()` on the same `unifi_alerts_watermarks_<entry_id>` path, so nothing about that controller/site is left behind.

## What's memory-only (lost on restart)

These are never written to disk and reset to their defaults on every Home Assistant restart:

- **`open_count` per category** - recomputed from a live controller poll every update cycle (`coordinator.py`). Not persisted because it is only ever a snapshot of current controller state, not a fact about the past.
- **Webhook dedup window state (`_last_push_at`)** - per category+alert-key monotonic timestamps used to drop duplicate pushes from a noisy controller within a short window. Bounded in size, held only in the coordinator instance.
- **`unrecognised_keys`** - a diagnostic counter of UniFi v2 system-log event keys seen during polling that don't map to a known category. Used to help users report gaps in the category mapping; not meaningful across restarts.

## What's in a diagnostics download

Settings > Devices & Services > UniFi Alerts > Download diagnostics produces a JSON file built by `diagnostics.py` (`async_get_config_entry_diagnostics`).

**Redacted before inclusion:** `CONF_API_KEY`, `CONF_WEBHOOK_SECRET` (the `_TO_REDACT` set), applied via `homeassistant.components.diagnostics.async_redact_data` to both `entry.data` and `entry.options`.

**Included:** webhook URLs are included (so a shared diagnostics file still shows what was configured). They no longer embed the bearer secret (breaking change, issue #176), so no stripping is required before inclusion.

**Included, coordinator state only:** per-category `enabled`, `is_alerting`, `open_count`, `alert_count`, `last_cleared_at`, `last_webhook_at`, `webhook_health()`, plus the rollup counters (`any_alerting`, `rollup_alert_count`, `rollup_open_count`) and the `unrecognised_keys` counts.

**Deliberately excluded:** per-category alert content, meaning `message`, `device_name`, and any raw alert body. These fields can carry controller-supplied hostnames, MAC addresses, or IP addresses, which should not appear verbatim in a file a user might paste into a public support thread or bug report. This exclusion is documented inline in `diagnostics.py` next to `coordinator_info`; if alert detail is ever added to diagnostics in the future, it must be routed through `async_redact_data` with an explicit field list rather than included directly.

## What's logged at DEBUG

When the `custom_components.unifi_alerts` logger is set to `DEBUG`, webhook receipt logs a narrowed view of the inbound payload, not the payload itself. `webhook_handler.py` defines `_SAFE_DEBUG_FIELDS`:

- `category`
- `alert_key`
- `key`
- `severity`
- `device_name`

Only these fields (when present in the payload) are logged, one line per webhook received. Any other field the controller sends, including the raw payload structure, firmware-specific additions, or free-text fields not in this list, is never written to the log.

The webhook bearer secret is never logged. Webhook URLs registered by the integration no longer embed it (issue #176), so URLs that appear anywhere in logs or diagnostics never carry the secret. Any `?token=...` a user pastes into their own Alarm Manager configuration is theirs to redact from screenshots or shared logs; this integration never echoes it back.

## Retention policy

There is no time-based retention window. Data for a category persists until one of:

1. **The category is cleared** - pressing Clear (or auto-clear firing) marks the category as acknowledged (`is_alerting = False`) and advances the watermark (`last_cleared_at`). It does NOT delete `last_alert` - the most recent alert's details remain visible in entity attributes. This is intentional: dashboards and automations can still reference the last-seen event after it has been acknowledged.
2. **The config entry is removed** - the watermark `Store` file is deleted outright (see Deletion above).
3. **Home Assistant itself is reset or uninstalled** - nothing in this integration outlives the HA install; there is no separate database, external store, or backup mechanism of its own.

## Summary for reviewers

- All storage is local to the HA host filesystem (`.storage/`), scoped per config entry, and removable in one action.
- No raw controller payloads are ever written to disk.
- No alert content (message, device name) appears in diagnostics downloads.
- No data is transmitted to any destination other than the user's own UniFi controller and the user's own Home Assistant instance.
