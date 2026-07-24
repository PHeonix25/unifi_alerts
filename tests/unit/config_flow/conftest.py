"""Shared helpers and fixtures for config_flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.unifi_alerts.config_flow import UniFiAlertsConfigFlow, UniFiAlertsOptionsFlow
from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
)

_VALID_INPUT = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    CONF_API_KEY: "test-api-key",
}


def make_flow() -> UniFiAlertsConfigFlow:
    """Create a config flow instance with a minimal hass mock."""
    flow = UniFiAlertsConfigFlow()
    flow.hass = MagicMock()
    # No pre-existing entries by default — async_step_ssdp's serial-based
    # rediscovery lookup (_find_entry_by_serial) iterates this list. Tests
    # that need a match override it with a MagicMock(return_value=[...]).
    flow.hass.config_entries.async_entries = MagicMock(return_value=[])
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.context = {}
    # Patch unique ID helpers — real implementations need a running hass
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def make_session_mock() -> MagicMock:
    """Return a mock representing the HA-managed aiohttp session.

    `async_get_clientsession()` returns a long-lived session; the config flow
    no longer wraps it in an `async with`. UniFiClient is patched in these
    tests, so the session value is opaque — any MagicMock works.
    """
    return MagicMock()


def make_reauth_flow(entry_id: str = "entry-test") -> UniFiAlertsConfigFlow:
    """Create a flow wired up for reauth tests."""
    flow = UniFiAlertsConfigFlow()
    flow.context = {"entry_id": entry_id}

    mock_entry = MagicMock()
    mock_entry.entry_id = entry_id
    mock_entry.title = "UniFi Alerts (https://192.168.1.1)"
    mock_entry.data = {
        CONF_CONTROLLER_URL: "https://192.168.1.1",
        CONF_API_KEY: "old-api-key",
        CONF_WEBHOOK_SECRET: "secret",
    }

    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    flow.hass = hass
    flow._reauth_entry = mock_entry  # pre-set so reauth_confirm can access it
    return flow


def make_reconfigure_flow(entry_id: str = "entry-reconfigure") -> UniFiAlertsConfigFlow:
    """Create a config flow instance wired up for reconfigure tests.

    `_get_reconfigure_entry` is a real `ConfigFlow` base-class method that
    reads `self._reconfigure_entry_id` (derived from flow context set up by
    HA's flow manager) and calls `self.hass.config_entries.async_get_known_entry`.
    Driving that machinery for real needs a running hass, so it is stubbed
    directly here, matching how `make_reauth_flow` stubs the equivalent
    reauth lookup.
    """
    flow = UniFiAlertsConfigFlow()
    flow.context = {}

    mock_entry = MagicMock()
    mock_entry.entry_id = entry_id
    mock_entry.title = "UniFi Alerts (https://192.168.1.1)"
    mock_entry.data = {
        CONF_CONTROLLER_URL: "https://192.168.1.1",
        CONF_API_KEY: "old-api-key",
        CONF_VERIFY_SSL: True,
        CONF_WEBHOOK_SECRET: "fixed-secret",
    }

    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.config_entries.async_schedule_reload = MagicMock()
    flow.hass = hass
    flow._get_reconfigure_entry = MagicMock(return_value=mock_entry)  # type: ignore[method-assign]
    return flow


def make_options_flow(
    url: str = "https://192.168.1.1",
    enabled_categories: list[str] | None = None,
) -> UniFiAlertsOptionsFlow:
    """Return an options-flow instance wired with a minimal mock config entry and hass."""
    config_entry = MagicMock()
    config_entry.entry_id = "entry-options-creds"
    config_entry.data = {
        CONF_CONTROLLER_URL: url,
        CONF_API_KEY: "existing-api-key",
        CONF_VERIFY_SSL: True,
        CONF_WEBHOOK_SECRET: "fixed-secret",
        CONF_ENABLED_CATEGORIES: enabled_categories or ALL_CATEGORIES,
    }
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    flow.hass = hass
    return flow
