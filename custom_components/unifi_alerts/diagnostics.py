"""Diagnostics support for UniFi Alerts."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_PASSWORD,
    DATA_COORDINATOR,
    DATA_WEBHOOK_IDS,
    DOMAIN,
)

_LOGGER = __import__("logging").getLogger(__name__)

_TO_REDACT: set[str] = {CONF_PASSWORD, CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a UniFi Alerts config entry.

    Exposes webhook URLs (needed for UniFi Alarm Manager configuration)
    alongside redacted config and live coordinator state.
    """
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get(DATA_COORDINATOR)
    webhook_urls: dict[str, str] = entry_data.get(DATA_WEBHOOK_IDS, {})

    coordinator_info: dict[str, Any]
    if coordinator is not None:
        coordinator_info = {
            "any_alerting": coordinator.any_alerting,
            "rollup_alert_count": coordinator.rollup_alert_count,
            "rollup_open_count": coordinator.rollup_open_count,
        }
    else:
        coordinator_info = {}

    return {
        "config_entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "options": async_redact_data(dict(entry.options), _TO_REDACT),
        "webhook_urls": webhook_urls,
        "coordinator": coordinator_info,
    }
