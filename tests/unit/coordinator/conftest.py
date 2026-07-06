"""Shared helpers for UniFiAlertsCoordinator tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_CLEAR_TIMEOUT,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
)
from custom_components.unifi_alerts.coordinator import UniFiAlertsCoordinator
from custom_components.unifi_alerts.models import UniFiAlert


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
