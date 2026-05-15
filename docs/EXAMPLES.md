# Examples

Dashboard cards and automations that work with the entities this integration creates. See the [Entities](../README.md#entities) section in the README for the full entity list.

---

## Lovelace dashboard card

An **Entities card** showing network health at a glance: the rollup binary sensor lights up when any category is alerting, followed by per-category binary sensors and the total open-alarm count. Swap in only the categories you have enabled.

```yaml
type: entities
title: UniFi Network Health
entities:
  # Rollup - any category alerting
  - entity: binary_sensor.unifi_alerts_any_alert
    name: Any Alert Active

  # Per-category binary sensors (ON = alert active)
  - entity: binary_sensor.unifi_alerts_network_device_offline_online
    name: Device Offline/Online
  - entity: binary_sensor.unifi_alerts_network_wan_offline_latency
    name: WAN Offline/Latency
  - entity: binary_sensor.unifi_alerts_security_threat_ids_detected
    name: Threat / IDS
  - entity: binary_sensor.unifi_alerts_security_firewall_block
    name: Firewall Block
  - entity: binary_sensor.unifi_alerts_power_poe_power_loss
    name: Power / PoE

  # Total open-alarm count (polled from controller)
  - entity: sensor.unifi_alerts_total_open_alerts
    name: Total Open Alerts
```

> **Tip:** For a more compact view, replace `type: entities` with `type: glance`. Per-category message and open-count sensors follow the same naming pattern, for example: `sensor.unifi_alerts_network_device_offline_online_last_message` and `sensor.unifi_alerts_network_device_offline_online_open_count`.

---

## Automation: notify on security threat

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
        entity_id: event.unifi_alerts_security_threat_ids_detected_event
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

> **Tip:** Replace `event.unifi_alerts_security_threat_ids_detected_event` with any per-category event entity (e.g. `event.unifi_alerts_network_device_offline_online_event`, `event.unifi_alerts_power_poe_power_loss_event`). Swap `persistent_notification.create` for `notify.mobile_app_your_phone` or any other notify action.

---

## Automation caveats

- **Event entities show `unknown` until the first alert fires.** `EventEntity` has no persistent state - it only carries the data from the most recent event. On a fresh install or after an HA restart, all event entities start in `unknown` state. This is normal and expected; your automations will trigger correctly once the first alert arrives.
- **Disabling a category makes its event entity `unavailable`.** If you disable a category in **Settings > Devices & Services > UniFi Alerts > Configure**, the corresponding event entity becomes unavailable and any automation that triggers on it will silently stop firing. Re-enable the category or update the automation accordingly.
