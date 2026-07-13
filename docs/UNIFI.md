# UniFi API reference

Reference for the UniFi Network controller API as used by this integration. The API is partially undocumented and community-reverse-engineered; treat all field names as potentially unstable across controller versions.

## Scope

This integration monitors **UniFi Network** alerts: events surfaced in the Network Application's System Log and SIEM feed (AP/switch/gateway events, IPS/threat detections, WAN transitions, honeypot alerts, client blocks, PoE events, etc.).

**UniFi Protect is not supported.** Protect (cameras, doorbells, motion/person detection, NVR) uses a separate API, device model, and event taxonomy. Protect events are silently ignored.

## Controller scope

**UniFi OS consoles only** as of v1.4.0. Tested on UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+. Classic self-hosted Network Application (Linux/Windows bare-metal) is not supported and the legacy `/api/...` paths and `/api/login` endpoint were removed alongside detection logic.

All requests are prefixed with `/proxy/network/`. Authentication uses `/api/auth/login` (userpass) or the `X-API-Key` header (API key). Logout uses `/api/auth/logout`.

## Authentication

### Username/password

```
POST /api/auth/login
{"username": "admin", "password": "..."}
```

Sets a session cookie; subsequent requests use the cookie automatically (aiohttp `ClientSession` handles this). Logout: `POST /api/auth/logout`.

**Important:** Do not enable 2FA/MFA on the account used for API access; it breaks non-interactive login. Use a dedicated read-only local account.

### API key

API keys are stateless: no login/logout. Generated in the UniFi OS web UI; the navigation path varies by firmware:

- **Newer firmware (Network Application 8.x+):** Settings > Admins & Users > API Keys
- **Some firmware versions:** Integrations > New API Key
- **Older firmware:** Settings > Control Plane > API Keys

The API key inherits permissions from the admin account that created it.

Pass the key as a request header on every call:

```
GET /proxy/network/api/s/default/alarm
X-API-Key: your-key-here
```

**Verification endpoint** (used during setup to confirm the key is valid):

```
GET /proxy/network/api/s/default/self
X-API-Key: your-key-here
```

> **Newer API (v2) note:** UniFi Network Application 8.x introduced a REST API under `/proxy/network/v2/api/`. `GET /proxy/network/v2/api/site` lists sites. The alarm endpoint is still at the classic `/proxy/network/api/s/{site}/alarm` (or `/list/alarm` / `/stat/alarm` depending on firmware). Note: `GET /proxy/network/v2/api/site/{site}/alarm` returns HTTP 404; the v2 alarm data lives at `POST /proxy/network/v2/api/site/{site}/system-log/all` (see "v2 system-log API" below).

### Auto-detect logic (in `UniFiClient.authenticate()`)

1. If `api_key` is present in config, try API-key auth.
2. If API-key auth fails (or no key supplied), fall back to username/password.
3. Store the detected method in `self._auth_method`.

## Alarm API endpoint

`GET /proxy/network/api/s/{site}/<path>`

> **Path variation by firmware.** UniFi has changed the alarm path multiple times. The integration probes them newest-to-oldest so modern firmware succeeds in one call:
>
> | Path | Era | Notes |
> |---|---|---|
> | `/list/alarm` | newest (UniFi Network 9.x+) | Tried first. Replaced `/stat/alarm` somewhere in the 9.x line. |
> | `/alarm` | long-standing | Universal historical path; still present on most firmware. Tried second. |
> | `/stat/alarm` | older intermediate | Some firmware exposes only this. Tried last. |
>
> A path that doesn't exist may return either 404 or `400 api.err.InvalidObject` depending on firmware; both are treated as "try the next path". A genuine 400 (e.g. wrong site name) is surfaced only after every path is exhausted.
>
> **If UniFi changes the endpoint again:** add the new path to the head of `alarm_paths` in `unifi_client.py::fetch_alarms`, update the table above, and add a fallback test in `tests/unit/unifi_client/test_legacy.py` (see `TestFetchAlarms::test_falls_back_*`).

