"""Pytest configuration and shared fixtures for unifi_alerts tests."""

from __future__ import annotations

import contextlib
from collections.abc import Generator, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aiohttp.resolver import ThreadedResolver
from aioresponses import aioresponses

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
)
from custom_components.unifi_alerts.coordinator import UniFiAlertsCoordinator
from custom_components.unifi_alerts.models import UniFiAlert
from custom_components.unifi_alerts.unifi_client import UNIFI_OS_NETWORK_PREFIX, UniFiClient

UNIFI_CLIENT_BASE_URL = "https://192.168.1.1"
UNIFI_CLIENT_LOGIN_URL = f"{UNIFI_CLIENT_BASE_URL}/api/auth/login"
UNIFI_CLIENT_LOGOUT_URL = f"{UNIFI_CLIENT_BASE_URL}/api/auth/logout"

MOCK_CONFIG = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "password",
    CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
    CONF_VERIFY_SSL: False,
}


@pytest.fixture
def mock_unifi_client() -> Generator[MagicMock, None, None]:
    """Mock UniFiClient so tests never make real HTTP calls."""
    with patch("custom_components.unifi_alerts.unifi_client.UniFiClient") as mock_cls:
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.categorise_alarms = AsyncMock(return_value={})
        instance.probe_system_log_endpoint = AsyncMock(return_value=False)
        instance.close = AsyncMock()
        yield instance


@pytest.fixture
def sample_webhook_payload() -> dict[str, Any]:
    return {
        "key": "EVT_GW_WANTransition",
        "message": "WAN port went offline",
        "device_name": "UDM-Pro",
        "site_name": "default",
        "severity": "critical",
    }


@pytest.fixture
def sample_alarm_record() -> dict[str, Any]:
    return {
        "key": "EVT_IPS_ThreatDetected",
        "msg": "Threat detected from 1.2.3.4",
        "device_name": "UDM-Pro",
        "site_name": "default",
        "archived": False,
        "datetime": "2024-01-15T10:30:00",
    }


# ── shared plain-function helpers (importable from any test file) ─────────────


