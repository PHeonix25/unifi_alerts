# Home Assistant patterns

Reference for Home Assistant-specific patterns used in this integration. Consult this when touching anything that extends an HA base class or interacts with HA core.

## Minimum supported version

**Home Assistant 2026.3** (requires Python 3.14), enforced by `hacs.json` and the pinned minimum-version CI leg. `ConfigEntry.runtime_data` (introduced in HA 2024.2), `ConfigFlowResult` return type annotation, and `Platform` enum usage require this version or newer. See `docs/DEVELOPING.md` § "Minimum supported Home Assistant version" for how the floor is kept in sync across `hacs.json`, CI, and the README.

## Config entries

This integration uses config entries exclusively; no `configuration.yaml` support.

- `async_setup_entry` in `__init__.py` is the entry point for all setup.
- Runtime state (coordinator, webhook URLs, unregister callable, HTTP client) is stored on `entry.runtime_data` as a `RuntimeData` dataclass (see `models.py`). Do **not** use `hass.data` for per-entry state.
- `async_unload_entry` must cleanly reverse everything `async_setup_entry` does: unload platforms, unregister webhooks, close the HTTP client.
- Options changes trigger `_async_update_listener`, which calls `async_reload`; this tears down and re-sets-up the entry cleanly. No partial reload logic needed.
- Config entry `VERSION = 3` (in `config_flow.py`). `async_migrate_entry` in `__init__.py` runs migrations sequentially: v1->v2 strips the legacy `is_unifi_os` key; v2->v3 backfills `webhook_secret`/`webhook_id_suffix` and raises a repair issue if the suffix changed. Bump `VERSION` and add a migration if the data schema changes again in a breaking way.

## DataUpdateCoordinator

`UniFiAlertsCoordinator` extends `DataUpdateCoordinator[dict[str, CategoryState]]`.

- `async_config_entry_first_refresh()` is awaited in `async_setup_entry`. If it fails, setup raises `ConfigEntryNotReady` and HA retries on the standard back-off. If the controller is unreachable at startup the entry stays in retry; intentional.
- `async_set_updated_data(data)` pushes data to all listeners immediately without waiting for the next poll interval. Used on webhook push.
- `self.data` reflects the last successful `_async_update_data` return value; since `_category_states` is mutated in place, `self.data` and `_category_states` point to the same dict. Don't rely on `self.data` for freshness; use the coordinator's public properties instead.
- Entities call `self.coordinator.async_request_refresh()` to force a poll. Do not call this on webhook push; use `async_set_updated_data` instead.

## Entity base classes

| Platform | Base class | Notes |
|---|---|---|
| `binary_sensor` | `CoordinatorEntity[...], BinarySensorEntity` | `is_on` returns bool |
| `sensor` | `CoordinatorEntity[...], SensorEntity` | `native_value` for state |
| `event` | `CoordinatorEntity[...], EventEntity` | Override `_handle_coordinator_update` to fire |
| `button` | `CoordinatorEntity[...], ButtonEntity` | `available` reflects category-enabled state |

All entities set `_attr_has_entity_name = True`. HA prefixes the entity name with the device name in the UI; entity IDs are of the form `binary_sensor.unifi_alerts_network_device`.

## Entity unique IDs

Format: `{entry.entry_id}_{category}_{suffix}` where suffix is `binary`, `message`, `count`, `event`, or `clear`.

Unique IDs must be stable across restarts. They are based on `entry.entry_id` (a UUID assigned by HA at first setup), not on the controller URL or any mutable config.

## Device registry

All entities use the same `_device_info` dict:

```python
{
    "identifiers": {(DOMAIN, entry.entry_id)},
    "name": "UniFi Alerts",
    "manufacturer": "Ubiquiti",
    "model": "UniFi Network Controller",
    "entry_type": "service",                  # not a physical device
    "configuration_url": entry.data["controller_url"],
}
```

`entry_type: "service"` tells HA this is a software integration, not a hardware device. `async_setup_entry` proactively registers this device via `dr.async_get_or_create` before platform forwarding so the Services card appears immediately, not lazily on first entity registration.

## Webhooks

Webhooks are registered with `homeassistant.components.webhook.async_register`.

- `local_only=True`: HA rejects requests from outside the local network at the framework level. Do not remove this without a documented reason.
- `allowed_methods=["POST"]`: only POST is accepted. UniFi Alarm Manager must be configured to send POST with a JSON body. GET requests are rejected with HTTP 405.
- Webhook IDs are deterministic strings: `unifi_alerts_{suffix}_{category}` (multi-entry safe; per-entry suffix is `secrets.token_hex(4)`) or `unifi_alerts_{category}` (legacy single-entry installs). They survive HA restarts without re-registration.
- `async_generate_url(hass, webhook_id)` generates the full URL including HA's `base_url`. Requires HA's external or internal URL to be configured correctly; otherwise the URL is wrong.

