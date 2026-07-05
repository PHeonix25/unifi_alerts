# UniFi Alerts - Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/PHeonix25/unifi_alerts)](https://github.com/PHeonix25/unifi_alerts/releases)
[![codecov](https://codecov.io/gh/PHeonix25/unifi_alerts/graph/badge.svg)](https://codecov.io/gh/PHeonix25/unifi_alerts)
[![AI Ready](https://img.shields.io/badge/AI--Ready-yes-brightgreen?style=flat)](https://github.com/johnpapa/ai-ready)

Aggregates **UniFi Network controller alerts** into Home Assistant sensors, binary sensors, and event entities. Real-time push via UniFi Alarm Manager webhooks, with REST polling as a backstop for open-count data and missed pushes.

---

## Features

- **Per-category binary sensors** - ON when an alert is active, OFF when clear
- **Per-category message sensors** - last alert message plus timestamp attributes
- **Per-category open-count sensors** - polled from the controller
- **Rollup sensors** - combined "any alert" binary and total open count
- **Event entities** - fire on every alert for automation triggers
- **Clear buttons** - manually reset any category or all at once
- **Auto-clear** - configurable timeout to reset sensors automatically
- **UI config flow** - full setup and options UI, no YAML
- **Auto-detect auth** - tries API key (UniFi OS) then falls back to username/password

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

- **Home Assistant** 2024.5 or later
- **UniFi OS console** - the classic self-hosted Network Application is not supported. The integration uses the `/proxy/network` API path, which is UniFi OS-only.
- **Local network reachability** - your UniFi controller and HA must share a network. Webhook URLs are local-only and cannot be reached over Nabu Casa remote access or from cloud-hosted controllers.
- **Credentials** - API key (recommended) or username + password.

### Tested controllers

| Model | Minimum firmware | Notes |
|---|---|---|
| UCG-Ultra | 4.0.x | Primary test platform |
| UDM-SE | 4.0.x | Reported by users |
| UCG-Max | 4.0.x | Reported by users |
| Cloud Key Gen2+ | 4.0.x | Reported by users |
| UDM / UDM-Pro | 4.0.x | Should work; not yet reported |

If your model is not listed, open an [issue](https://github.com/PHeonix25/unifi_alerts/issues) with controller model and firmware so we can grow this table.

---

## Installation

### Via HACS (recommended)

1. Open HACS > **Integrations** > three-dot menu > **Custom repositories**
2. Add `https://github.com/PHeonix25/unifi_alerts` with category **Integration**
3. Click **Download** on the UniFi Alerts card
4. Restart Home Assistant

### Manual

Copy `custom_components/unifi_alerts/` into your HA `config/custom_components/` directory and restart.

### Updating

After every HACS update (or manual file copy), **fully restart Home Assistant**. The integration's Reload action will not pick up new code or a new `manifest.json` version - HA caches imported Python modules in memory, and only a full restart re-imports them from disk.

1. HACS > **UniFi Alerts** > **Update**
2. **Settings > System > Restart Home Assistant > Restart Home Assistant**
3. Verify the new version on the device-info pane: **Settings > Devices & Services > UniFi Alerts**

---

## Setup

### 1. Generate a UniFi API key (recommended)

API keys are available on all supported UniFi OS consoles. The navigation path varies by firmware:

| Firmware / UI version | Path |
|---|---|
| Network Application 8.x+ | **Settings > Admins & Users > API Keys > Create** |
| Some UCG / UDM firmware | **Integrations > API > New API Key** |
| Older Cloud Key Gen2+ | **Settings > Control Plane > API Keys** |

The key is shown only once at creation - copy it immediately.

> **Tip:** Create a dedicated local admin account for the integration. Do not use a cloud account or one with MFA enabled, since non-interactive login will fail.

### 2. Add the integration in Home Assistant

1. **Settings > Devices & Services > Add Integration** > search **UniFi Alerts**
2. Enter your controller URL (e.g. `https://192.168.1.1`) and credentials. For API key auth, leave Username/Password blank; for username/password, leave API Key blank.
3. Select the alert categories you want to monitor (client/device categories are noisy by default).
4. Configure polling interval and auto-clear timeout.
5. **Copy the webhook URLs** shown on the final screen before clicking Submit. The integration is not created until you click Submit.

> You can retrieve webhook URLs later from **Settings > Devices & Services > UniFi Alerts > Configure**.

### 3. Configure UniFi Alarm Manager

For each enabled category, create an alarm in **UniFi Network > Settings > Notifications > Alarm Manager**:

1. Click **Create Alarm**
2. Set the **trigger** matching your category (see table below)
3. Set scope (specific devices or network-wide)
4. Under **Action**, choose **Webhook > Custom Webhook > POST**
5. Paste the webhook URL for that category from the HA integration page
6. Click **Create**

> **Test Alarm** in UniFi verifies the webhook reaches HA before you save.

#### Trigger reference

| Integration category | UniFi Alarm Manager trigger | Notes |
|---|---|---|
| Network: Device offline/online | **UniFi Devices** (or "Network Device" on older firmware) | APs, switches, gateways going offline or reconnecting |
| Network: WAN offline/latency | **Internet & WAN** | WAN failover, internet transitions |
| Network: Client connect/disconnect | **Client Devices** (or "Wireless Client" on older firmware) | Wireless and wired clients joining or leaving |
| Security: Threat / IDS detected | **Security** | IPS/IDS alerts, rogue AP detection |
| Security: Honeypot triggered | **Security** | Honeypot hit events; same trigger as the other Security categories |
| Security: Firewall block | **Security** | GeoIP filtered traffic, firewall deny events |
| Power: PoE / power loss | **Power** | PoE disconnect/overload, UPS events, power loss |

> **Security categories share a trigger.** All three Security categories (Threat, Honeypot, Firewall) use the same "Security" trigger type in Alarm Manager. If you enable more than one, create a separate alarm for each using the same trigger but paste each category's distinct webhook URL. When a security event fires, UniFi will call all three URLs; each receives the event and the integration routes it to the correct category based on the event key. To avoid this, enable only the security categories you actively use.

> **Webhook secret rotation:** if you regenerate the secret via the options flow, every existing URL becomes invalid immediately. Re-paste all new URLs into Alarm Manager, or affected alarms will silently fail with HTTP 401.

#### Confirming a category received its first webhook

You do not have to wait for a real alert to know the wiring works. Each per-category binary sensor exposes two attributes:

- `webhook_health`: `never_received` until the first webhook arrives, then `healthy`. It reads `stale` once more than 7 days pass without a webhook (expected for rarely-firing categories such as honeypot or threat).
- `last_webhook_at`: the UTC timestamp of the most recent webhook received for that category, or `None` if none has arrived.

Fire a **Test Alarm** from Alarm Manager (or trigger the event yourself) and watch `webhook_health` flip to `healthy`. A category still showing `never_received` after a test points to a wrong URL, a missing `?token=`, or an alarm whose trigger does not match the category. The same fields appear per category in the integration's **Download diagnostics** output.

### Multiple controllers or sites

You can add the integration more than once. Each instance has its own set of entities, webhook URLs, and config:

- **Multiple physical controllers** (e.g. a UDM Pro at one site plus a UCG Ultra at another): add the integration twice, once per controller URL. Each instance is independent.
- **Single controller, multiple UniFi sites**: still add the integration once per site you want to monitor. Use the same controller URL for each instance, but set a different **UniFi site name** in the "Configure Alert Categories" step. The site name appears in UniFi Network's URL (e.g. `https://192.168.1.1/network/site-name/`) and in the admin UI under **Settings > System > Sites**.

The **site name** field defaults to `default`, which is correct for controllers with a single site or controllers that have never been renamed. If you renamed your site in UniFi Network, enter the slug shown in the URL, not the human-readable display name.

> **Webhook URLs are per integration instance.** Each instance generates its own set of webhook URLs. If you add two instances for two sites on the same controller, configure separate alarms in each site's Alarm Manager pointing to the correct instance's URLs.

---

## Entities

Entity IDs are derived from the entity's display name, which HA slugifies on first install. The `unique_id` format is `{entry_id}_{category}_{sensor_type}`. Renaming an entity in the UI changes the friendly name only; the `unique_id` is stable, so automations referencing the entity ID remain valid.

Per-category entities (example uses `network_device`; the same pattern applies to all categories):

| Entity | Example entity ID | Type |
|---|---|---|
| Binary sensor | `binary_sensor.unifi_alerts_network_device_offline_online` | ON = alert active |
| Message sensor | `sensor.unifi_alerts_network_device_offline_online_last_message` | Last alert text |
| Count sensor | `sensor.unifi_alerts_network_device_offline_online_open_count` | Open alarm count |
| Event entity | `event.unifi_alerts_network_device_offline_online_event` | Fires per alert |
| Clear button | `button.unifi_alerts_clear_network_device_offline_online` | Manual clear |

Rollup entities (one per config entry, regardless of enabled categories):

| Entity | Entity ID | Type |
|---|---|---|
| Rollup binary | `binary_sensor.unifi_alerts_any_alert` | Any category alerting |
| Rollup count | `sensor.unifi_alerts_total_open_alerts` | Total open count |
| Clear all button | `button.unifi_alerts_clear_all_alerts` | Clear everything |

See [docs/EXAMPLES.md](docs/EXAMPLES.md) for a Lovelace dashboard card and an automation that fires on security threats.

---

## Privacy and data retention

All data stays on your local network; the integration does not communicate with any external service. For the full statement of what is stored, where, what appears in diagnostics downloads, and how to purge it, see [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md).

---

## Uninstall

**Settings > Devices & Services > UniFi Alerts > three-dot menu > Delete.**

---

## Support

- Common setup issues: [Troubleshooting](docs/TROUBLESHOOTING.md)
- Bug reports and questions: [github.com/PHeonix25/unifi_alerts/issues](https://github.com/PHeonix25/unifi_alerts/issues)
- Unrecognised alert keys: open an issue with the raw `key` value from your HA logs. The UniFi event key > category mappings in `const.py` are community-sourced and incomplete.

---

## Contributing

Issues and PRs welcome. The full developer guide lives in [docs/DEVELOPING.md](docs/DEVELOPING.md): local setup, running checks, the CI pipeline, branching strategy, and release process.

A short tour of the rest of the documentation:

| Document | When to read |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the modules fit together |
| [docs/HOMEASSISTANT.md](docs/HOMEASSISTANT.md) | HA-specific patterns: coordinators, entities, config flow |
| [docs/UNIFI.md](docs/UNIFI.md) | UniFi API, auth methods, alarm payload taxonomy |
| [docs/TESTING.md](docs/TESTING.md) | Test layout and conventions |
| [docs/REPO_LAYOUT.md](docs/REPO_LAYOUT.md) | Per-file responsibilities |
| [CLAUDE.md](CLAUDE.md) | Non-negotiable constraints and coding conventions |
