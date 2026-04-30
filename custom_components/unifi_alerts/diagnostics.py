"""Diagnostics support for UniFi Alerts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_WEBHOOK_SECRET,
)

_TO_REDACT: set[str] = {CONF_PASSWORD, CONF_API_KEY, CONF_USERNAME, CONF_WEBHOOK_SECRET}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a UniFi Alerts config entry.

    Exposes webhook URLs (needed for UniFi Alarm Manager configuration)
    alongside redacted config and live coordinator state.
    """
    runtime_data = getattr(entry, "runtime_data", None)
    coordinator = runtime_data.coordinator if runtime_data is not None else None
    # Strip token query params so secrets are not exposed in shared diagnostics output
    webhook_urls: dict[str, str] = {
        cat: url.split("?")[0]
        for cat, url in (runtime_data.webhook_urls if runtime_data is not None else {}).items()
    }

    coordinator_info: dict[str, Any]
    if coordinator is not None:
        categories: dict[str, dict[str, Any]] = {}
        for cat, state in coordinator.category_states.items():
            categories[cat] = {
                "enabled": state.enabled,
                "is_alerting": state.is_alerting,
                "open_count": state.open_count,
                "alert_count": state.alert_count,
                "last_cleared_at": (
                    state.last_cleared_at.isoformat() if state.last_cleared_at is not None else None
                ),
            }
        coordinator_info = {
            "any_alerting": coordinator.any_alerting,
            "rollup_alert_count": coordinator.rollup_alert_count,
            "rollup_open_count": coordinator.rollup_open_count,
            "categories": categories,
        }
    else:
        coordinator_info = {}

    return {
        "config_entry": async_redact_data(dict(entry.data), _TO_REDACT),
        "options": async_redact_data(dict(entry.options), _TO_REDACT),
        "webhook_urls": webhook_urls,
        "coordinator": coordinator_info,
    }
