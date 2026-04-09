# TESTING.md

## Running tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-homeassistant-custom-component aiohttp

# Run all tests
pytest tests/ -v

# Run a specific file
pytest tests/test_coordinator.py -v

# Run with coverage
pytest tests/ --cov=custom_components/unifi_alerts --cov-report=term-missing
```

## Linting and type checking

```bash
# Lint (errors only)
ruff check custom_components/

# Format check
ruff format --check custom_components/

# Auto-fix formatting
ruff format custom_components/

# Type check
mypy custom_components/unifi_alerts --ignore-missing-imports
```

CI runs all of these on every push via `.github/workflows/ci.yml`.

## What's tested

| File | Coverage |
|---|---|
| `test_models.py` | `UniFiAlert` construction from webhook and API payloads, field fallback, 255-char truncation; `CategoryState` init, apply_alert, clear |
| `test_coordinator.py` | Init; `push_alert`; rollup properties; `cancel_clear`; `async_shutdown`; polling path (no count increment, already-alerting guard); polling error paths (`InvalidAuthError` re-auth, `UpdateFailed`); `rollup_open_count`; `_auto_clear` state transition |
| `test_unifi_client.py` | `_classify`, `_network_path`, `_headers`, `_detect_unifi_os`, `_login_userpass`; `fetch_alarms` (success, archived filter, 401, ClientError, auto-auth); `categorise_alarms` (grouping, skip unknown, empty); `authenticate` (API key, fallback, no-fallback); `close` (userpass/OS logout, API key skip, unauthenticated skip) |
| `test_config_flow.py` | All config-flow steps; duplicate URL guard; options flow defaults; webhook URL fields; error value preservation |
| `test_diagnostics.py` | Redaction of sensitive fields; webhook URL exposure; coordinator state; missing-data handling |
| `test_webhook_handler.py` | `register_all` (category filter, token URL, _registered list); `unregister_all` (cleanup, exception suppression); `_make_handler` (valid token, missing token → 401, wrong token → 401, no secret, malformed JSON fallback, payload field mapping) |
| `test_init.py` | `async_setup_entry` (happy path, auth failure, first-refresh failure, SSL warning, platform forwarding); `async_unload_entry` (teardown order, failed-unload guard); `_async_update_listener` |
| `test_entities.py` | All entity property methods across binary_sensor, sensor, event, button; event-entity increment guard; button press / clear-all logic |

## What's NOT tested (see TODO.md)

- End-to-end integration tests with real `hass` fixture (webhook POST → binary sensor flips; auto-clear → sensor resets; options flow → entity update)
- Options flow form submission (only the init form display is tested, not saving changes)
- Config flow: categories step form submission, all validation edge values

## Test conventions

- Tests are synchronous where possible. Use `pytest.mark.asyncio` (or `asyncio_mode = auto` from `pytest.ini`) for async tests.
- Never make real HTTP calls. Mock `UniFiClient` at the class level using `unittest.mock.patch`.
- The `MOCK_CONFIG` fixture in `conftest.py` is the canonical set of config values. Use it as a base and override only what a specific test needs.
- Use `MagicMock()` for `hass` in coordinator tests — provide `hass.async_create_task` as a `MagicMock` that returns a mock task.

## Adding a test for a new category

When adding a new entry to `UNIFI_KEY_TO_CATEGORY`, add a corresponding parametrize case to `test_unifi_client.py::TestClassify::test_known_keys`:

```python
@pytest.mark.parametrize("key,expected", [
    ...
    ("EVT_NEW_SomeEvent", CATEGORY_NEW_THING),  # add here
])
def test_known_keys(self, key, expected):
    ...
```

## Adding an integration test (future)

Once the `hass` fixture is set up in `conftest.py`, integration tests follow this pattern:

```python
from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_setup_entry(hass, mock_unifi_client):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.unifi_alerts_network_device")
    assert state is not None
    assert state.state == "off"
```
