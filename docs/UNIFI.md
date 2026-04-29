# UNIFI.md

Reference for the UniFi Network controller API as used by this integration. The API is partially undocumented and community-reverse-engineered — treat all field names as potentially unstable across controller versions.

## Scope

This integration monitors **UniFi Network** alerts — events surfaced in the Network Application's System Log and SIEM feed (AP/switch/gateway events, IPS/threat detections, WAN transitions, honeypot alerts, client blocks, PoE events, etc.).

**UniFi Protect is not supported.** Protect (cameras, doorbells, motion/person detection, NVR) uses a completely separate API, device model, and event key taxonomy. Protect events will not be classified by this integration and will be silently ignored. A separate integration would be required for Protect monitoring.

## Controller types

The integration must handle two distinct controller environments:

| Type | Detection | API base path | Auth |
|---|---|---|---|
| **Self-hosted** (Linux/Windows software) | No `x-csrf-token` header on `/` | `/api/...` | Session cookie (user/pass only) |
| **UniFi OS** (UDM, UDM Pro, UDM SE, UCG, UCG-Ultra, Cloud Key Gen2+) | `x-csrf-token` header present | `/proxy/network/api/...` | Session cookie **or** API key |

Detection happens in `UniFiClient._detect_unifi_os()` by making a GET to `/` and checking response headers.

### Detection caveats and known failure modes

The `x-csrf-token` heuristic is fragile. It fails in several common real-world configurations:

- **Reverse proxy / custom domain**: Nginx, Caddy, Traefik, and similar proxies often strip or do not forward the `x-csrf-token` response header. A user accessing their controller at `https://unifi.example.com` via a reverse proxy will have detection return `False` even if the underlying hardware is a UDM or UCG.
- **UCG-Ultra firmware**: Some UCG-Ultra firmware versions do not set `x-csrf-token` on the `/` response, causing detection to fail on the device itself (no proxy involved).
- **HTTP→HTTPS redirect**: The detection request follows redirects (`allow_redirects=True`), but if the final destination doesn't serve `x-csrf-token` (e.g. a landing page or portal), detection still returns `False`.

**Critical implication:** API keys are **UniFi OS-only** — they cannot be generated or used on self-hosted (classic) controllers. If a user has supplied an API key in the config, the controller is UniFi OS by definition. The code must not route API key verification requests through the legacy `/api/s/...` path regardless of what detection returns. `_verify_api_key()` hardcodes the `/proxy/network` prefix for this reason.

## Authentication

### Username/password (all controller types)

**Self-hosted:**
```
POST /api/login
{"username": "admin", "password": "..."}
```
Sets a session cookie. Subsequent requests use the cookie automatically (aiohttp `ClientSession` handles this).

**UniFi OS:**
```
POST /api/auth/login
{"username": "admin", "password": "..."}
```

Logout: `POST /api/logout` (self-hosted) or `POST /api/auth/logout` (UniFi OS).

**Important:** Do not enable 2FA/MFA on the account used for API access — it breaks non-interactive login. Use a dedicated read-only local account.

### API key (UniFi OS only)

API keys are stateless — no login/logout needed. They are generated in the UniFi OS web UI; the exact navigation path varies by firmware version:

- **Newer firmware (Network Application 8.x+):** Settings → Admins & Users → API Keys
- **Some firmware versions:** Integrations → New API Key
- **Older firmware:** Settings → Control Plane → API Keys

The API key inherits permissions from the admin account that created it.

Usage — pass the key as a request header on every call:

```
GET /proxy/network/api/s/default/alarm
X-API-Key: your-key-here
```

**Verification endpoint** (used during setup to confirm the key is valid):

```
GET /proxy/network/api/s/default/self
X-API-Key: your-key-here
```

This endpoint **always** requires the `/proxy/network` prefix — it does not exist at `/api/s/default/self`. `_verify_api_key()` hardcodes the `/proxy/network` prefix and does not rely on `_detect_unifi_os()`, so it works correctly even when detection returns a false negative.

