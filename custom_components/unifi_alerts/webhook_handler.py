"""Webhook registration and dispatch for UniFi Alerts."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable

from aiohttp.web import Request, Response
from homeassistant.components.webhook import (
    async_generate_url,
    async_register,
    async_unregister,
)
from homeassistant.core import HomeAssistant

from .const import (
    ALL_CATEGORIES,
    CONF_ENABLED_CATEGORIES,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    WEBHOOK_MAX_BODY_BYTES,
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
        secret: str = self._config.get(CONF_WEBHOOK_SECRET, "")
        urls: dict[str, str] = {}

        for category in ALL_CATEGORIES:
            if category not in enabled:
                continue
            webhook_id = webhook_id_for_category(category)
            # Wrap category in closure to avoid late-binding
            handler = self._make_handler(category, secret)
            async_register(
                self._hass,
                DOMAIN,
                f"UniFi Alerts — {category}",
                webhook_id,
                handler,
                allowed_methods=["POST"],
                local_only=True,
            )
            self._registered.append(webhook_id)
            base_url = async_generate_url(self._hass, webhook_id)
            urls[category] = f"{base_url}?token={secret}" if secret else base_url
            _LOGGER.debug("Registered webhook for %s", category)

        return urls

    def unregister_all(self) -> None:
        for webhook_id in self._registered:
            with contextlib.suppress(Exception):
                async_unregister(self._hass, webhook_id)
        self._registered.clear()

    def _make_handler(self, category: str, secret: str):
        """Return an async webhook handler bound to a specific category."""

        async def handle_webhook(
            hass: HomeAssistant,
            webhook_id: str,
            request: Request,
        ) -> Response | None:
            if secret and request.query.get("token") != secret:
                _LOGGER.warning(
                    "Webhook request for category %s rejected: missing or invalid token",
                    category,
                )
                return Response(status=401)

            try:
                raw = await request.content.read(WEBHOOK_MAX_BODY_BYTES + 1)
                if len(raw) > WEBHOOK_MAX_BODY_BYTES:
                    _LOGGER.warning(
                        "Webhook body for category %s exceeds %d bytes, rejecting",
                        category,
                        WEBHOOK_MAX_BODY_BYTES,
                    )
                    return Response(status=413)
                payload = json.loads(raw.decode()) if raw else {}
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                payload = {}

            _LOGGER.debug("Webhook received for category %s: %s", category, payload)
            alert = UniFiAlert.from_webhook_payload(category, payload)
            self._push_callback(category, alert)
            return None

        return handle_webhook
