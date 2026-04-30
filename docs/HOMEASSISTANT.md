# HOMEASSISTANT.md

Reference for Home Assistant-specific patterns used in this integration. Consult this when touching anything that extends an HA base class or interacts with the HA core.

## Minimum supported version

**Home Assistant 2024.5** (requires Python 3.12). `ConfigEntry.runtime_data` (introduced in HA 2024.2), `ConfigFlowResult` return type annotation, and `Platform` enum usage require this version or newer.

## Config entries

This integration uses config entries exclusively — no `configuration.yaml` support.

- `async_setup_entry` in `__init__.py` is the entry point for all setup.
- Runtime state (coordinator, webhook URLs, unregister callable, HTTP client) is stored on `entry.runtime_data` as a `RuntimeData` dataclass (see `models.py`). Do **not** use `hass.data` for per-entry state.
- `async_unload_entry` must cleanly reverse everything `async_setup_entry` does: unload platforms, unregister webhooks, close the HTTP client.
- Options changes trigger `_async_update_listener`, which calls `async_reload` — this tears down and re-sets-up the entry cleanly. No partial reload logic needed.
- Config entry `VERSION = 1` in `config_flow.py`. If the data schema changes in a breaking way, increment this and add a migration step `async_migrate_entry`.

## DataUpdateCoordinator

`UniFiAlertsCoordinator` extends `DataUpdateCoordinator[dict[str, CategoryState]]`.

Important HA coordinator behaviour to be aware of:
- `async_config_entry_first_refresh()` is called in `async_setup_entry`. If it raises `UpdateFailed`, setup fails and HA shows an error. If the controller is unreachable at startup, this will fail the entry — this is intentional.
- `async_set_updated_data(data)` pushes data to all listeners immediately without waiting for the next poll interval. Used on webhook push.
- `self.data` on the coordinator always reflects the last successful `_async_update_data` return value — but since `_category_states` is mutated in place, `self.data` and `_category_states` point to the same dict. Don't rely on `self.data` for freshness — use the coordinator's public properties instead.
- Entities call `self.coordinator.async_request_refresh()` if they need to force a poll. Do not call this on webhook push — use `async_set_updated_data` instead.

## Entity base classes

| Platform | Base class | Notes |
|---|---|---|
| `binary_sensor` | `CoordinatorEntity[...], BinarySensorEntity` | `is_on` returns bool |
| `sensor` | `CoordinatorEntity[...], SensorEntity` | `native_value` for state |
| `event` | `CoordinatorEntity[...], EventEntity` | Override `_handle_coordinator_update` to fire |
| `button` | `ButtonEntity` | No coordinator subscription needed |

All entities set `_attr_has_entity_name = True`. This means HA prefixes the entity name with the device name in the UI. Entity IDs will be of the form `binary_sensor.unifi_alerts_network_device`.

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
    "entry_type": "service",   # not a physical device
}
```

`entry_type: "service"` tells HA this is a software integration, not a hardware device. This affects how it's shown in the device registry UI.

## Webhooks

Webhooks are registered with `homeassistant.components.webhook.async_register`.

- `local_only=True` — HA rejects requests from outside the local network at the framework level. Do not remove this.
- `allowed_methods=["POST"]` — only POST is accepted. UniFi Alarm Manager must be configured to send POST with a JSON body. GET requests are rejected with HTTP 405.
- Webhook IDs are deterministic strings (`unifi_alerts_{category}`), not UUIDs, so they survive HA restarts.
- `async_generate_url(hass, webhook_id)` generates the full URL including HA's `base_url`. This requires HA's external URL or internal URL to be configured correctly — if it isn't, the URL will be incorrect. This is a known limitation (see `TODO.md`).

## Platforms

Platforms are declared in `PLATFORMS` in `__init__.py` and set up with `async_forward_entry_setups`. Each platform's `async_setup_entry` receives the `AddEntitiesCallback` and calls it with a list of entity instances.

When adding a new platform: add it to `PLATFORMS`, create `{platform}.py`, implement `async_setup_entry`, and add corresponding tests.

## aiohttp session lifecycle

Two helpers exist; they have different ownership semantics:

| Helper | Ownership | Close it? |
|---|---|---|
| `async_get_clientsession(hass)` | HA-owned shared session | **Never** |
| `async_create_clientsession(hass)` | HA-owned dedicated session | **Never** — HA registers a cleanup handler that closes it on shutdown |

Calling `await session.close()` on either will trigger a deprecation warning from `homeassistant.helpers.frame` and is treated as a bug by HA. The session will be closed automatically when the integration is unloaded or HA shuts down.

If you need a truly short-lived session with explicit lifecycle control (e.g. a one-off auth check in a config flow), create a raw `aiohttp.ClientSession()` yourself and use it as an async context manager:

```python
# DO: own it explicitly
async with aiohttp.ClientSession() as session:
    client = UniFiClient(session, url, user_input)
    auth_method = await client.authenticate()

# DON'T: close an HA-managed session
session = async_create_clientsession(hass)
try:
    ...
finally:
    await session.close()  # triggers HA warning
```

The config flow `async_step_user` currently does the wrong thing — see `TODO.md`.

## Config flow patterns

- `async_show_form` returns a form to the user. The same step function is called again with `user_input` populated when the user submits.
- Validation errors go in `errors: dict[str, str]` where the key is a field name or `"base"` for form-level errors. Error codes map to strings in `strings.json` → `config.error`.
- `self.context` is a dict that persists across steps within a single flow. Used here to pass credentials from step 1 to step 2.
- `async_create_entry` finalises the flow and writes `entry.data`. It triggers `async_setup_entry`.

## Translations

`strings.json` and `translations/en.json` must be kept **identical**. The `strings.json` file is used by the HA frontend tooling; `translations/en.json` is the runtime file loaded by HA.

Drift between the two files is now caught automatically:
- **CI** (`lint` job): diffs the two files and fails if they differ.
- **Pre-push hook** (`.githooks/pre-push`): same diff runs before every `git push`.

If adding a new config flow step or error code, update **both** files before committing.

## Logging

Use `_LOGGER.debug` for normal operational events (alert received, auth success). Use `_LOGGER.warning` for recoverable problems (auth expired, re-authenticating). Use `_LOGGER.error` for setup failures. Never use `print()`.

## Testing with pytest-homeassistant-custom-component

The test suite currently uses plain `MagicMock` and `AsyncMock` fixtures and does not use the `hass` fixture from `pytest-homeassistant-custom-component`. See `TODO.md` — full HA integration tests (using the `hass` fixture and simulating config entry setup) are a planned improvement.

To use the `hass` fixture in future tests:
```python
# In conftest.py
pytest_plugins = "pytest_homeassistant_custom_component"

# In a test
async def test_setup(hass, mock_unifi_client):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
```