> **Note on newer API (v2):** UniFi Network Application 8.x introduced a newer REST API under `/proxy/network/v2/api/`. For example, `GET /proxy/network/v2/api/site` lists all sites. The alarm endpoint remains at the classic `/proxy/network/api/s/{site}/alarm` (or `/stat/alarm` on some firmware) path as of the time of writing, but this may change in future firmware versions. The v2 API may be a better verification target if the classic endpoint is deprecated.

### Auto-detect logic (in `UniFiClient.authenticate()`)

1. Detect UniFi OS via header check
2. If `api_key` is present in config → try API key auth
3. If API key fails (or not present) → fall back to username/password
4. Store the detected auth method in `self._auth_method`

## Alarm API endpoint

**Self-hosted:** `GET /api/s/{site}/<path>`
**UniFi OS:** `GET /proxy/network/api/s/{site}/<path>`

> **Path variation by firmware — flagged for future maintainers.** UniFi has changed the alarm endpoint path multiple times. The integration probes them in newest-to-oldest order so modern firmware succeeds in one call:
>
> | Path | Era | Notes |
> |---|---|---|
> | `/list/alarm` | newest (UniFi Network 9.x+) | Tried first. Replaced `/stat/alarm` at some point in the 9.x release line. |
> | `/alarm` | long-standing | Universal historical path; still present on most firmware. Tried second. |
> | `/stat/alarm` | older intermediate | Some firmware exposes only this variant. Tried last. |
>
> A path that doesn't exist may return either `404` or `400 api.err.InvalidObject` depending on firmware — both are treated as "try the next path". A genuine `400` (e.g. wrong site name) is surfaced to the user only after **all** paths have been tried.
>
> **If UniFi changes the endpoint again:** add the new path to the head of `alarm_paths` in `unifi_client.py::fetch_alarms`, update this table, and add a fallback test in `tests/unit/test_unifi_client.py` (see `TestFetchAlarms::test_falls_back_*`).

Default site name is `default`. Multi-site deployments are not currently supported (see `TODO.md`).

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

The integration filters to `archived: false` records only. The `archived` field exists in API responses but **there is no documented write API to set it and no option in the UniFi Network UI to archive/dismiss individual alarms**. The field appears to be set only by internal Ubiquiti housekeeping processes that are opaque to integrators. In practice, `open_count` is a lifetime cumulative counter that can only grow.

#### Error responses

The controller returns HTTP 200 even for application-level errors. The `meta.rc` field distinguishes success from failure:

```json
{
  "meta": {"rc": "error", "msg": "api.err.InvalidObject"},
  "data": []
}
```

`meta.rc` is `"ok"` on success and `"error"` on failure. `meta.msg` contains a machine-readable error code (e.g. `api.err.InvalidObject` for an unrecognised object reference or invalid site name).

`fetch_alarms()` checks `meta.rc` after parsing the JSON body and raises `CannotConnectError` if it is not `"ok"`. This propagates as `UpdateFailed` in the coordinator and is surfaced as an integration error in Home Assistant.

### Field reliability

| Field | Reliability | Notes |
|---|---|---|
| `key` | High | Primary classification field. Format: `EVT_{prefix}_{event}` |
| `msg` | High | Human-readable message, varies by controller version |
| `archived` | High | Always present |
| `datetime` | Medium | ISO 8601 string, may be absent on older controllers |
| `device_name` | Medium | May be `ap_name`, `sw_name`, or absent |
| `site_name` | Low | Not always present |
| `severity` | Low | Not always present; values undocumented |
| `subsystem` | Low | Broad categories like `lan`, `wan`, `wlan` |

## Webhook payloads

When UniFi Alarm Manager sends a webhook POST, the JSON body structure differs from the polled alarm format. It is less consistent and varies across UniFi Network firmware versions.

Known field names for the alert message:
- `message` (most common in recent Network firmware)
- `msg` (some older Network firmware versions)
- `text` (observed in some Network firmware versions; treated as fallback)
- `description` (rare; observed in some Network firmware versions)

