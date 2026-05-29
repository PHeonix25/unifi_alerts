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
- **Auto-detect auth** - API key (recommended) or username/password
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

- Home Assistant 2024.5 or later
- UniFi OS console (UDM, UDM-Pro, UDM-SE, UCG-Ultra, UCG-Max, Cloud Key Gen2+). Classic self-hosted Network Application is not supported.
- UniFi controller reachable on the same local network as your HA instance
- Credentials: API key (recommended) or username + password

---

## Quick setup

1. Install via HACS, then restart Home Assistant.
2. **Settings > Devices & Services > Add Integration** > search **UniFi Alerts**.
3. Enter your controller URL and credentials.
4. Select alert categories, polling interval, and auto-clear timeout.
5. **Copy the webhook URLs** shown on the final screen into **UniFi Network > Settings > Notifications > Alarm Manager** - one URL per category - before clicking Submit.

See the [full README](https://github.com/PHeonix25/unifi_alerts) for the API-key path, the Alarm Manager walkthrough, dashboard examples, and troubleshooting.

---

## Links

- [Full documentation / README](https://github.com/PHeonix25/unifi_alerts)
- [Troubleshooting](https://github.com/PHeonix25/unifi_alerts/blob/main/docs/TROUBLESHOOTING.md)
- [Issue tracker](https://github.com/PHeonix25/unifi_alerts/issues)
- [License (MIT)](https://github.com/PHeonix25/unifi_alerts/blob/main/LICENSE)