Default site name is `default`. Multi-site is configurable via `CONF_SITE` per entry; per-category site selection is not implemented (see `docs/ROADMAP.md`, Deferred).

### Response structure

```json
{
  "meta": {"rc": "ok"},
  "data": [
    {
      "key": "EVT_GW_WANTransition",
      "msg": "WAN port (eth8) transitioned from connected to disconnected",
      "datetime": "2024-01-15T10:30:00",
      "site_id": "abc123",
      "site_name": "default",
      "device_name": "UDM-Pro",
      "archived": false,
      "subsystem": "wan"
    }
  ]
}
```

The integration filters to `archived: false` records only. The `archived` field exists in API responses but **there is no documented write API to archive/dismiss individual alarms and no UI option**. The community-discovered `POST /cmd/evtmgt {"cmd":"archive-all-alarms"}` endpoint returns `api.err.NotFound` on current firmware. In practice, controller-side `open_count` only grows.

**IPS / IDS / threat events are included in `/list/alarm` on UniFi Network 9.x and 10.x.** Confirmed by direct probing of a UCG-Ultra running Network 10.3.58: alarms with `"key":"EVT_IPS_IpsAlert"` appear in the standard alarm list with full payload (`signature`, `srcip`, `dest_port`, `inner_alert_*`, `ubnt_category`, etc.). The separate `/proxy/network/api/s/{site}/stat/ips/event` endpoint (referenced in the older unpoller Go library) returns `api.err.NotFound` on Network 10.x; do not waste time polling it. Query parameters `?archived=true|false`, `?limit=N`, `?sort=-datetime`, and `?_sort=-datetime` are all silently ignored on this firmware; filter and slice in Python after fetching.

> **Critical limitation: 3000-record cap.** `/list/alarm` returns a hard maximum of approximately 3000 records, sorted oldest-first. There is no server-side pagination or sort control. On high-volume controllers (more than ~33 IPS/threat events per day), the entire 3000-record window predates the current date and recent alarms are not present in the polled response. Field observation on a UCG-Ultra with ~120 threat events/day: `/list/alarm` covered approximately the oldest 25 days of the 90-day retention window only; alarms from the following ~65 days were absent. Today's events were confirmed present only via the v2 `system-log/all` endpoint (see below). This is why `open_count` shows 0 on busy controllers even when `alert_count` is non-zero. See `docs/research/alert-endpoints.md` for the full investigation record.

#### Error responses

The controller returns HTTP 200 even for application-level errors. The `meta.rc` field distinguishes success from failure:

```json
{
  "meta": {"rc": "error", "msg": "api.err.InvalidObject"},
  "data": []
}
```

`meta.rc` is `"ok"` on success, `"error"` on failure. `meta.msg` carries a machine-readable code (e.g. `api.err.InvalidObject` for a bad site reference).

`fetch_alarms()` checks `meta.rc` after parsing and raises `CannotConnectError` on non-`"ok"`; this propagates as `UpdateFailed` in the coordinator.

### Field reliability

| Field | Reliability | Notes |
|---|---|---|
| `key` | High | Primary classification field. Format: `EVT_{prefix}_{event}` |
| `msg` | High | Human-readable message; varies by controller version |
| `archived` | High | Always present |
| `datetime` | Medium | ISO 8601 string; may be absent on older controllers |
| `device_name` | Medium | May be `ap_name`, `sw_name`, or absent |
| `site_name` | Low | Not always present |
| `severity` | Low | Not always present; values undocumented |
| `subsystem` | Low | Broad categories like `lan`, `wan`, `wlan` |

## v2 system-log API (Network 9.x+)

> **This is the correct modern polling path for UniFi OS consoles.** The legacy
> `/list/alarm` endpoint has a hard 3000-record cap sorted oldest-first; on busy
> controllers it returns no recent alarms at all. The v2 system-log API supports
> timestamp-range filtering and real pagination. The integration must migrate to
> this path for `open_count` to be reliable on high-volume installations.

