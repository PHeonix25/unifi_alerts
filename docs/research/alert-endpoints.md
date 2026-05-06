# Research: UniFi alert endpoint investigation

Field research conducted 2026-05-06 against a UCG-Ultra running UniFi Network
10.3.58 (firmware v5.0.16, device type UDRULT, `data_retention_days: 90`).

## Why this was investigated

Production field testing showed `open_count` always reading 0 despite confirmed
IPS/threat webhook deliveries (`alert_count=14`, `open_count=0`). This document
records every endpoint probed, what it returned, and the conclusions drawn.

## Hypothesis log

Hypotheses are recorded in chronological order so we do not re-investigate
dead ends.

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| 1 | UniFi auto-archives IPS alarms faster than the poll interval | Disproven | No write API to archive alarms exists on Network 9.x+. |
| 2 | IPS events live at `/stat/ips/event`, not `/list/alarm` | Disproven | `/stat/ips/event` returns `api.err.NotFound`; `/list/alarm` contains `EVT_IPS_IpsAlert` with full payload. |
| 3 | Today's alarms appear in `/list/alarm` but are below the watermark | Disproven | Field-confirmed: today's alarms do NOT appear in `/list/alarm` at all (3000-record cap). |
| 4 | `/list/alarm` has a 3000-record cap sorted oldest-first | Confirmed | Both `/list/alarm` and `/rest/alarm` return the same 3000 records covering only the oldest end of the retention window; today's events are absent. Confirmed present via `/system-log/all`. |

## Endpoints probed

### Legacy alarm paths

All reachable via `GET /proxy/network/api/s/{site}/<path>`.

| Path | Result |
|---|---|
| `/list/alarm` | Returns up to 3000 records, oldest-first. Active on Network 10.x. |
| `/alarm` | Returns same 3000-record set as `/list/alarm`. |
| `/stat/alarm` | Returns same 3000-record set. |
| `/rest/alarm` | Returns same 3000 records, same date range as `/list/alarm`. |
| `/stat/event` | `api.err.NotFound` on Network 10.x. |
| `/stat/ips/event` | `api.err.NotFound`. Referenced in older community libraries; does not exist on Network 10.x. |

### Query parameters tested on `/list/alarm`

All of the following are silently ignored; the full 3000-record list is
returned regardless:

- `?limit=N`
- `?_limit=N`
- `?archived=true` / `?archived=false`
- `?sort=-datetime`
- `?_sort=-datetime`

### v2 API paths

| Path | Method | Result |
|---|---|---|
| `/proxy/network/v2/api/site/{site}/alarm` | GET | HTTP 404. Does not exist. |
| `/proxy/network/v2/api/site/{site}/system-log/count` | POST | Returns category and event counts. Confirmed working. |
| `/proxy/network/v2/api/site/{site}/system-log/all` | POST | Returns paginated events with timestamp filtering. Confirmed working. |
| `/proxy/network/v2/api/site/{site}/system-log/critical` | POST | Returns `[]`. No events classified as "critical" on this controller. |

## The 3000-record cap

`/list/alarm` returns a fixed maximum of approximately 3000 records, sorted
oldest-first. On a high-volume controller (this one generates ~120 IPS/threat
alerts per day), 3000 records covers only ~25 days. Alarms newer than position
3000 in the sorted list are not returned; there is no pagination and no
server-side sort control.

Field observation:

- `data_retention_days: 90` per `/proxy/network/api/s/{site}/stat/sysinfo`
- `/list/alarm` covered approximately the oldest 25 days of the retention
  window (oldest = 90 days ago; newest = position 3000)
- Alarms from the following ~65 days were not in the polled response
- Today's IPS events confirmed absent from `/list/alarm` and confirmed present
  in `/system-log/all` with matching source IPs

**Consequence for `open_count`:** on any controller where IPS/threat event
volume exceeds ~33 alerts/day, the entire 3000-record window predates the
current date. `open_count` via the legacy polling path will always be 0 because
no polled alarm is newer than the `last_cleared_at` watermark set at Clear time.

## v2 system-log API

The modern event-query API for UniFi OS consoles on Network 9.x+.

### Capabilities probe: `/system-log/count`

`POST /proxy/network/v2/api/site/{site}/system-log/count` with body `{}`.

Returns a breakdown of event counts by category, event type, and general/audit
type. Example (counts from field installation):

```json
{
  "categories": [
    {"count": 87,    "name": "AUDIT"},
    {"count": 4,     "name": "SOFTWARE_UPDATES"},
    {"count": 142,   "name": "INTERNET_AND_WAN"},
    {"count": 5234,  "name": "SECURITY"},
    {"count": 9412,  "name": "CLIENT_DEVICES"},
    {"count": 31,    "name": "UNIFI_DEVICES"}
  ],
  "events": [
    {"count": 5234,  "name": "THREAT_BLOCKED"},
    {"count": 4108,  "name": "CLIENT_CONNECTED_WIRELESS"},
    ...
  ],
  "type": [
    {"count": 87,    "name": "AUDIT"},
    {"count": 15001, "name": "GENERAL"}
  ]
}
```

Use this as the v2 availability probe: if the response is a JSON object (not
HTTP 404 or `api.err.NotFound`), the v2 path is available on this controller.

