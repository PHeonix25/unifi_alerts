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
| `test_coordinator.py` | Init with full/partial enabled categories; `push_alert` state changes, count increment, disabled-category guard, listener notification, unknown-category warning; rollup properties (`any_alerting`, `rollup_alert_count`, `rollup_last_alert`) |
| `test_unifi_client.py` | `_classify` for all mapped key prefixes and unknown keys; `_network_path` for both controller types; `_headers` for both auth methods |

## What's NOT tested (see TODO.md)

- Config flow (requires `pytest-homeassistant-custom-component` `hass` fixture — not yet set up)
- `async_setup_entry` / `async_unload_entry`
- Webhook handler dispatch end-to-end
- Entity state updates in response to coordinator changes
- Auto-clear timer scheduling and execution
- `UniFiClient.authenticate()` with mocked HTTP responses
- `UniFiClient.fetch_alarms()` with mocked HTTP responses
- Options flow
- Button press → coordinator clear → entity state update

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
