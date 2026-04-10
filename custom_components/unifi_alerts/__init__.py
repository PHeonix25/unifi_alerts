"""The UniFi Alerts integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_VERIFY_SSL,
    DATA_COORDINATOR,
    DATA_UNREGISTER_WEBHOOKS,
    DATA_WEBHOOK_IDS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import UniFiAlertsCoordinator
from .unifi_client import UniFiClient
from .webhook_handler import WebhookManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.EVENT,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Alerts from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    if not verify_ssl:
        _LOGGER.warning(
            "SSL certificate verification is disabled for %s. "
            "This is a security risk — only use this for controllers with self-signed certificates.",
            entry.data.get("controller_url", "unknown"),
        )
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = UniFiClient(session, entry.data["controller_url"], dict(entry.data))

    try:
        await client.authenticate()
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed to authenticate to UniFi controller: %s", err)
        raise ConfigEntryNotReady(f"Could not connect to UniFi controller: {err}") from err

    coordinator = UniFiAlertsCoordinator(hass, client, dict(entry.data) | dict(entry.options))

    # Perform an initial poll so entities have data before first render
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Initial data fetch failed: {err}") from err

    # Register webhooks and capture the generated URLs for display
    webhook_manager = WebhookManager(
        hass,
        entry.entry_id,
        dict(entry.data) | dict(entry.options),
        coordinator.push_alert,
    )
    webhook_urls = webhook_manager.register_all()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_WEBHOOK_IDS: webhook_urls,
        DATA_UNREGISTER_WEBHOOKS: webhook_manager.unregister_all,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Re-register webhooks and reload options when the entry is updated
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("UniFi Alerts set up with %d webhook(s).", len(webhook_urls))
    _LOGGER.debug(
        "Webhook URLs: %s",
        ", ".join(f"{cat}={url}" for cat, url in webhook_urls.items()),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        coordinator = entry_data.get(DATA_COORDINATOR)
        if coordinator:
            await coordinator.async_shutdown()
        unregister = entry_data.get(DATA_UNREGISTER_WEBHOOKS)
        if unregister:
            unregister()
        client = entry_data.get("client")
        if client:
            await client.close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