`UniFiAlert.from_webhook_payload()` tries these in order. These field names are all tried as defensive fallbacks regardless of which Network firmware version is sending the webhook. UniFi Protect webhooks are not supported.

The integration only accepts POST webhooks — GET requests are rejected with HTTP 405. UniFi Alarm Manager must be configured to send POST. JSON parse failures are caught and fall back to `{}`.

### Alert lifecycle

**What the integration can do:**
- Read open (`archived: false`) alarms via the poll API
- Receive real-time pushes via UniFi Alarm Manager webhooks
- Reset HA-local alert state via Clear buttons / `clear_category` / `clear_all` services; each Clear sets a per-category acknowledgement watermark so `open_count` reflects "alarms since last cleared" rather than a lifetime total

**What the integration cannot do — clearing alerts on the controller is not possible:**
- There is no documented write API for archiving individual Network alarms. The community-discovered `POST /cmd/evtmgt {"cmd":"archive-all-alarms"}` endpoint returns `api.err.NotFound` on current UniFi Network firmware — it no longer exists.
- There is no option in the UniFi Network UI to dismiss or archive individual alarms.
- Pressing **Clear** in HA resets HA-local state only (`is_alerting → false`, `alert_count → 0`, acknowledgement watermark → now). The underlying alarms remain on the controller indefinitely. Without the per-category watermark, `open_count` would grow to thousands without ever decreasing.

> **Design implication:** `open_count` without a watermark is a meaningless lifetime counter. The integration addresses this by persisting a `last_acknowledged_at` timestamp per category in `entry.options`. Polling counts only alarms newer than that timestamp. Pressing Clear advances the timestamp to now.

### Event entities and webhooks

**HA Event entities fire only via webhooks — not via polling.** This is by design:
- **Webhook path:** `push_alert()` increments `alert_count` → event entity detects the change in `_handle_coordinator_update` and fires `alert_received`
- **Polling path:** `open_count` and `is_alerting` are updated, but `alert_count` is NOT incremented — no Event entity fires

If webhooks are not configured in UniFi Alarm Manager, Event entities will never fire, even though binary sensors and sensors update normally via polling.

**Troubleshooting if events don't fire:**
1. Confirm webhooks are configured in UniFi Network → System → Alarm Manager → Integrations, pointing at the URLs shown during HA setup
2. Enable DEBUG logging for `custom_components.unifi_alerts` and look for `"Alert pushed to category"` — if absent, the webhook is not reaching the integration
3. Check HA logs for HTTP 401 responses — this indicates a webhook token mismatch
4. Verify the category configured in UniFi matches a category enabled in the HA integration options

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

The full mapping from key to category is in `UNIFI_KEY_TO_CATEGORY` in `const.py`. This list is **incomplete** — community-sourced and should be expanded as users report unclassified keys.

## Expanding the key map

When a user reports an alert that isn't being categorised (it will show up in HA logs as a debug message from `unifi_client.py`), add the key to `UNIFI_KEY_TO_CATEGORY` in `const.py`. If the key belongs to a new category type not yet in `ALL_CATEGORIES`, that's a larger change — see `TODO.md`.

Guidelines:
- Use the shortest prefix that uniquely identifies the event family (e.g. `EVT_GW_Honeypot` not `EVT_GW_HoneypotDetected` if there are multiple honeypot variants)
- Add a comment with the category group
- Add a corresponding test case in `test_unifi_client.py::TestClassify`

## Known API inconsistencies

- **Port 8443 vs 443**: Self-hosted controllers default to port 8443; UniFi OS uses 443. The integration does not auto-append a port — the user must include it in the controller URL.
- **SSL certificates**: Self-hosted controllers use self-signed certificates. `verify_ssl` defaults to `True` (secure by default). Users with self-signed certs must disable it via the config flow.
- **Site names**: Some controllers use `default`; others use the site ID (a hex string). Multi-site support is not implemented — see `TODO.md`.
- **Timestamp format**: The `datetime` field is usually ISO 8601 but some older controllers emit epoch milliseconds. `UniFiAlert.from_api_alarm()` has a try/except fallback to `datetime.now()`.
