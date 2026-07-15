# UniFi Alerts for Home Assistant

[![codecov](https://codecov.io/gh/PHeonix25/unifi_alerts/graph/badge.svg)](https://codecov.io/gh/PHeonix25/unifi_alerts)

**Local network only: webhooks are not reachable over Nabu Casa remote access.**

Aggregates **UniFi Network controller alerts** into Home Assistant sensors, binary sensors, event entities, and buttons. Alerts arrive in real time via UniFi Alarm Manager webhooks, with periodic REST polling as a backstop for open-count data and missed pushes.

---

## Features

- **Real-time webhook push** - UniFi Alarm Manager POSTs alerts to per-category endpoints; no polling delay for active alerts
- **REST polling fallback** - configurable interval keeps open-count sensors accurate even if a webhook is missed
- **Per-category binary, message, and open-count sensors** - plus rollup "any alert" and total-open-count
- **Event entities** - fire on every inbound alert; use as automation triggers
- **Clear buttons** - reset any individual category or all categories at once
- **UI config flow** - full setup and options UI; no YAML required
- **API-key authentication** - a stateless `X-API-Key` header, no session cookies or login/logout
- **Secure defaults** - SSL verification on, webhook bearer-token auth enforced, local-only endpoints

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

- Home Assistant 2025.1 or later
- UniFi OS console (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+) running Network Application 8.x or later. Classic self-hosted Network Application is not supported.
- UniFi controller reachable on the same local network as your HA instance
- Credentials: a UniFi API key (the only supported credential)

---

## Quick setup

1. Generate a UniFi API key on your controller (**Settings > Admins & Users > API Keys** on Network Application 8.x+; the path varies slightly on older firmware).
2. Install via HACS, then restart Home Assistant.
3. **Settings > Devices & Services > Add Integration** > search **UniFi Alerts**.
4. Enter your controller URL and the API key.
5. Select alert categories, polling interval, and auto-clear timeout.
6. **Copy the webhook URLs** shown on the final screen into **UniFi Network > Settings > Notifications > Alarm Manager** - one URL per category - before clicking Submit.

See the [full README](https://github.com/PHeonix25/unifi_alerts) for the full API-key setup walkthrough, the Alarm Manager guide, dashboard examples, and troubleshooting.

---

## Links

- [Full documentation / README](https://github.com/PHeonix25/unifi_alerts)
- [Troubleshooting](https://github.com/PHeonix25/unifi_alerts/blob/main/docs/TROUBLESHOOTING.md)
- [Issue tracker](https://github.com/PHeonix25/unifi_alerts/issues)
- [License (MIT)](https://github.com/PHeonix25/unifi_alerts/blob/main/LICENSE)
