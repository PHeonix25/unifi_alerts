"""The UniFi Alerts integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    CONF_CONTROLLER_URL,
    CONF_VERIFY_SSL,
    DATA_COORDINATOR,
    DATA_UNREGISTER_WEBHOOKS,
    DATA_WEBHOOK_IDS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import UniFiAlertsCoordinator
from .services import async_register_services, async_unregister_services
from .unifi_client import InvalidAuthError, UniFiClient
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
    except InvalidAuthError as err:
        _LOGGER.error("Authentication failed for UniFi controller: %s", err)
        raise ConfigEntryAuthFailed(f"Invalid credentials for UniFi controller: {err}") from err
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed to authenticate to UniFi controller: %s", err)
        raise ConfigEntryNotReady(f"Could not connect to UniFi controller: {err}") from err

    # Proactively register the hub device so it appears in HA's Services section
    # immediately after setup — before any entity is registered.
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="UniFi Alerts",
        manufacturer="Ubiquiti",
        model="UniFi Network Controller",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=entry.data.get(CONF_CONTROLLER_URL),
    )

    coordinator = UniFiAlertsCoordinator(
        hass, client, dict(entry.data) | dict(entry.options), entry.entry_id
    )

    # Restore persisted acknowledgement watermarks before first poll so that
    # open_count is filtered correctly from the very first data fetch.
    await coordinator.async_restore_watermarks()

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

    # Register domain services (idempotent — safe for multiple entries)
    async_register_services(hass)

    # Re-register webhooks and reload options when the entry is updated
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("UniFi Alerts set up. Registered %d webhook(s).", len(webhook_urls))
    if _LOGGER.isEnabledFor(logging.DEBUG):
        # Redact ?token=<secret> before logging — DEBUG logs commonly end up
        # in GitHub issues, and the token is the only thing protecting the
        # webhook endpoint from local-network forgery.
        _LOGGER.debug(
            "UniFi Alerts webhook URLs: %s",
            ", ".join(f"{cat}={_redact_webhook_token(url)}" for cat, url in webhook_urls.items()),
        )
    return True


def _redact_webhook_token(url: str) -> str:
    """Strip ``?token=<secret>`` from a webhook URL for safe DEBUG logging."""
    token_marker = "?token="
    idx = url.find(token_marker)
    if idx == -1:
        return url
    return f"{url[:idx]}?token=***"


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
        # Unregister domain-level services only when the last entry is gone
        if not hass.data.get(DOMAIN):
            async_unregister_services(hass)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