## Platforms

Platforms are declared in `PLATFORMS` in `__init__.py` and set up with `async_forward_entry_setups`. Each platform's `async_setup_entry` receives the `AddEntitiesCallback` and calls it with a list of entity instances.

When adding a new platform: add it to `PLATFORMS`, create `{platform}.py`, implement `async_setup_entry`, and add corresponding tests.

## aiohttp session lifecycle

**Always use `async_get_clientsession(hass, verify_ssl=...)`. Never create a bare `aiohttp.ClientSession()`**: not in `__init__.py`, not in `config_flow.py`, nowhere. HA owns the session lifecycle, configures the proxy / connection pool, and routes the user's `verify_ssl` setting through to it.

Two helpers exist; they have different ownership semantics:

| Helper | Ownership | Close it? |
|---|---|---|
| `async_get_clientsession(hass, verify_ssl=...)` | HA-owned shared session (one cached per `verify_ssl` value) | **Never** |
| `async_create_clientsession(hass)` | HA-owned dedicated session | **Never**; HA registers a cleanup handler that closes it on shutdown |

Calling `await session.close()` on either triggers a deprecation warning from `homeassistant.helpers.frame` and is treated as a bug by HA. The session is closed automatically when the integration unloads or HA shuts down.

```python
# DO: HA-managed, no try/finally needed
session = async_get_clientsession(hass, verify_ssl=verify_ssl)
client = UniFiClient(session, url, user_input)
await client.authenticate()

# DON'T: bare ClientSession bypasses HA's proxy + pool + verify_ssl wiring
async with aiohttp.ClientSession() as session:
    ...

# DON'T: close an HA-managed session
session = async_create_clientsession(hass)
try:
    ...
finally:
    await session.close()  # triggers HA warning
```

This applies to short-lived config-flow validation calls too: `async_get_clientsession` returns a cached session keyed by `verify_ssl`, so repeated calls during setup cost nothing.

## Direct `aiohttp` use

`aiohttp` is a Home Assistant core dependency and is always available. **Do not list `aiohttp` in `manifest.json` `requirements`**; hassfest treats core packages in custom-integration requirements as redundant. Importing `aiohttp` (e.g. for `aiohttp.ClientTimeout`, `aiohttp.ClientError`, `aiohttp.ClientResponseError`, or `aiohttp.web.Request` / `Response` in a webhook handler) is fine; that's working with the types, not creating sessions.

## Config flow patterns

- `async_show_form` returns a form to the user. The same step function is called again with `user_input` populated when the user submits.
- Validation errors go in `errors: dict[str, str]` where the key is a field name or `"base"` for form-level errors. Error codes map to strings in `strings.json` under `config.error`.
- `self.context` is a dict that persists across steps within a single flow.
- `async_create_entry` finalises the flow and writes `entry.data`; it triggers `async_setup_entry`.

## Translations

`strings.json` and `translations/en.json` must be kept **identical**. `strings.json` is used by the HA frontend tooling; `translations/en.json` is the runtime file loaded by HA.

Drift is caught automatically:

- CI `lint` job: diffs the two files and fails on mismatch.
- Pre-push hook (`.githooks/pre-push`): same diff before every `git push`.

If adding a new config-flow step or error code, update **both** files before committing.

## Logging

Use `_LOGGER.debug` for normal operational events (alert received, auth success). Use `_LOGGER.warning` for recoverable problems (auth expired, re-authenticating). Use `_LOGGER.error` for setup failures. Never use `print()`.

When logging exceptions raised from external systems (UniFi, aiohttp), log `type(err).__name__` only, never `str(err)`. Some `aiohttp.ClientError` subclasses embed credential-bearing URLs in their string representation; logging only the class name prevents credentials from leaking into HA logs and the repair UI.

## Testing with pytest-homeassistant-custom-component

The test suite has two layers:

- `tests/unit/` uses plain `MagicMock` / `AsyncMock` fixtures and does not start a real `HomeAssistant`. No HTTP calls escape.
- `tests/integration/` uses the real `hass` fixture from `pytest_homeassistant_custom_component`. `UniFiClient` is patched so no HTTP calls escape, but the HA setup lifecycle, entity registry, options flow, webhook dispatch, and auto-clear all run end-to-end.

Mark integration tests with `@pytest.mark.integration`. See `docs/TESTING.md` for fixtures and patterns.
