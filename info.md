# UniFi Alerts for Home Assistant

Aggregates **UniFi Network controller alerts** into Home Assistant sensors, binary sensors, event entities, and buttons. Alerts arrive in real time via UniFi Alarm Manager webhooks and are supplemented by periodic REST polling for open-count data and resilience against missed pushes.

---

## Features

- **Real-time webhook push** — UniFi Alarm Manager POSTs alerts to per-category endpoints registered by HA; no polling delay for active alerts
- **REST polling fallback** — configurable interval keeps open-count sensors accurate even if a webhook is missed
- **Per-category binary sensors** — ON when an alert is active, auto-clears after a configurable timeout
- **Per-category message sensors** — last alert text and timestamp as state attributes
- **Per-category open-count sensors** — live count polled from the controller
- **Rollup sensors** — a single "any alert active" binary and a total open-count sensor
- **Event entities** — fire on every inbound alert; use as automation triggers
- **Clear buttons** — reset any individual category or all categories at once
- **UI config flow** — full setup and options UI; no YAML required
- **Auto-detect auth** — tries API key (UniFi OS) then falls back to username/password
- **Secure defaults** — SSL verification on, webhook bearer-token auth enforced, local-only endpoints

### Alert categories

| Category | Covers |
|---|---|
| Network: Device offline/online | APs, switches, gateways disconnecting/reconnecting |
| Network: WAN offline/latency | WAN failover, internet access events |
| Network: Client connect/disconnect | Wireless and wired client join/leave |
| Security: Threat / IDS detected | IPS/IDS threat alerts |
| Security: Honeypot triggered | Honeypot hit events |
| Security: Firewall block | GeoIP and blocked traffic events |
| Power: PoE / power loss | PoE disconnect, power cycle, UPS events |

---

## Requirements

- Home Assistant 2026.1.0 or later
- UniFi Network controller reachable on the same local network as your HA instance
- Credentials: API key (UniFi OS consoles) **or** username + password (older controllers)

> **Local network only:** webhook URLs are not reachable over Nabu Casa remote access or from cloud-hosted controllers.

---

## Quick setup

1. Install via HACS: **Integrations → Custom repositories** → add `https://github.com/PHeonix25/unifi_alerts` → **Download** → restart HA.
2. Go to **Settings → Devices & Services → Add Integration** → search **UniFi Alerts**.
3. Enter your controller URL and credentials (API key or username/password).
4. Select the alert categories you want to monitor and configure polling interval and auto-clear timeout.
5. **Copy the webhook URLs** shown on the final screen into **UniFi Network → Settings → Notifications → Alarm Manager** — one URL per category.

See the [full documentation](https://github.com/PHeonix25/unifi_alerts) for detailed instructions, screenshots, and an automation example.

---

## Links

- [Full documentation / README](https://github.com/PHeonix25/unifi_alerts)
- [Issue tracker](https://github.com/PHeonix25/unifi_alerts/issues)
- [Source code](https://github.com/PHeonix25/unifi_alerts)
- [License (MIT)](https://github.com/PHeonix25/unifi_alerts/blob/main/LICENSE)
