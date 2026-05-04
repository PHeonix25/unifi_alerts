"""Webhook registration and dispatch for UniFi Alerts."""

from __future__ import annotations

import contextlib
import hmac
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
    CONF_WEBHOOK_ID_SUFFIX,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    WEBHOOK_MAX_BODY_BYTES,
    webhook_id_for_category,
)
from .models import UniFiAlert

_LOGGER = logging.getLogger(__name__)

# Fields safe to log at DEBUG. Avoids leaking arbitrary controller payload
# fields (which may include client MACs, IPs, or future firmware additions).
_SAFE_DEBUG_FIELDS: tuple[str, ...] = (
    "category",
    "alert_key",
    "key",
    "severity",
    "device_name",
)


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
        """Register webhooks for all enabled categories. Returns {category: url}.

        Each registration is wrapped in its own try/except so a single failure
        does not abort the rest of the loop, and ``self._registered`` is only
        appended to after a successful ``async_register`` call so
        ``unregister_all()`` never tries to unregister something that never
        registered.
        """
        enabled = self._config.get(CONF_ENABLED_CATEGORIES, ALL_CATEGORIES)
        secret: str = self._config.get(CONF_WEBHOOK_SECRET, "")
        suffix: str = self._config.get(CONF_WEBHOOK_ID_SUFFIX, "")
        urls: dict[str, str] = {}

        for category in ALL_CATEGORIES:
            if category not in enabled:
                continue
            webhook_id = webhook_id_for_category(category, suffix)
            handler = self._make_handler(category, secret)
            try:
                async_register(
                    self._hass,
                    DOMAIN,
                    f"UniFi Alerts — {category}",
                    webhook_id,
                    handler,
                    allowed_methods=["POST"],
                    local_only=True,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to register webhook for category %s (%s): %s",
                    category,
                    type(err).__name__,
                    err,
                )
                continue
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
            if secret:
                provided = request.query.get("token", "")
                # Use hmac.compare_digest to avoid leaking the secret via a
                # timing side-channel — `==` / `!=` exit early on the first
                # mismatching byte, which lets a remote attacker recover the
                # secret byte-by-byte.
                if not hmac.compare_digest(provided, secret):
                    _LOGGER.warning(
                        "Webhook request for category %s rejected: missing or invalid token",
                        category,
                    )
                    return Response(status=401)

            raw = b""
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
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as err:
                # Decode failures previously fell through silently to an empty
                # payload, hiding misconfigured controllers and truncated
                # bodies. Log enough to diagnose without dumping the full body.
                preview = raw[:80].decode("utf-8", errors="replace") if raw else ""
                _LOGGER.warning(
                    "Webhook body decode failed for category %s (%s): %r",
                    category,
                    type(err).__name__,
                    preview,
                )
                payload = {}

            if _LOGGER.isEnabledFor(logging.DEBUG):
                # Narrow the payload to known-safe fields before logging so
                # arbitrary controller fields (client MACs, IPs, future
                # firmware additions) never end up in user-shared logs.
                safe = {k: payload.get(k) for k in _SAFE_DEBUG_FIELDS if k in payload}
                _LOGGER.debug("Webhook received for category %s: %s", category, safe)
            alert = UniFiAlert.from_webhook_payload(category, payload)
            self._push_callback(category, alert)
            return None

        return handle_webhook
