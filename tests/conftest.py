"""Pytest configuration and shared fixtures for unifi_alerts tests."""
from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    DOMAIN,
)


MOCK_CONFIG = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "password",
    CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
    "verify_ssl": False,
}


@pytest.fixture
def mock_unifi_client() -> Generator[MagicMock, None, None]:
    """Mock UniFiClient so tests never make real HTTP calls."""
    with patch(
        "custom_components.unifi_alerts.unifi_client.UniFiClient"
    ) as mock_cls:
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.categorise_alarms = AsyncMock(return_value={})
        instance.close = AsyncMock()
        yield instance


@pytest.fixture
def sample_webhook_payload() -> dict:
    return {
        "key": "EVT_GW_WANTransition",
        "message": "WAN port went offline",
        "device_name": "UDM-Pro",
        "site_name": "default",
        "severity": "critical",
    }


@pytest.fixture
def sample_alarm_record() -> dict:
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
