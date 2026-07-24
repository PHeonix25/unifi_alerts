"""Pytest configuration and shared fixtures for unifi_alerts tests."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Coroutine, Generator, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
)

MOCK_CONFIG = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    CONF_API_KEY: "test-api-key",
    CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
    CONF_VERIFY_SSL: False,
}


@pytest.fixture
def mock_unifi_client() -> Generator[MagicMock]:
    """Mock UniFiClient so tests never make real HTTP calls."""
    with patch("custom_components.unifi_alerts.unifi_client.UniFiClient") as mock_cls:
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value=None)
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


def run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion for a sync (typically hypothesis @given)
    test, without leaving the process-wide event loop unset afterward.

    `asyncio.run()` calls `asyncio.set_event_loop(None)` in its cleanup, and
    on Python 3.12+ that makes any later `asyncio.get_event_loop()` call
    raise `RuntimeError: There is no current event loop`. The older
    pytest-asyncio pulled in by the CI minimum-HA leg
    (`pytest-homeassistant-custom-component==0.13.317`) hits exactly that
    call when setting up the next `@pytest.mark.asyncio` test, which fails
    the entire remainder of the suite. Using our own loop here, and
    re-installing a fresh one afterward instead of clearing it, avoids that.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


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
        CONF_API_KEY: "test-api-key",
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
