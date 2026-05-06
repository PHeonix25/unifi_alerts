# TODO

Outstanding work only. Items are removed when they ship; completion lives in `docs/HISTORY.md`, and the per-release plan lives in `docs/ROADMAP.md`.

## 🟡 High-value

- **Verify update-in-place**: confirm a HACS file copy + config-entry reload (Settings > Integrations > UniFi Alerts > ⋮ > Reload) is enough on a real HA install. A forced restart would be a friction point. Document the expected flow in `README.md`.
- **README + info.md examples sweep**: confirm sensor names in the dashboard / automation YAML match the current `unique_id` format and that no copy still references self-hosted controllers.

## 🟢 Nice-to-have

- **HACS default catalogue submission**: open the PR to <https://github.com/hacs/default> once all v1.x items below are closed.
- **Tier 2 docs linter (markdownlint)**: layer `markdownlint-cli2` on top of `scripts/validate_docs.py` to catch structural issues (heading-level skips, mixed list markers, bare URLs, trailing whitespace) that a regex linter cannot. Adds a Node dependency; commit a `.markdownlint.json` config tuned for this repo. Run it from CI's `lint` job and the pre-push hook alongside the existing prose check.

## Reliability / correctness

- **Polling re-asserts `is_alerting` for alarms older than the watermark** (`coordinator.py:127-134`): `_async_update_data()` filters by `last_cleared_at` when computing `open_count` but uses the **unfiltered** list when deciding whether to flip `is_alerting` and update `last_alert`. After Clear, the watermark zeroes `open_count`, but the next poll re-discovers the same pre-watermark alarm and re-asserts `is_alerting` with a stale message. Field-confirmed: UI shows status=Problem + Open Count=0 simultaneously. Fix: apply the watermark filter to the `is_alerting` branch too. Add a regression test in `test_coordinator.py` that sets a watermark via `async_clear_category()`, runs `_async_update_data()` with an alarm where `received_at < watermark`, and asserts `is_alerting is False`, `last_alert is None`, `open_count == 0`.
- **`_auto_clear` does not persist watermarks** (`coordinator.py:298-304`): `state.clear()` advances `last_cleared_at` in memory but `_async_persist_watermarks()` is never awaited, so an HA restart after a timer-triggered clear loses the watermark and `open_count` jumps back to the lifetime total.
- **Epoch-ms timestamps dropped** (`models.py:54-63`): `datetime.fromisoformat(str(ts))` rejects numeric strings, so polled alerts using epoch-ms `datetime`/`timestamp` fields silently fall back to `now(UTC)`. Add an epoch-ms branch before the ISO fallback.
- **`open_count` lags on webhook path** (`coordinator.py`): `push_alert()` updates `is_alerting` and `alert_count` but never touches `open_count`; only polling sets it. For up to one poll interval (default 60 s) after a webhook, the binary sensor shows Problem while Open Count shows 0. Field-confirmed: `alert_count=14`, `open_count=0`. Root causes confirmed: (1) `push_alert()` never increments `open_count`; (2) `/list/alarm` has a hard ~3000-record cap sorted oldest-first, so on busy controllers (more than ~33 alarms/day) recent alarms are not present in the polled response at all and poll-time reconciliation never fires. Disproven hypotheses (recorded to prevent re-investigation): (a) UniFi auto-archives IPS alarms - no archive API exists; (b) IPS events live at `/stat/ips/event` - that endpoint returns `api.err.NotFound` on Network 10.x; `/list/alarm` does contain `EVT_IPS_IpsAlert`. Short-term fix (v1.5.0): optimistic increment in `push_alert()` when `alert.received_at > state.last_cleared_at`, with poll-time correction. Long-term fix (v1.6.0): switch polling to the v2 `system-log/all` API (see "Polling strategy" item below). Full investigation: `docs/research/alert-endpoints.md`.
- **Polling strategy must switch to v2 system-log API for busy controllers** (`unifi_client.py`): `/list/alarm` caps at ~3000 records oldest-first. The v2 `POST /proxy/network/v2/api/site/{site}/system-log/all` endpoint supports `timestampFrom`/`timestampTo` (epoch ms) and `pageNumber`/`pageSize` pagination; field-confirmed working on Network 10.3.58. Implementation: probe `/system-log/count` on startup; if available, use `system-log/all` with `timestampFrom = last_cleared_at or (now - 24h)` for polling; fall back to legacy `/list/alarm` for older controllers. Requires a new `UniFiAlert.from_system_log_event()` parser (the v2 schema uses `message_raw` + `parameters` templates, epoch-ms `timestamp`, `status: "NEW"`, and a new key format with no `EVT_` prefix) and a separate v2 key-to-category map. See `docs/research/alert-endpoints.md` and `docs/UNIFI.md § v2 system-log API`.
- **`_category_states` rebuilt on reload** (`coordinator.py`): `alert_count` and `last_alert` are discarded on every options change. Persist them alongside watermarks in the existing `Store`.
- **Silent JSON-parse failure during 400-error inspection** (`unifi_client.py`): `except Exception: pass` swallows malformed UniFi error bodies, hiding the `api.err.InvalidObject` fallback. Log at DEBUG with the exception class name.

## Security

- **Options-flow credential changes persist before the user submits the flow** (`config_flow.py`): `async_step_credentials` calls `async_update_entry()` eagerly. Abandoning the flow after credentials but before finish leaves the change persisted. Stage into `self._pending_data` and persist atomically in `async_step_finish`.
- **`verify_ssl` toggle alone does not persist** (`config_flow.py`): `credentials_changed` ignores the SSL flag. Flipping the checkbox without other changes is a no-op. Best landed alongside the staging refactor above.

## Type safety / tech debt

- **`mypy strict = false`**: migrate `UniFiClient.config: dict[str, Any]` to a `TypedDict` or frozen dataclass, then bump `pyproject.toml` to `strict = true`.
- **No sensor `device_class`** (`sensor.py`): open-count and rollup-count sensors have no class. None of HA's built-ins map cleanly; consider richer `state_class` instead.
- **Buttons don't inherit `CoordinatorEntity`** (`button.py`): `UniFiClearCategoryButton` and `UniFiClearAllButton` extend `ButtonEntity` directly, so they always appear available even when their category is disabled. Add the mixin and an `available` property.

## Testing

- **`test_auto_clear_persists_watermark`**: assert `_store.async_save` is called when `_auto_clear` fires (red-green pair for the bug above).
- **`test_from_api_alarm_epoch_ms`**: assert a numeric epoch-ms timestamp produces the correct UTC datetime.
- **Webhook-mid-poll interleaving test** (`test_coordinator.py`): assert a webhook arriving while `_async_update_data()` is awaited does not regress `is_alerting`.
- **`make lint` to cover `tests/`**: extend the Makefile target and resolve the six pre-existing `I001`/`F401` issues in `test_services.py` and `test_config_flow.py`.
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
