# TESTING.md

## Setup

Install all dev dependencies into the project venv:

```bash
make setup
# equivalent to:
# python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

`requirements-dev.txt` is the single source of truth for dev dependencies — it is also used by both CI jobs, so local and CI environments are identical.

---

## Running checks

```bash
make check      # default target — runs everything below in sequence
make lint       # ruff lint + format check
make typecheck  # mypy
make validate   # HACS manifest pre-flight (scripts/validate_hacs.py)
make test       # pytest
```

Individual commands if you prefer to skip the Makefile:

```bash
# All tests (unit + integration)
.venv/bin/pytest tests/ -v
.venv/bin/pytest tests/ --cov=custom_components/unifi_alerts --cov-report=term-missing

# Unit tests only
.venv/bin/pytest tests/unit/ -v

# Integration tests only
.venv/bin/pytest tests/integration/ -v -m integration

# Single file
.venv/bin/pytest tests/unit/test_coordinator.py -v

# Lint
.venv/bin/ruff check custom_components/
.venv/bin/ruff format --check custom_components/
.venv/bin/ruff format custom_components/         # auto-fix formatting

# Type check
.venv/bin/mypy custom_components/unifi_alerts --ignore-missing-imports

# HACS manifest pre-flight
python3 scripts/validate_hacs.py

# Translation drift check
diff custom_components/unifi_alerts/strings.json \
     custom_components/unifi_alerts/translations/en.json
```

---

## Pre-push hook

`.githooks/pre-push` runs the full `make check` suite automatically before every `git push`. Install it once per clone:

```bash
git config core.hooksPath .githooks
```

If the hook blocks your push, fix the reported issue — do not use `git push --no-verify` to bypass it.

---

## Test directory structure

Tests are split into two peer subdirectories:

```
tests/
  unit/                    # plain-mock unit tests — no real HA instance
    conftest.py            # MOCK_CONFIG, make_hass(), make_entry(), shared fixtures
    test_coordinator.py
    test_config_flow.py
    test_diagnostics.py
    test_entities.py
    test_init.py
    test_models.py
    test_unifi_client.py
    test_webhook_handler.py
  integration/             # full HA lifecycle tests using hass fixture
    __init__.py            # enables relative imports within the package
    conftest.py            # entry fixture, mock_unifi_client, get_coordinator()
    test_auto_clear.py     # auto-clear timeout resets binary sensors
    test_lifecycle.py      # entity creation, options flow, coordinator wiring
    test_webhook.py        # webhook HTTP dispatch end-to-end
```

`tests/unit/` has **no** `__init__.py` so pytest adds it to `sys.path`, enabling bare `from conftest import` in unit test files.

`tests/integration/` has `__init__.py` enabling relative imports (`from .conftest import ...`).

---

## Unit tests

Unit tests in `tests/unit/` use `MagicMock` / `AsyncMock` for the HA instance and the UniFi client. They never make real HTTP calls and do not require a running event loop beyond what pytest-asyncio provides.

Key conventions:
- Never make real HTTP calls. Mock `UniFiClient` at the class level using `unittest.mock.patch`.
- The `MOCK_CONFIG` dict in `tests/unit/conftest.py` is the canonical config baseline.
- `make_hass()` and `make_entry()` in `tests/unit/conftest.py` are helpers for setup/unload tests.
- Use `pytest.mark.asyncio` (or the `asyncio_mode = auto` setting in `pytest.ini`) for async tests.
- Mock `hass.async_create_task` AND `hass.async_create_background_task` together wherever the coordinator's `_schedule_clear` path is exercised.

### What's tested

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

---

## Integration tests

Integration tests in `tests/integration/` use a real `HomeAssistant` instance provided by the `hass` fixture from `pytest_homeassistant_custom_component`. All `UniFiClient` HTTP calls are still mocked — the tests verify HA lifecycle behaviour without hitting a real controller.

Mark all integration tests with `@pytest.mark.integration`.

### Fixtures

| Fixture | Scope | Purpose |
|---|---|---|
| `hass` | function | Real `HomeAssistant` instance (from PHCC) |
| `hass_client` | function | aiohttp test client bound to `hass.http.app` |
| `mock_unifi_client` | function | Patches `UniFiClient` so no HTTP calls escape |
| `entry` | function | Sets up the config entry + HTTP/webhook infra; unloads on teardown |
| `_prime_pycares_shutdown_thread` | session | Warms up aiodns/pycares resolver so `verify_cleanup` doesn't flag Thread-1 as new |

### Key implementation notes

- **`hass.async_create_background_task`** is used for auto-clear tasks so they do NOT block `hass.async_block_till_done()`. Background tasks are cancelled on entry unload via `coordinator.async_shutdown()`.
- **pycares Thread-1** (`_run_safe_shutdown_loop`): aiohttp DNS usage can start this daemon thread on first use. The session-scoped `_prime_pycares_shutdown_thread` fixture primes that path by constructing `aiodns.DNSResolver(...)` before tests so the thread is in `verify_cleanup`'s baseline; if `aiodns` is not installed, this is a no-op.
- **HTTP infrastructure**: The `entry` fixture calls `async_setup_component(hass, "webhook", {})` and sets `internal_url` before setting up the config entry. Tests that don't use the `entry` fixture but need `hass_client` must set this up themselves (see `test_no_secret_config_accepts_post_without_token`).
- **Auto-clear in tests**: Patch `custom_components.unifi_alerts.coordinator.asyncio.sleep` with `AsyncMock()` to make the delay instant, then call `await hass.async_block_till_done(wait_background_tasks=True)` so HA drains the background task queue. Follow with a second `await hass.async_block_till_done()` to flush any HA state-write callbacks triggered by the coordinator update.

### What's tested

| File | Scenarios |
|---|---|
| `test_lifecycle.py` | Entity creation for all categories; rollup sensor; count sensors; clear buttons; options flow disabling a category makes its sensor unavailable |
| `test_auto_clear.py` | Push alert → sensor ON; auto-clear fires → sensor OFF; rollup also resets; push without clear keeps sensor ON |
| `test_webhook.py` | Valid POST + correct token → sensor ON; missing token → 401; wrong token → 401; GET → no dispatch; no-secret config → POST accepted without token |

---

## Adding a test for a new event key

When adding a new entry to `UNIFI_KEY_TO_CATEGORY`, add a corresponding parametrize case to `tests/unit/test_unifi_client.py::TestClassify::test_known_keys`:

```python
@pytest.mark.parametrize("key,expected", [
    ...
    ("EVT_NEW_SomeEvent", CATEGORY_NEW_THING),  # add here
])
def test_known_keys(self, key, expected):
    ...
```

---

## Adding a new integration test

Integration tests follow this pattern:

```python
from .conftest import ENTRY_ID, entity_id_for, get_coordinator

@pytest.mark.integration
async def test_something(hass, entry, hass_client):
    uid = f"{ENTRY_ID}_network_wan_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    coordinator = get_coordinator(hass, entry)
    coordinator.push_alert("network_wan", make_alert())
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "on"
```

Key points:
- The `entry` fixture handles HTTP/webhook setup and entry teardown automatically.
- Call `await hass.async_block_till_done()` after any state change to let HA propagate updates.
- Use `entity_id_for(hass, platform, unique_id)` to resolve entity IDs from the registry.
- Unique IDs follow the pattern `{entry_id}_{category}_binary`, `{entry_id}_{category}_message`, etc.
