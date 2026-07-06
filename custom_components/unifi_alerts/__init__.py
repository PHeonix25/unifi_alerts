"""The UniFi Alerts integration."""

from __future__ import annotations

import logging
import secrets
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CONTROLLER_URL,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    ISSUE_ID_AUTH_FAILED,
    ISSUE_ID_PERSIST_FAILED,
    ISSUE_ID_WEBHOOK_SECRET_ROTATED,
    ISSUE_ID_WEBHOOK_URLS_CHANGED,
    STORAGE_VERSION_WATERMARKS,
)
from .coordinator import UniFiAlertsCoordinator
from .models import RuntimeData, UniFiClientConfig
from .services import async_register_services, async_unregister_services
from .unifi_auth import CannotConnectError, InvalidAuthError
from .unifi_client import UniFiClient
from .webhook_handler import WebhookManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.EVENT,
    Platform.BUTTON,
]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry versions to current."""
    if config_entry.version == 1:
        new_data = {k: v for k, v in config_entry.data.items() if k != "is_unifi_os"}
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        _LOGGER.info("Migrated config entry %s from version 1 to 2", config_entry.entry_id)

    if config_entry.version == 2:
        new_data = dict(config_entry.data)
        changed = False
        suffix_backfilled = False
        if not new_data.get("webhook_secret"):
            new_data["webhook_secret"] = secrets.token_urlsafe(32)
            changed = True
        if not new_data.get("webhook_id_suffix"):
            new_data["webhook_id_suffix"] = secrets.token_hex(4)
            changed = True
            suffix_backfilled = True
        if changed:
            hass.config_entries.async_update_entry(config_entry, data=new_data, version=3)
            _LOGGER.debug(
                "Migrated config entry %s to version 3: backfilled webhook secret/suffix. "
                "Re-paste webhook URLs from Settings > Devices & Services > UniFi Alerts > Configure.",
                config_entry.entry_id,
            )
            if suffix_backfilled:
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"{ISSUE_ID_WEBHOOK_URLS_CHANGED}_{config_entry.entry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=ISSUE_ID_WEBHOOK_URLS_CHANGED,
                    translation_placeholders={"name": config_entry.title},
                )
        else:
            hass.config_entries.async_update_entry(config_entry, version=3)
        return True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UniFi Alerts from a config entry."""
    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    if not verify_ssl:
        _LOGGER.warning(
            "SSL certificate verification is disabled for %s. "
            "This is a security risk — only use this for controllers with self-signed certificates.",
            entry.data.get("controller_url", "unknown"),
        )
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    # HA's ConfigEntry.data is Mapping[str, Any]; cast at the boundary so
    # internal call sites are typed via UniFiClientConfig.
    client = UniFiClient(
        session,
        entry.data["controller_url"],
        cast(UniFiClientConfig, dict(entry.data)),
    )

    try:
        await client.authenticate()
    except InvalidAuthError as err:
        _LOGGER.error("Authentication failed for UniFi controller: %s", type(err).__name__)
        raise ConfigEntryAuthFailed(
            f"Invalid credentials for UniFi controller: {type(err).__name__}"
        ) from err
    except CannotConnectError as err:
        _LOGGER.error("Failed to authenticate to UniFi controller: %s", type(err).__name__)
        raise ConfigEntryNotReady(
            f"Could not connect to UniFi controller: {type(err).__name__}"
        ) from err

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
        hass,
        client,
        cast(UniFiClientConfig, dict(entry.data) | dict(entry.options)),
        entry.entry_id,
    )

    # Restore persisted acknowledgement watermarks before first poll so that
    # open_count is filtered correctly from the very first data fetch.
    await coordinator.async_restore_watermarks()

    # Perform an initial poll so entities have data before first render.
    # async_config_entry_first_refresh() (HA core) already raises the
    # semantically correct exception on failure — ConfigEntryNotReady for a
    # connectivity/UpdateFailed outcome, or ConfigEntryAuthFailed if the
    # coordinator's own re-auth attempt failed (see coordinator._async_update_data).
    # A blanket except here would misclassify a ConfigEntryAuthFailed as
    # ConfigEntryNotReady, silently suppressing HA's reauth-repair flow.
    await coordinator.async_config_entry_first_refresh()

    # Register webhooks and capture the generated URLs for display
    webhook_manager = WebhookManager(
        hass,
        entry.entry_id,
        cast(UniFiClientConfig, dict(entry.data) | dict(entry.options)),
        coordinator.push_alert,
    )
    webhook_urls = webhook_manager.register_all()

    entry.runtime_data = RuntimeData(
        coordinator=coordinator,
        webhook_urls=webhook_urls,
        unregister_webhooks=webhook_manager.unregister_all,
        client=client,
    )

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
    token_marker = "?token="  # noqa: S105  # URL query marker for redaction, not a secret
    idx = url.find(token_marker)
    if idx == -1:
        return url
    return f"{url[:idx]}?token=***"


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime_data: RuntimeData = entry.runtime_data
        await runtime_data.coordinator.async_shutdown()
        runtime_data.unregister_webhooks()
        await runtime_data.client.close()
        # Unregister domain-level services only when the last entry is gone
        remaining = [
            e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
        ]
        if not remaining:
            async_unregister_services(hass)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up persisted storage and repair issues after a config entry is removed.

    Fires after async_unload_entry, once HA has decided the entry itself is
    gone for good (not just reloading). Without this, the per-entry watermark
    Store file and any open repair issues keyed to entry.entry_id would remain
    orphaned forever, since nothing else ever reads or clears them again.
    """
    store: Store[dict[str, Any]] = Store(
        hass, STORAGE_VERSION_WATERMARKS, f"{DOMAIN}_watermarks_{entry.entry_id}"
    )
    await store.async_remove()

    for issue_id_base in (
        ISSUE_ID_AUTH_FAILED,
        ISSUE_ID_WEBHOOK_SECRET_ROTATED,
        ISSUE_ID_WEBHOOK_URLS_CHANGED,
        ISSUE_ID_PERSIST_FAILED,
    ):
        ir.async_delete_issue(hass, DOMAIN, f"{issue_id_base}_{entry.entry_id}")

    _LOGGER.debug("Cleaned up storage and repair issues for removed entry %s", entry.entry_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