### Probe for v2 availability

`POST /proxy/network/v2/api/site/{site}/system-log/count` with body `{}`.

If the response is a JSON object (not HTTP 404), the v2 path is available.
Fall back to legacy `/list/alarm` when it is not. Older controllers and the
Classic Network Application do not have this endpoint.

### Fetch recent events

`POST /proxy/network/v2/api/site/{site}/system-log/all`

```json
{
  "timestampFrom": 1778025600000,
  "timestampTo":   1778112000000,
  "categories": ["SECURITY", "INTERNET_AND_WAN", "UNIFI_DEVICES", "POWER"],
  "pageNumber": 0,
  "pageSize": 100
}
```

- `timestampFrom` / `timestampTo`: Unix epoch **milliseconds** (not seconds,
  not ISO 8601).
- `categories`: filter by one or more enum values (see table below). Incorrect
  names cause HTTP 400; use the exact strings.
- `pageNumber`: zero-based page index.
- `pageSize`: capped at 100 per page (observed limit).

Response envelope:

```json
{
  "data": [...],
  "page_number": 0,
  "total_element_count": 74,
  "total_page_count": 8
}
```

### Category enum values

| Enum value | Description | Integrates to |
|---|---|---|
| `SECURITY` | IPS/IDS, threat detection, firewall blocks | `cat_security_threat`, `cat_security_firewall` |
| `INTERNET_AND_WAN` | WAN failover, latency | `cat_network_wan` |
| `UNIFI_DEVICES` | AP/switch/gateway offline/online | `cat_network_device` |
| `CLIENT_DEVICES` | Client connect/disconnect/roam | `cat_network_client` |
| `POWER` | PoE / power loss | `cat_power` |
| `AUDIT` | Admin-action events | (no current category) |
| `SOFTWARE_UPDATES` | Firmware updates | (no current category) |
| `VPN` | VPN tunnel events | (no current category) |

### Event record schema

Fields differ substantially from the legacy `/list/alarm` format:

| Field | Type | Notes |
|---|---|---|
| `id` | string | MongoDB ObjectId |
| `category` | string | Explicit enum value (e.g. `"SECURITY"`) |
| `event` | string | Event sub-type (e.g. `"THREAT_BLOCKED"`) |
| `key` | string | Specific event key (e.g. `"THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT"`); no `EVT_` prefix |
| `message_raw` | string | Template string with `{PARAM}` placeholders |
| `parameters` | object | Named substitution values for `message_raw` |
| `severity` | string | `"LOW"`, `"MEDIUM"`, `"HIGH"`, `"VERY_HIGH"` |
| `status` | string | `"NEW"` = open/unacknowledged (equivalent to `archived: false` in legacy) |
| `timestamp` | integer | Unix epoch **milliseconds** (not an ISO string) |
| `subcategory` | string | e.g. `"SECURITY_INTRUSION_PREVENTION"` |
| `type` | string | `"GENERAL"` or `"AUDIT"` |

The `message_raw` + `parameters` pattern requires a new payload parser.
`UniFiAlert.from_api_alarm()` cannot be reused without modification. A
dedicated `UniFiAlert.from_system_log_event()` constructor is required (tracked
under Reliability in `docs/ROADMAP.md`).

### Key format difference

Legacy `/list/alarm` uses `EVT_{system}_{event}` keys (e.g. `EVT_IPS_IpsAlert`)
mapped via `UNIFI_KEY_TO_CATEGORY`. The v2 API uses a flat descriptive format
with no common prefix (e.g. `THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT`). The
two formats cannot share a single prefix-match table; a separate v2 key map is
required.

### `/system-log/critical` note

`POST /proxy/network/v2/api/site/{site}/system-log/critical` was tested and
returned an empty `data` array on a UCG-Ultra with several thousand SECURITY
events available. Use `/system-log/all` with explicit `categories` filtering
instead.