### Fetch with timestamp filter: `/system-log/all`

`POST /proxy/network/v2/api/site/{site}/system-log/all`

Request body:

```json
{
  "timestampFrom": 1778025600000,
  "timestampTo":   1778112000000,
  "categories": ["SECURITY"],
  "pageNumber": 0,
  "pageSize": 100
}
```

- `timestampFrom` / `timestampTo`: Unix epoch **milliseconds** (not seconds,
  not ISO 8601).
- `categories`: subset of the enum values listed below. Incorrect names cause
  HTTP 400.
- `pageNumber`: zero-based page index.
- `pageSize`: observed cap of 100 per page.

Response envelope:

```json
{
  "data": [...],
  "page_number": 0,
  "total_element_count": 92,
  "total_page_count": 10
}
```

### Example event record (SECURITY / THREAT_BLOCKED)

```json
{
  "category": "SECURITY",
  "event": "THREAT_BLOCKED",
  "id": "60a1b2c3d4e5f60718293a4b",
  "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
  "message_raw": "A network intrusion attempt from {SRC_IP} to {DST_CLIENT} has been detected and blocked.",
  "parameters": {
    "SRC_IP":    {"id": "198.51.100.1", "name": "198.51.100.1", "not_actionable": true},
    "DST_CLIENT": {"id": "bc:24:11:aa:bb:cc", "name": "<internal device>"},
    "DEVICE": {
      "id": "9c:05:d6:11:22:33", "ip": "192.168.X.X",
      "model": "UCG-Ultra", "name": "UCG-Ultra", "version": "5.0.16"
    }
  },
  "severity": "HIGH",
  "show_on_dashboard": false,
  "status": "NEW",
  "subcategory": "SECURITY_INTRUSION_PREVENTION",
  "target": "DEVICE",
  "timestamp": 1778025612345,
  "title_raw": "Threat Detected and Blocked",
  "type": "THREAT_DETECTION_AND_PREVENTION"
}
```

### Key schema differences vs legacy `/list/alarm`

| Aspect | Legacy `/list/alarm` | v2 `/system-log/all` |
|---|---|---|
| Key format | `EVT_IPS_IpsAlert` | `THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT` |
| Message | Pre-formatted string (`msg` field) | Template in `message_raw` + `parameters` dict |
| Timestamp field | `datetime` (ISO 8601 string) | `timestamp` (epoch milliseconds integer) |
| Open/closed state | `archived: false` | `status: "NEW"` |
| Category | Derived from key prefix via `UNIFI_KEY_TO_CATEGORY` | Explicit `category` field |
| Pagination | None (hard cap ~3000, oldest-first) | `pageNumber` / `pageSize` / `total_page_count` |
| IPS events | `EVT_IPS_IpsAlert` with raw network fields | `THREAT_BLOCKED` with structured `parameters` |

### Category enum values (confirmed on Network 10.3.58)

| Enum value | Description |
|---|---|
| `AUDIT` | Admin-action events |
| `SOFTWARE_UPDATES` | Firmware update events |
| `INTERNET_AND_WAN` | WAN/internet transitions |
| `SECURITY` | IPS/IDS, threat detection, firewall |
| `CLIENT_DEVICES` | Client connect/disconnect/roam |
| `UNIFI_DEVICES` | AP/switch/gateway device events |
| `POWER` | PoE / power events (from published API schema; not confirmed in count response above) |
| `VPN` | VPN tunnel events (from published API schema; not confirmed in count response above) |

## aiounifi

The official HA UniFi integration library (`Kane610/aiounifi`) has no alarm
model. It delivers events via WebSocket (`/proxy/network/wss/s/{site}/events`)
and does not poll `/list/alarm` at all. There is no upstream reference
implementation for alarm polling parameters.

## Conclusions

1. **`/list/alarm` is unfixable for busy controllers.** No query parameters
   control sorting or record count. The 3000-record oldest-first cap means
   recent alarms are invisible on high-volume installations (observed: well
   over 100 IPS/threat events per day on the field installation).

2. **The v2 `system-log/all` path is the correct modern endpoint** for
   time-bounded, paginated alarm queries on UniFi OS consoles running Network
   9.x+.

3. **Two-phase fix for `open_count`:**
   - Phase 1 (v1.5.0): optimistic increment in `push_alert()` fixes real-time
     accuracy for webhook-delivered alarms without requiring an API change.
   - Phase 2 (v1.6.0): switch polling to `POST /system-log/all` with
     `timestampFrom = last_cleared_at or (now - 24h)`. Requires a new key
     mapping (`THREAT_BLOCKED_*` -> category) and a new payload parser
     (`UniFiAlert.from_system_log_event()`). Auto-detect required: probe
     `/system-log/count` first; fall back to legacy `/list/alarm` for older
     controllers and Classic Network Application.

4. **Schema differences are substantial.** The v2 event key format
   (`THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT`) shares no prefix convention with
   the legacy format (`EVT_IPS_IpsAlert`). A separate key-to-category map and
   a separate `from_system_log_event()` constructor on `UniFiAlert` are
   required; do not try to extend the existing `UNIFI_KEY_TO_CATEGORY` prefix
   table to cover both formats.
