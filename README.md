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
   - **API key** (UDM Pro, UCG Ultra, and other UniFi OS devices): generate one in the UniFi OS web UI (see [Generating an API key](#generating-an-api-key) below), leave Username/Password blank
   - **Username / password** (older controllers, Cloud Key): fill in Username and Password, leave API Key blank
3. Select the alert categories you want to monitor (see table above — client/device categories are noisy by default)
4. Configure polling interval and auto-clear timeout
5. **Copy the webhook URLs** shown on the final screen into UniFi Alarm Manager (see next section). Click **Submit** to save — the integration is not created until you click Submit.

> You can always retrieve your webhook URLs later from **Settings → Devices & Services → UniFi Alerts → Configure**.

---

## Generating an API key

API keys are supported on **UniFi OS consoles only** (UDM, UDM Pro, UDM SE, UCG-Ultra, Cloud Key Gen2+). They are not available on self-hosted (Linux/Windows) controllers.

The navigation path to create a key varies by firmware version:

| Firmware / UI version | Path |
|---|---|
| Network Application 8.x+ | **Settings → Admins & Users → API Keys → Create** |
| Some UCG / UDM firmware | **Integrations → API → New API Key** |
| Older Cloud Key Gen2+ | **Settings → Control Plane → API Keys** |

If you cannot find the option, try each path in order. The key is only displayed once at creation — copy it immediately and paste it into the integration setup.

> **Tip:** Create a dedicated read-only local admin account for the integration. Do not use a cloud account or an account with MFA enabled — non-interactive login will break.

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

## Examples

### Lovelace / dashboard card

The snippet below creates an **Entities card** showing network health at a glance: the rollup binary sensor lights up when any category is alerting, followed by per-category binary sensors and the total open-alarm count. Swap in only the categories you have enabled.

```yaml
type: entities
title: UniFi Network Health
entities:
  # Rollup — any category alerting
  - entity: binary_sensor.unifi_alerts_any_alert
    name: Any Alert Active

  # Per-category binary sensors (ON = alert active)
  - entity: binary_sensor.unifi_alerts_network_device
    name: Device Offline/Online
  - entity: binary_sensor.unifi_alerts_network_wan
    name: WAN Offline/Latency
  - entity: binary_sensor.unifi_alerts_security_threat
    name: Threat / IDS
  - entity: binary_sensor.unifi_alerts_security_firewall
    name: Firewall Block
  - entity: binary_sensor.unifi_alerts_power
    name: Power / PoE

  # Total open-alarm count (polled from controller)
  - entity: sensor.unifi_alerts_total_open_alerts
    name: Total Open Alerts
```

> **Tip:** For a more compact view, replace `type: entities` with `type: glance`. Per-category message sensors (`sensor.unifi_alerts_<category>_last_message`) and open-count sensors (`sensor.unifi_alerts_<category>_open_count`) can be added the same way.

---

### Automation example

UniFi Alerts uses Home Assistant **Event entities** (not the hass event bus). When an alert arrives the entity fires a single event of type `alert_received` and its state updates with the full payload as attributes. Trigger on the event entity using `platform: state`; the payload is available on `trigger.to_state.attributes`.

The event data attributes are:

| Attribute | Description |
|---|---|
| `message` | Human-readable alert text from UniFi |
| `category` | Integration category slug (e.g. `security_threat`) |
| `device_name` | UniFi device that raised the alert |
| `alert_key` | Raw UniFi event key (e.g. `EVT_IPS_ThreatDetected`) |
| `severity` | Severity string from the UniFi payload |
| `site` | UniFi site name (default: `default`) |
| `received_at` | ISO-8601 UTC timestamp |

```yaml
automation:
  - alias: "Notify on UniFi security threat"
    trigger:
      - platform: state
        entity_id: event.unifi_alerts_security_threat
    condition:
      # Only act when the entity actually fired a new event (state changes on each alert)
      - condition: template
        value_template: "{{ trigger.to_state.state != 'unavailable' }}"
    action:
      - service: persistent_notification.create
        data:
          title: "UniFi Security Alert"
          message: >
            {{ trigger.to_state.attributes.get('message', 'Unknown alert') }}
            (device: {{ trigger.to_state.attributes.get('device_name', 'unknown') }},
            key: {{ trigger.to_state.attributes.get('alert_key', '') }})
          notification_id: "unifi_security_threat"
```

> **Tip:** Replace `event.unifi_alerts_security_threat` with any per-category event entity (e.g. `event.unifi_alerts_network_device`, `event.unifi_alerts_power`). Swap `persistent_notification.create` for `notify.mobile_app_your_phone` or any other notify action.

---

## Contributing

Issues and PRs welcome at [github.com/PHeonix25/unifi_alerts](https://github.com/PHeonix25/unifi_alerts).

The UniFi event key → category mappings in `const.py` are community-sourced and incomplete. If you see unrecognised alerts in your HA logs, please open an issue with the raw `key` value.

### Development setup

**Requirements:** Python 3.12+, Git.

```bash
# 1. Clone and enter the repo
git clone https://github.com/PHeonix25/unifi_alerts.git
cd unifi_alerts

# 2. Install the pre-push hook (one-time, per clone)
git config core.hooksPath .githooks

# 3. Create a virtual environment and install all dev dependencies
make setup
```

### Running checks

```bash
make check      # run everything: lint, typecheck, HACS validation, tests (default)
make lint       # ruff lint + format check only
make typecheck  # mypy only
make validate   # HACS manifest pre-flight only
make test       # pytest only
```

`make check` is the same suite that CI runs. The pre-push hook runs it automatically before every `git push`, so CI should never see a failure that didn't appear locally first.

### CI pipeline

| Job | What it checks |
|---|---|
| **Validate with hassfest** | HA manifest schema and key ordering |
| **HACS manifest pre-flight** | Required fields, iot_class, no HA core built-ins in `dependencies` |
| **Validate with HACS Action** | Full HACS compatibility (runs after pre-flight) |
| **Lint & type-check** | ruff, mypy, and `strings.json` ↔ `translations/en.json` parity |
| **Run tests** | Full pytest suite (234 tests) |

### Key rules to know before submitting a PR

- **`manifest.json` `dependencies`** — do NOT list HA core built-ins (`webhook`, `http`, `frontend`, etc.). `hassfest` accepts them but the HACS validator rejects them and will fail CI. Only list external integrations that HACS needs to install.
- **`strings.json` and `translations/en.json`** must be kept identical. CI diffs them and fails if they diverge.
- **All I/O must be async** — no `requests`, no blocking calls.
- **No `configuration.yaml` support** — everything goes through the config flow.
- **Webhook token auth is mandatory** — do not remove or bypass the `?token=` check in `webhook_handler.py`.

See `CLAUDE.md` for the full developer context and `TESTING.md` for test conventions.