## Webhook payloads

When UniFi Alarm Manager sends a webhook POST, the JSON body differs from the polled alarm format. It is less consistent and varies across firmware.

Known field names for the alert message:

- `message` (most common in recent Network firmware)
- `msg` (older versions)
- `text` (some versions; treated as fallback)
- `description` (rare)

`UniFiAlert.from_webhook_payload()` tries these in order. UniFi Protect webhooks are not supported.

The integration accepts POST only; GET is rejected with HTTP 405. JSON parse failures are caught, log at WARNING with class name and 80-byte body preview, and fall back to `{}`.

### Alert lifecycle

What the integration can do:

- Read open (`archived: false`) alarms via the poll API.
- Receive real-time pushes via UniFi Alarm Manager webhooks.
- Reset HA-local alert state via Clear buttons / `clear_category` / `clear_all` services. Each Clear advances a per-category acknowledgement watermark (`last_cleared_at`) so `open_count` reflects "alarms since last cleared" rather than a lifetime total.

What the integration **cannot** do (controller-side state is read-only):

- There is no documented write API to archive individual Network alarms. The community-discovered `POST /cmd/evtmgt {"cmd":"archive-all-alarms"}` returns `api.err.NotFound` on current firmware.
- There is no UI option to dismiss or archive individual alarms.
- Pressing Clear in HA resets HA-local state only (`is_alerting -> false`, `alert_count -> 0`, `last_cleared_at -> newest known alarm, or now if none seen yet`). The underlying alarms remain on the controller indefinitely. Without the watermark, `open_count` would grow to thousands without ever decreasing.

> **Design implication:** `open_count` without a watermark is a meaningless lifetime counter. The integration persists `last_cleared_at` per category via `homeassistant.helpers.storage.Store`. Polling counts only alarms newer than that timestamp.
>
> **Clock assumption:** `last_cleared_at` is anchored to the controller's own clock, not the HA host clock. On Clear, the watermark is set to the newest `received_at` among alarms already known for that category (poll or webhook), falling back to `datetime.now(UTC)` only when no alarm has ever been seen. This keeps the `open_count` comparison controller-clock vs controller-clock, so it is unaffected by clock skew between HA and the controller. The webhook path is the one exception: a webhook's `received_at` is stamped by HA at receipt time (there is no controller timestamp in the Alarm Manager payload), so a webhook-only alert's watermark contribution is still HA-clock-based by necessity.

### Event entities and webhooks

**HA Event entities fire only via webhooks, not via polling.** This is by design:

- **Webhook path:** `push_alert()` increments `alert_count`; the event entity detects the change in `_handle_coordinator_update` and fires `alert_received`.
- **Polling path:** `open_count` and `is_alerting` update, but `alert_count` is **not** incremented; no Event entity fires.

If webhooks are not configured in UniFi Alarm Manager, Event entities never fire, even though binary sensors and sensors update normally via polling.

**Troubleshooting if events don't fire:**

1. Confirm webhooks are configured in UniFi Network > System > Alarm Manager > Integrations, pointing at the URLs shown during HA setup.
2. Enable DEBUG logging for `custom_components.unifi_alerts` and look for `"Alert pushed to category"`; if absent, the webhook is not reaching the integration.
3. Check HA logs for HTTP 401 responses; this indicates a webhook token mismatch.
4. Verify the category configured in UniFi matches a category enabled in the HA integration options.

## Severity normalization

Every alert, regardless of which ingestion path produced it (webhook push, legacy `/list/alarm` polling, or v2 `system-log` polling), is assigned a normalized `severity_level` in addition to its original raw `severity` string. `custom_components/unifi_alerts/severity.py` is the source of truth; this section documents its behavior.

### Ordering

Exactly four Severity_Levels exist, ordered:

```
LOW < MEDIUM < HIGH < VERY_HIGH
```

