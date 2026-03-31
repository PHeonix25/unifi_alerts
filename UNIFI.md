# UNIFI.md

Reference for the UniFi Network controller API as used by this integration. The API is partially undocumented and community-reverse-engineered — treat all field names as potentially unstable across controller versions.

## Controller types

The integration must handle two distinct controller environments:

| Type | Detection | API base path | Auth |
|---|---|---|---|
| **Self-hosted** (Linux/Windows software) | No `x-csrf-token` header on `/` | `/api/...` | Session cookie (user/pass only) |
| **UniFi OS** (UDM, UDM Pro, UDM SE, UCG, UCG-Ultra, Cloud Key Gen2+) | `x-csrf-token` header present | `/proxy/network/api/...` | Session cookie **or** API key |

Detection happens in `UniFiClient._detect_unifi_os()` by making a HEAD/GET to `/` and checking response headers.

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

Generated in UniFi OS Settings → Control Plane → API Keys (or similar, varies by version). Stateless — no login/logout needed.

```
GET /proxy/network/api/s/default/alarm
X-API-Key: your-key-here
```

The API key inherits permissions from the admin account that created it.

### Auto-detect logic (in `UniFiClient.authenticate()`)

1. Detect UniFi OS via header check
2. If `api_key` is present in config → try API key auth
3. If API key fails (or not present) → fall back to username/password
4. Store the detected auth method in `self._auth_method`

## Alarm API endpoint

**Self-hosted:** `GET /api/s/{site}/alarm`
**UniFi OS:** `GET /proxy/network/api/s/{site}/alarm`

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

The integration filters to `archived: false` records only. Archived alarms are ones the user has dismissed in the UniFi UI.

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

When UniFi Alarm Manager sends a webhook POST, the JSON body structure differs from the polled alarm format. It is less consistent and varies by UniFi application (Network vs Protect) and version.

Known field names for the message:
- `message` (most common in recent Network versions)
- `msg` (older Network, some Protect)
- `text` (some Protect events)
- `description` (rare)

`UniFiAlert.from_webhook_payload()` tries these in order.

GET webhooks (UniFi's default) have no body — the integration handles this by catching JSON parse failures and using `{}`.

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
- **SSL certificates**: Self-hosted controllers use self-signed certificates. `verify_ssl` defaults to `False`. Users with valid certs can enable it via the config flow.
- **Site names**: Some controllers use `default`; others use the site ID (a hex string). Multi-site support is not implemented — see `TODO.md`.
- **Timestamp format**: The `datetime` field is usually ISO 8601 but some older controllers emit epoch milliseconds. `UniFiAlert.from_api_alarm()` has a try/except fallback to `datetime.now()`.
