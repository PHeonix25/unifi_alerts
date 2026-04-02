# UniFi Alerts — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/PHeonix25/unifi_alerts)](https://github.com/PHeonix25/unifi_alerts/releases)

Aggregates **UniFi Network controller alerts** into Home Assistant sensors, binary sensors, and event entities. Supports real-time push via UniFi Alarm Manager webhooks and polling for historical/count data.

---

## Features

- **Per-category binary sensors** — ON when an alert is active, OFF when clear
- **Per-category message sensors** — last alert message + timestamp as attributes
- **Per-category open-count sensors** — polled from the controller
- **Rollup sensors** — combined "any alert" binary and total open count
- **Event entities** — fire on every alert for automation triggers
- **Clear buttons** — manually reset any category or all at once
- **Auto-clear** — configurable timeout to reset sensors automatically
- **UI config flow** — full setup and options UI, no YAML required
- **Auto-detect auth** — tries API key (UniFi OS) then falls back to username/password

### Alert categories

| Category | Covers |
| --- | --- |
| Network: Device offline/online | APs, switches, gateways disconnecting/reconnecting |
| Network: WAN offline/latency | WAN failover, internet access events |
| Network: Client connect/disconnect | Wireless and wired client join/leave |
| Security: Threat / IDS detected | IPS/IDS threat alerts |
| Security: Honeypot triggered | Honeypot hit events |
| Security: Firewall block | GeoIP and blocked traffic events |
| Power: PoE / power loss | PoE disconnect, power cycle, UPS events |

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/PHeonix25/unifi_alerts` with category **Integration**
3. Click **Download** on the UniFi Alerts card
4. Restart Home Assistant

### Manual

Copy `custom_components/unifi_alerts/` into your HA `config/custom_components/` directory and restart.

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration** → search **UniFi Alerts**
2. Enter your controller URL (e.g. `https://192.168.1.1`) and credentials
   - **API key** (UDM Pro, UCG Ultra, and other UniFi OS devices): generate one in **Settings → Admins & Users → API Keys**, leave Username/Password blank
   - **Username / password** (older controllers, Cloud Key): fill in Username and Password, leave API Key blank
3. Select the alert categories you want to monitor (see table above — client/device categories are noisy by default)
4. Configure polling interval and auto-clear timeout
5. **Copy the webhook URLs** shown on the final screen into UniFi Alarm Manager (see next section). Click **Submit** to save — the integration is not created until you click Submit.

> You can always retrieve your webhook URLs later from **Settings → Devices & Services → UniFi Alerts → Configure**.

---

## Configuring UniFi Alarm Manager

> ⚠️ **Local network required:** Webhook URLs are local-network only. Your UniFi controller must be on the same local network as your Home Assistant instance. Cloud-hosted controllers or remote access via Nabu Casa cannot reach these endpoints.

For each enabled category, create an alarm in **UniFi Network → Settings → Notifications → Alarm Manager**:

1. Click **Create Alarm**
2. Set the trigger(s) matching the category (see table above)
3. Set scope (specific devices or network-wide)
4. Under **Action**, choose **Webhook → Custom Webhook → POST**
5. Paste the webhook URL from the HA integration page
6. Click **Create**

> **Tip:** Use **Test Alarm** in UniFi to verify the webhook reaches HA before saving.

---

## Entities created

For each enabled category (example: `network_device`):

| Entity | ID pattern | Type |
| --- | --- | --- |
| Binary sensor | `binary_sensor.unifi_alerts_network_device` | ON = alert active |
| Message sensor | `sensor.unifi_alerts_network_device_last_message` | Last alert text |
| Count sensor | `sensor.unifi_alerts_network_device_open_count` | Open alarm count |
| Event entity | `event.unifi_alerts_network_device` | Fires per alert |
| Clear button | `button.unifi_alerts_clear_network_device` | Manual clear |

Plus rollup entities:

| Entity | ID | Type |
| --- | --- | --- |
| Rollup binary | `binary_sensor.unifi_alerts_any_alert` | Any category alerting |
| Rollup count | `sensor.unifi_alerts_total_open_alerts` | Total open count |
| Clear all button | `button.unifi_alerts_clear_all` | Clear everything |

---

## Automation example

```yaml
automation:
  - alias: "Notify on UniFi security threat"
    trigger:
      - platform: event
        event_type: unifi_alerts_event
        event_data:
          category: security_threat
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⚠️ UniFi Security Alert"
          message: "{{ trigger.event.data.message }}"
```

---

## Contributing

Issues and PRs welcome at [github.com/PHeonix25/unifi_alerts](https://github.com/PHeonix25/unifi_alerts).

The UniFi event key → category mappings in `const.py` are community-sourced and incomplete. If you see unrecognised alerts in your HA logs, please open an issue with the raw `key` value.
