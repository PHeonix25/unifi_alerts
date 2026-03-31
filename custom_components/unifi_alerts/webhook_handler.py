"""Webhook registration and dispatch for UniFi Alerts."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable

from aiohttp.web import Request
from homeassistant.components.webhook import (
    async_generate_url,
    async_register,
    async_unregister,
)
from homeassistant.core import HomeAssistant

from .const import (
    ALL_CATEGORIES,
    CONF_ENABLED_CATEGORIES,
    DOMAIN,
    webhook_id_for_category,
)
from .models import UniFiAlert

_LOGGER = logging.getLogger(__name__)


class WebhookManager:
    """Registers one HA webhook per alert category and routes inbound payloads."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict,
        push_callback: Callable[[str, UniFiAlert], None],
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._config = config
        self._push_callback = push_callback
        self._registered: list[str] = []

    def register_all(self) -> dict[str, str]:
        """Register webhooks for all enabled categories. Returns {category: url}."""
        enabled = self._config.get(CONF_ENABLED_CATEGORIES, ALL_CATEGORIES)
        urls: dict[str, str] = {}

        for category in ALL_CATEGORIES:
            if category not in enabled:
                continue
            webhook_id = webhook_id_for_category(category)
            # Wrap category in closure to avoid late-binding
            handler = self._make_handler(category)
            async_register(
                self._hass,
                DOMAIN,
                f"UniFi Alerts — {category}",
                webhook_id,
                handler,
                allowed_methods=["GET", "POST"],
                local_only=True,
            )
            self._registered.append(webhook_id)
            url = async_generate_url(self._hass, webhook_id)
            urls[category] = url
            _LOGGER.debug("Registered webhook for %s: %s", category, url)

        return urls

    def unregister_all(self) -> None:
        for webhook_id in self._registered:
            with contextlib.suppress(Exception):
                async_unregister(self._hass, webhook_id)
        self._registered.clear()

    def _make_handler(self, category: str):
        """Return an async webhook handler bound to a specific category."""

        async def handle_webhook(
            hass: HomeAssistant,
            webhook_id: str,
            request: Request,
        ) -> None:
            try:
                payload = await request.json()
            except Exception:  # noqa: BLE001
                # Fall back gracefully — UniFi can send GET with no body
                payload = {}

            _LOGGER.debug("Webhook received for category %s: %s", category, payload)
            alert = UniFiAlert.from_webhook_payload(category, payload)
            self._push_callback(category, alert)

        return handle_webhook
