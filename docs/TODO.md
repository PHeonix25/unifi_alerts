# TODO

Outstanding work only. Items are removed when they ship; completion lives in `docs/HISTORY.md`, and the per-release plan lives in `docs/ROADMAP.md`.

## 🟢 Nice-to-have

- **HACS default catalogue submission**: open the PR to <https://github.com/hacs/default> once all v1.x items below are closed.
- **Tier 2 docs linter (markdownlint)**: layer `markdownlint-cli2` on top of `scripts/validate_docs.py` to catch structural issues (heading-level skips, mixed list markers, bare URLs, trailing whitespace) that a regex linter cannot. Adds a Node dependency; commit a `.markdownlint.json` config tuned for this repo. Run it from CI's `lint` job and the pre-push hook alongside the existing prose check.

## Reliability / correctness

- **Polling strategy must switch to v2 system-log API for busy controllers** (`unifi_client.py`): `/list/alarm` caps at ~3000 records oldest-first. The v2 `POST /proxy/network/v2/api/site/{site}/system-log/all` endpoint supports `timestampFrom`/`timestampTo` (epoch ms) and `pageNumber`/`pageSize` pagination; field-confirmed working on Network 10.3.58. Implementation: probe `/system-log/count` on startup; if available, use `system-log/all` with `timestampFrom = last_cleared_at or (now - 24h)` for polling; fall back to legacy `/list/alarm` for older controllers. Requires a new `UniFiAlert.from_system_log_event()` parser (the v2 schema uses `message_raw` + `parameters` templates, epoch-ms `timestamp`, `status: "NEW"`, and a new key format with no `EVT_` prefix) and a separate v2 key-to-category map. See `docs/research/alert-endpoints.md` and `docs/UNIFI.md § v2 system-log API`.
- **`_category_states` rebuilt on reload** (`coordinator.py`): `alert_count` and `last_alert` are discarded on every options change. Persist them alongside watermarks in the existing `Store`.

## Type safety / tech debt

- **`mypy strict = false`**: migrate `UniFiClient.config: dict[str, Any]` to a `TypedDict` or frozen dataclass, then bump `pyproject.toml` to `strict = true`.
- **No sensor `device_class`** (`sensor.py`): open-count and rollup-count sensors have no class. None of HA's built-ins map cleanly; consider richer `state_class` instead.

## Testing

- **Webhook-mid-poll interleaving test** (`test_coordinator.py`): assert a webhook arriving while `_async_update_data()` is awaited does not regress `is_alerting`.
- **Optional: integration test for full rotation cycle**: options-flow > entry-update > reload > re-register, end-to-end. Each step is unit-tested already.

## Documentation

- **Supported-firmware matrix** in README/info.md: table of tested UDM-SE / UCG-Ultra / UCG-Max / Cloud Key Gen2+ models with firmware versions.
- **Troubleshooting / FAQ section**: consolidate scattered notes (local-only webhooks, self-signed certs, "why is `open_count` so high?", API-key generation paths, cloud-access failures). Scenarios to include:
  - **"Webhooks never arrive but the integration is set up"**: the canonical diagnostic is `curl -i -X POST '<webhook_url>' -H 'Content-Type: application/json' -d '{}'` **from the UniFi controller itself** (SSH in). Curl from HA only proves loopback works; curl from a third LAN device proves LAN routing works; only the controller-side curl proves the controller can actually reach HA. Field case: a stale local DNS entry on the UniFi controller pointed `ha.example` at the wrong IP, so Alarm Manager POSTs went into a black hole even though `local_only` accepted requests from every other LAN device. The controller-side curl was the only test that surfaced it.
  - **"Old webhook token silently dropped after Regenerate"**: rotating the webhook secret in the options flow invalidates every URL Alarm Manager already has. Subsequent POSTs with the old `?token=...` are rejected with HTTP 401 by `webhook_handler.py:124-128` and logged at `WARNING` level (`Webhook request for category %s rejected: missing or invalid token`). HA's default log level shows WARNING, so it's visible in **Settings > System > Logs** without enabling DEBUG. Users filtering to ERROR-only will miss it. After regeneration, the new URLs must be re-pasted into Alarm Manager or every alarm silently 401s.
  - **"Event entities show Unknown on fresh install"**: HA event entities have no persistent state; they only update when an event fires. On a brand-new install (or after an HA restart before the first webhook arrives) all `*_Event` entities show "Unknown". This is expected. They update to the event type and payload the moment the first real alarm webhook is received.
  - **"Open Count shows 0 immediately after an alarm fires"**: `push_alert()` (the webhook path) updates `is_alerting` and fires the event entity immediately, but `open_count` only refreshes on the next REST poll (default every 60 seconds). For up to one poll interval after a webhook, the binary sensor shows Problem while the Open Count sensor shows 0. This is a known gap tracked under Reliability above; the FAQ should explain the delay rather than leaving users to think the count sensor is broken.
- **Uninstall instructions**: one-liner: Settings > Devices & Services > UniFi Alerts > ⋮ > Delete.
- **`info.md` local-network warning**: bold "⚠ Local network only: webhooks are not reachable over Nabu Casa remote access" in the first paragraph.
- **Setup-flow webhook copy warning**: `strings.json` note on the finish step: "Copy all URLs into UniFi Network > Settings > Notifications > Alarm Manager **before** clicking Submit."
- **Privacy / data-retention section** in README: which payload fields are stored, that nothing leaves the local network, that auto-clear removes `is_alerting`/`last_alert` after the configured timeout.
- **Automation edge case** in README: disabling a category in options makes its event entity unavailable, breaking dependent automations.
- **`unique_id` format** in README: document `{entry_id}_{category}_{sensor_type}` and that UI renames preserve the unique_id so automations are safe.

## Architecture

- **Entity naming via `_attr_translation_key`**: all four platform files hard-code `_attr_name = f"{CATEGORY_LABELS[cat]} ..."`. Migrate to `has_entity_name = True` + `_attr_translation_key` so strings live in `strings.json`. Unlocks localisation.
- **Split `tests/unit/test_config_flow.py` into a package**: ~1405 lines with four logically independent classes; rebase chains across classes produce interleaved conflicts. Convert to `tests/unit/config_flow/{__init__,conftest,test_setup,test_options,test_reauth}.py`.

## Known issues

- **`_device_info()` duplication**: duplicated identically across `binary_sensor.py`, `sensor.py`, `event.py`, `button.py`. Intentional for platform isolation; extract to a shared `entity_base.py` only if it becomes a maintenance burden.