def make_hass() -> MagicMock:
    """Return a minimal hass mock wired up for config-entry setup/unload tests."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    return hass


def make_entry(
    data: dict | None = None,
    options: dict | None = None,
    entry_id: str = "entry-abc",
) -> MagicMock:
    """Return a mock config entry with sane defaults.

    The default ``data`` dict mirrors a fully-configured entry so tests that
    only care about ``entry_id`` can call ``make_entry()`` with no arguments.
    Tests that need specific field values can pass an explicit ``data`` dict.
    """
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = data or {
        CONF_CONTROLLER_URL: "https://192.168.1.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "password",
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
        CONF_VERIFY_SSL: True,
        "webhook_secret": "fake-secret",
    }
    entry.options = options or {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    return entry


@contextlib.contextmanager
def patch_setup_entry_collaborators(
    mock_client: MagicMock,
    mock_coordinator: MagicMock,
    mock_wm: MagicMock,
    *,
    dev_reg: MagicMock | None = None,
) -> Iterator[None]:
    """Patch the five external collaborators `async_setup_entry` depends on.

    Every `test_init.py` setup test needs the same five patches (session,
    client, coordinator, webhook manager, device registry) regardless of what
    it's actually testing; only the mocks' configured behaviour differs
    between tests. Pass `dev_reg` when a test needs to assert against the
    device-registry mock itself (e.g. `async_get_or_create` call args);
    otherwise a throwaway `MagicMock()` is used. Callers needing an additional
    patch (`_LOGGER`, `async_register_services`) or `pytest.raises` nest it
    around this context manager rather than this helper taking every
    possible extra.
    """
    with (
        patch("custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()),
        patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
        patch(
            "custom_components.unifi_alerts.UniFiAlertsCoordinator",
            return_value=mock_coordinator,
        ),
        patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
        patch("custom_components.unifi_alerts.dr.async_get", return_value=dev_reg or MagicMock()),
    ):
        yield


# ── shared coordinator-test helpers (importable from any test_coordinator_*.py) ──


def make_coordinator(hass: MagicMock | None = None, enabled: list[str] | None = None):
    """Build a UniFiAlertsCoordinator wired to mock hass/client with sane defaults."""
    if hass is None:
        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()  # discard the coroutine cleanly — no "never awaited" warning
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task

    client = MagicMock()
    client.categorise_alarms = AsyncMock(return_value={})
    client.probe_system_log_endpoint = AsyncMock(return_value=False)

    config = {
        CONF_ENABLED_CATEGORIES: enabled or ALL_CATEGORIES,
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 30,
    }
    coord = UniFiAlertsCoordinator(hass, client, config)
    # Persistence is exercised in dedicated tests; default to a mock Store so
    # push_alert's debounced async_delay_save is a harmless no-op here (the
    # real Store needs a live event loop the MagicMock hass does not provide).
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    coord._store.async_delay_save = MagicMock()
    return coord


def make_alert(category: str, message: str = "test alert", key: str = "") -> UniFiAlert:
    payload = {"message": message}
    if key:
        payload["key"] = key
    return UniFiAlert.from_webhook_payload(category, payload)


def make_coordinator_with_cancellable_task():
    """Coordinator whose scheduled clear task is a controllable MagicMock.

    For tests asserting on the task itself (`.cancel()` called, `.done()`
    state) rather than just discarding it — `make_coordinator()`'s default
    fake immediately closes the coroutine and returns a fresh throwaway
    MagicMock each call, which can't be asserted against afterward.
    """
    hass = MagicMock()
    task_mock = MagicMock()
    task_mock.done.return_value = False

    def _create_task(coro, **kwargs):
        coro.close()
        return task_mock

    hass.async_create_task = _create_task
    hass.async_create_background_task = _create_task
    coord = make_coordinator(hass=hass)
    coord.async_set_updated_data = MagicMock()
    return coord, task_mock


def make_hass_and_client():
    """Return a hass mock + client mock for coordinator tests."""
    hass = MagicMock()

    def _create_task(coro, **kwargs):
        coro.close()
        return MagicMock()

    hass.async_create_task = _create_task
    hass.async_create_background_task = _create_task

    client = MagicMock()
    client.probe_system_log_endpoint = AsyncMock(return_value=False)
    client.fetch_system_log_alarms = AsyncMock(return_value=[])
    client.categorise_alarms = AsyncMock(return_value={})
    return hass, client


def make_full_coordinator(hass: MagicMock, client: MagicMock) -> UniFiAlertsCoordinator:
    config = {
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 30,
    }
    coord = UniFiAlertsCoordinator(hass, client, config)
    coord.async_set_updated_data = MagicMock()
    return coord


# ── shared UniFiClient HTTP-test helpers (importable from any test_unifi_client_*.py) ──

# Sessions created by make_unifi_client() during the current test, closed by
# the _close_unifi_client_sessions autouse fixture below.
# pytest-homeassistant-custom-component asserts no lingering threads/timers
# survive a test, and an unclosed aiohttp.ClientSession schedules its own
# cleanup on the loop's default executor, which trips that check — so every
# session made here must be closed before the test ends.
_unifi_client_sessions: list[aiohttp.ClientSession] = []


def make_unifi_client(config: dict | None = None) -> UniFiClient:
    """Build a UniFiClient wired to a real aiohttp.ClientSession.

    aioresponses patches ClientSession._request, so no real socket is ever
    opened here; using the real session (instead of a MagicMock) means these
    tests exercise actual aiohttp request/response plumbing rather than a
    hand-built double of it. The session is tracked for teardown by
    _close_unifi_client_sessions.

    Uses a TCPConnector pinned to ThreadedResolver rather than aiohttp's
    aiodns-backed default. No DNS lookup ever actually happens (aioresponses
    intercepts before the connector runs), but constructing and then closing
    an AsyncResolver spins up pycares' global shutdown thread on first use —
    a daemon thread that outlives the test and trips the HA test harness's
    "no lingering threads" check. ThreadedResolver has no such side effect.
    """
    connector = aiohttp.TCPConnector(resolver=ThreadedResolver())
    session = aiohttp.ClientSession(connector=connector)
    _unifi_client_sessions.append(session)
    cfg = config or {
        "username": "admin",
        "password": "password",
        "verify_ssl": False,
    }
    return UniFiClient(session, UNIFI_CLIENT_BASE_URL, cfg)


@pytest.fixture(autouse=True)
async def _close_unifi_client_sessions() -> Generator[None, None, None]:
    """Close every aiohttp.ClientSession created via make_unifi_client() this test.

    Autouse and harmless for tests that never call make_unifi_client(): the
    list stays empty and the teardown loop is a no-op.
    """
    yield
    while _unifi_client_sessions:
        session = _unifi_client_sessions.pop()
        if not session.closed:
            await session.close()


def list_alarm_url(site: str = "default") -> str:
    return f"{UNIFI_CLIENT_BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/list/alarm"


def alarm_url(site: str = "default") -> str:
    return f"{UNIFI_CLIENT_BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/alarm"


def stat_alarm_url(site: str = "default") -> str:
    return f"{UNIFI_CLIENT_BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/stat/alarm"


def probe_url(site: str = "default") -> str:
    return f"{UNIFI_CLIENT_BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/count"


def system_log_url(site: str = "default") -> str:
    return f"{UNIFI_CLIENT_BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/all"


def find_calls(m: aioresponses, method: str, url: str) -> list:
    """Return the recorded request history for one (method, url) pair.

    Compares by string rather than by yarl.URL equality so this stays robust
    to aioresponses' internal key normalisation across versions.
    """
    calls: list = []
    for (recorded_method, recorded_url), call_list in m.requests.items():
        if recorded_method == method and str(recorded_url) == url:
            calls.extend(call_list)
    return calls


def total_calls(m: aioresponses) -> int:
    return sum(len(v) for v in m.requests.values())
