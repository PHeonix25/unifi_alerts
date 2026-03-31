"""Config flow for UniFi Alerts."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    ALL_CATEGORIES,
    CATEGORY_LABELS,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .unifi_client import CannotConnectError, InvalidAuthError, UniFiClient

_LOGGER = logging.getLogger(__name__)


class UniFiAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow shown in Settings → Integrations."""

    VERSION = 1

    def __init__(self) -> None:
        self._controller_url: str = ""
        self._detected_auth_method: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: controller URL + credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_CONTROLLER_URL].rstrip("/")
            session = async_create_clientsession(self.hass)
            client = UniFiClient(session, url, user_input)
            try:
                auth_method = await client.authenticate()
                await client.close()
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during auth")
                errors["base"] = "unknown"
            else:
                self._controller_url = url
                self._detected_auth_method = auth_method
                # Store credentials so we can pass them to step 2
                self.context["credentials"] = user_input
                return await self.async_step_categories()

        schema = vol.Schema(
            {
                vol.Required(CONF_CONTROLLER_URL, default="https://192.168.1.1"): str,
                vol.Optional(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Optional(CONF_API_KEY): str,
                vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/PHeonix25/unifi_alerts"
            },
        )

    async def async_step_categories(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: choose which alert categories to enable."""
        if user_input is not None:
            enabled = [
                cat for cat in ALL_CATEGORIES
                if user_input.get(f"cat_{cat}", False)
            ]
            credentials: dict = self.context.get("credentials", {})
            data = {
                **credentials,
                CONF_ENABLED_CATEGORIES: enabled,
                CONF_POLL_INTERVAL: user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                CONF_CLEAR_TIMEOUT: user_input.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT),
                CONF_AUTH_METHOD: self._detected_auth_method,
            }
            return self.async_create_entry(
                title=f"UniFi Alerts ({self._controller_url})",
                data=data,
            )

        # Build a schema with one boolean per category
        fields: dict = {}
        for cat in ALL_CATEGORIES:
            fields[vol.Optional(f"cat_{cat}", default=True)] = bool

        fields[vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL)] = (
            vol.All(int, vol.Range(min=10, max=3600))
        )
        fields[vol.Optional(CONF_CLEAR_TIMEOUT, default=DEFAULT_CLEAR_TIMEOUT)] = (
            vol.All(int, vol.Range(min=1, max=1440))
        )

        schema = vol.Schema(fields)
        return self.async_show_form(
            step_id="categories",
            data_schema=schema,
            description_placeholders={
                cat: CATEGORY_LABELS[cat] for cat in ALL_CATEGORIES
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return UniFiAlertsOptionsFlow(config_entry)


class UniFiAlertsOptionsFlow(OptionsFlow):
    """Handle re-configuration (Settings → Integrations → Configure)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = [
                cat for cat in ALL_CATEGORIES
                if user_input.get(f"cat_{cat}", False)
            ]
            return self.async_create_entry(
                title="",
                data={
                    CONF_ENABLED_CATEGORIES: enabled,
                    CONF_POLL_INTERVAL: user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    CONF_CLEAR_TIMEOUT: user_input.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT),
                },
            )

        current_enabled: list[str] = self._config_entry.data.get(
            CONF_ENABLED_CATEGORIES, ALL_CATEGORIES
        )
        current_poll: int = self._config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        current_clear: int = self._config_entry.data.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT)

        fields: dict = {}
        for cat in ALL_CATEGORIES:
            fields[vol.Optional(f"cat_{cat}", default=(cat in current_enabled))] = bool
        fields[vol.Optional(CONF_POLL_INTERVAL, default=current_poll)] = (
            vol.All(int, vol.Range(min=10, max=3600))
        )
        fields[vol.Optional(CONF_CLEAR_TIMEOUT, default=current_clear)] = (
            vol.All(int, vol.Range(min=1, max=1440))
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
            errors=errors,
        )
