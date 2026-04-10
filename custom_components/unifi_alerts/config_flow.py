"""Config flow for UniFi Alerts."""

from __future__ import annotations

import logging
import secrets
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.components.webhook import async_generate_url
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from yarl import URL

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
    CONF_WEBHOOK_SECRET,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    webhook_id_for_category,
)
from .unifi_client import CannotConnectError, InvalidAuthError, UniFiClient

_LOGGER = logging.getLogger(__name__)


class UniFiAlertsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow shown in Settings → Integrations."""

    VERSION = 1

    def __init__(self) -> None:
        self._controller_url: str = ""
        self._detected_auth_method: str | None = None
        self._credentials: dict[str, Any] = {}
        self._entry_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: controller URL + credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_CONTROLLER_URL].rstrip("/")
            if URL(url).scheme not in ("http", "https"):
                errors[CONF_CONTROLLER_URL] = "invalid_url_scheme"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                async with aiohttp.ClientSession() as session:
                    client = UniFiClient(session, url, user_input)
                    try:
                        auth_method = await client.authenticate()
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
                        self._credentials = {
                            **user_input,
                            CONF_WEBHOOK_SECRET: secrets.token_urlsafe(32),
                        }
                        return await self.async_step_categories()

        _password_selector = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
        _api_key_selector = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

        if user_input is not None:
            # Rebuild schema with submitted values as defaults so the user
            # doesn't have to re-enter everything on a validation error.
            # Password/API key fields deliberately omit `default=` so HA does
            # not pre-fill sensitive values — the user must re-enter them.
            # Username uses a conditional default: omit entirely when empty so
            # HA treats the field as truly blank rather than pre-filled.
            _username = user_input.get(CONF_USERNAME, "")
            schema = vol.Schema(
                {
                    vol.Required(CONF_CONTROLLER_URL, default=user_input[CONF_CONTROLLER_URL]): str,
                    vol.Optional(
                        CONF_USERNAME, **({"default": _username} if _username else {})
                    ): str,
                    vol.Optional(CONF_PASSWORD): _password_selector,
                    vol.Optional(CONF_API_KEY): _api_key_selector,
                    vol.Optional(
                        CONF_VERIFY_SSL,
                        default=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    ): bool,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_CONTROLLER_URL, default="https://192.168.1.1"): str,
                    vol.Optional(CONF_USERNAME): str,
                    vol.Optional(CONF_PASSWORD): _password_selector,
                    vol.Optional(CONF_API_KEY): _api_key_selector,
                    vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
                }
            )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"docs_url": "https://github.com/PHeonix25/unifi_alerts"},
        )

    async def async_step_categories(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: choose which alert categories to enable."""
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = [cat for cat in ALL_CATEGORIES if user_input.get(f"cat_{cat}", False)]
            if not enabled:
                errors["base"] = "at_least_one_category"
            else:
                self._entry_data = {
                    **self._credentials,
                    CONF_ENABLED_CATEGORIES: enabled,
                    CONF_POLL_INTERVAL: user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    CONF_CLEAR_TIMEOUT: user_input.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT),
                    CONF_AUTH_METHOD: self._detected_auth_method,
                }
                return await self.async_step_finish()

        # Build a schema with one boolean per category
        fields: dict = {}
        # Default noisy client/device categories to OFF; exceptional events ON
        _chatty = {"network_device", "network_client"}
        for cat in ALL_CATEGORIES:
            fields[vol.Optional(f"cat_{cat}", default=(cat not in _chatty))] = bool

        fields[vol.Optional(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL)] = vol.All(
            int, vol.Range(min=10, max=3600)
        )
        fields[vol.Optional(CONF_CLEAR_TIMEOUT, default=DEFAULT_CLEAR_TIMEOUT)] = vol.All(
            int, vol.Range(min=1, max=1440)
        )

        schema = vol.Schema(fields)
        return self.async_show_form(
            step_id="categories",
            data_schema=schema,
            errors=errors,
            description_placeholders={cat: CATEGORY_LABELS[cat] for cat in ALL_CATEGORIES},
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3: display webhook URLs, then create the entry on submit."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"UniFi Alerts ({self._controller_url})",
                data=self._entry_data,
            )

        enabled: list[str] = self._entry_data.get(CONF_ENABLED_CATEGORIES, ALL_CATEGORIES)
        secret: str = self._entry_data.get(CONF_WEBHOOK_SECRET, "")
        fields: dict = {}
        for cat in ALL_CATEGORIES:
            if cat in enabled:
                url = (
                    f"{async_generate_url(self.hass, webhook_id_for_category(cat))}?token={secret}"
                )
                fields[vol.Optional(f"webhook_url_{cat}", default=url)] = str
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema(fields),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return UniFiAlertsOptionsFlow(config_entry)


class UniFiAlertsOptionsFlow(OptionsFlow):
    """Handle re-configuration (Settings → Integrations → Configure)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            enabled = [cat for cat in ALL_CATEGORIES if user_input.get(f"cat_{cat}", False)]
            if not enabled:
                errors["base"] = "at_least_one_category"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_ENABLED_CATEGORIES: enabled,
                        CONF_POLL_INTERVAL: user_input.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                        CONF_CLEAR_TIMEOUT: user_input.get(
                            CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT
                        ),
                    },
                )

        current_enabled: list[str] = self._config_entry.options.get(
            CONF_ENABLED_CATEGORIES,
            self._config_entry.data.get(CONF_ENABLED_CATEGORIES, ALL_CATEGORIES),
        )
        current_poll: int = self._config_entry.options.get(
            CONF_POLL_INTERVAL,
            self._config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )
        current_clear: int = self._config_entry.options.get(
            CONF_CLEAR_TIMEOUT,
            self._config_entry.data.get(CONF_CLEAR_TIMEOUT, DEFAULT_CLEAR_TIMEOUT),
        )

        fields: dict = {}
        for cat in ALL_CATEGORIES:
            fields[vol.Optional(f"cat_{cat}", default=(cat in current_enabled))] = bool
        fields[vol.Optional(CONF_POLL_INTERVAL, default=current_poll)] = vol.All(
            int, vol.Range(min=10, max=3600)
        )
        fields[vol.Optional(CONF_CLEAR_TIMEOUT, default=current_clear)] = vol.All(
            int, vol.Range(min=1, max=1440)
        )

        secret: str = self._config_entry.data.get(CONF_WEBHOOK_SECRET, "")
        for cat in ALL_CATEGORIES:
            url = f"{async_generate_url(self.hass, webhook_id_for_category(cat))}?token={secret}"
            fields[vol.Optional(f"webhook_url_{cat}", default=url)] = str
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
            errors=errors,
        )
