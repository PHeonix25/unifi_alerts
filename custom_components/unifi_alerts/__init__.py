"""The UniFi Alerts integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DATA_COORDINATOR,
    DATA_UNREGISTER_WEBHOOKS,
    DATA_WEBHOOK_IDS,
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

    session = async_get_clientsession(hass, verify_ssl=entry.data.get("verify_ssl", False))
    client = UniFiClient(session, entry.data["controller_url"], dict(entry.data))

    try:
        await client.authenticate()
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed to authenticate to UniFi controller: %s", err)
        return False

    coordinator = UniFiAlertsCoordinator(hass, client, dict(entry.data) | dict(entry.options))

    # Perform an initial poll so entities have data before first render
    await coordinator.async_config_entry_first_refresh()

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

    _LOGGER.info(
        "UniFi Alerts set up. Webhook URLs: %s",
        ", ".join(f"{cat}={url}" for cat, url in webhook_urls.items()),
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
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
