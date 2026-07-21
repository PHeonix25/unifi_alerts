# Troubleshooting

Common setup and operational issues, with verified diagnostics.

---

## Webhooks never arrive but the integration is set up

The integration appears healthy - no errors in HA logs, entities are created - but alarms never trigger sensors.

The canonical diagnostic is to run the following **from the UniFi controller itself** (SSH in):

```bash
curl -i -X POST '<webhook_url>' -H 'Content-Type: application/json' -d '{}'
```

Why the location matters:

- Running curl from HA proves only that loopback works.
- Running curl from another LAN device proves LAN routing works.
- Only running curl from the controller proves that the controller can reach HA.

Field case: a stale local DNS entry on the UniFi controller pointed `ha.example` at the wrong IP. Alarm Manager POSTs went into a black hole even though every other LAN device could reach HA. HA logs showed no rejected requests because the POSTs never arrived. The controller-side curl was the only test that surfaced the DNS mismatch.

If the controller-side curl returns a non-2xx response (or times out), the issue is network reachability from the controller - not HA configuration. Check DNS resolution on the controller, firewall rules between the controller VLAN and the HA host, and whether your HA instance is bound to the correct network interface.

---

## Old webhook token silently dropped after Regenerate

Symptom: alarms were working, then you rotated the webhook secret via the options flow, and now nothing comes through. HA logs show lines like:

```
WARNING ... Webhook request for category <name> rejected: missing or invalid token
```

Cause: rotating the webhook secret invalidates every `Authorization` header value and legacy `?token=...` query parameter that Alarm Manager already has. Neither matches the new secret, so every POST is rejected with HTTP 401. HA's default log level surfaces WARNING, so these rejections are visible in Settings > System > Logs without enabling DEBUG.

Fix: after regenerating, re-open the options flow finish step, copy the new secret, and update the `Authorization` header (or re-paste the `?token=` URL) for each category in UniFi Network > Settings > Notifications > Alarm Manager. Every category needs updating - a single stale secret means that category silently 401s.

If you do not update Alarm Manager promptly, alarms continue to fire on the UniFi side but none reach HA.

---

## Event entities show Unknown on fresh install

Symptom: immediately after setup (or after an HA restart), all `*_Event` entities show state "Unknown" in the entity list.

This is expected. HA event entities have no persistent state. They carry the payload from the most recent fired event and nothing else. On a fresh install - or after an HA restart before the first webhook arrives - there is no previous event to show, so the state is "Unknown".

The entities update the moment the first real alarm webhook is received. No action is required. Automations that trigger on these entities will fire correctly once alerts start arriving.

---

## Open Count shows 0 immediately after an alarm fires

Symptom: a webhook arrives, the binary sensor flips to Problem and the event entity fires, but the Open Count sensor shows 0 (or a stale value) for up to a minute.

Cause: the webhook path and the REST polling path are independent. When a webhook arrives, `is_alerting` flips and the event entity fires immediately. The `open_count` sensor is populated from the REST poll only, and the default poll interval is 60 seconds. For up to one full poll interval after a webhook fires, the binary sensor and count sensor can disagree.

This is expected behaviour, not a bug. The count will reconcile on the next poll. If you need the count to update faster, reduce the polling interval in the integration options (Settings > Devices & Services > UniFi Alerts > Configure > polling interval).