`normalize_severity()` always returns one of these four values - never empty, never an unrecognised string.

### The `No_Filter` sentinel

`No_Filter` (displayed to users as "No Filter") is a Minimum_Severity_Setting value, not a Severity_Level. It is used only for the per-category minimum-severity gate and is never assigned as an alert's own normalized severity. For the purposes of the Minimum_Severity_Setting selector's ordering only, `No_Filter` sits below `LOW`:

```
No_Filter < LOW < MEDIUM < HIGH < VERY_HIGH
```

A category set to `No_Filter` accepts every alert regardless of severity, with no comparison performed.

### Legacy severity synonym table

Legacy alarm severities are inconsistent free-form strings. `normalize_severity()` matches case-insensitively and ignores leading/trailing whitespace, first against the four canonical names above, then against this synonym table:

| Raw value | Normalized Severity_Level |
|---|---|
| `critical` | `VERY_HIGH` |
| `urgent` | `VERY_HIGH` |
| `error` | `HIGH` |
| `warning` | `MEDIUM` |
| `info` | `LOW` |
| `notice` | `LOW` |

When a user reports a legacy severity string that isn't classified correctly, add it to `_SEVERITY_SYNONYMS` in `severity.py` and update the table above.

### Fallback

If the raw severity string is empty, or matches neither a canonical name nor a synonym after case-folding and trimming, `normalize_severity()` falls back to `LOW`.

## Event key taxonomy

Keys follow the pattern `EVT_{system}_{event}`:

| Prefix | System |
|---|---|
| `EVT_AP_` | Access points |
| `EVT_SW_` | Switches |
| `EVT_GW_` | Gateways / UDM |
| `EVT_WU_` | Wireless users (clients) |
| `EVT_WG_` | Wireless guests |
| `EVT_LU_` | Wired (LAN) users |
| `EVT_IPS_` | IPS/IDS system |
| `EVT_IDS_` | IDS (older prefix) |

The full mapping from key to category is in `UNIFI_KEY_TO_CATEGORY` in `const.py`. The list is **incomplete** and community-sourced; expand as users report unclassified keys.

## Expanding the key map

When a user reports an alert that isn't being categorised (look for the DEBUG log from `unifi_client.py`), add the key to `UNIFI_KEY_TO_CATEGORY` in `const.py`. If the key belongs to a new category type not yet in `ALL_CATEGORIES`, that's a larger change; track it as a GitHub Issue.

Guidelines:

- Use the shortest prefix that uniquely identifies the event family (e.g. `EVT_GW_Honeypot` not `EVT_GW_HoneypotDetected` if there are multiple honeypot variants).
- Add a comment with the category group.
- Add a corresponding test case in `tests/unit/unifi_client/test_legacy.py::TestClassify`.

## Known API inconsistencies

- **SSL certificates**: UniFi OS consoles ship with self-signed certificates by default. `verify_ssl` defaults to `True` (secure). Users with self-signed certs must disable verification via the config flow.
- **Site names**: some controllers use `default`; others use the site ID (a hex string). `CONF_SITE` per entry covers this. Per-category site selection is not implemented.
- **Timestamp format**: the `datetime` field in legacy alarm records is usually ISO 8601 but some controllers emit epoch milliseconds. `UniFiAlert.from_api_alarm()` falls back to `datetime.now(UTC)` when neither parses. The v2 `system-log` API always uses epoch milliseconds in the `timestamp` field.
- **`/list/alarm` 3000-record cap**: the legacy alarm endpoint returns at most ~3000 records sorted oldest-first. No query parameter overrides this. On controllers generating more than ~33 alarms per day, recent events are not present in the polled response and `open_count` will always read 0 via the legacy path. The v2 `system-log/all` endpoint (see above) is the correct fix; it supports timestamp-range filtering and pagination. Field-confirmed on Network 10.3.58. Full investigation in `docs/research/alert-endpoints.md`.
