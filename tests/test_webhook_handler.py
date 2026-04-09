"""Tests for WebhookManager — registration, token auth, and alert dispatch."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    CONF_ENABLED_CATEGORIES,
    CONF_WEBHOOK_SECRET,
)
from custom_components.unifi_alerts.webhook_handler import WebhookManager


# ── helpers ──────────────────────────────────────────────────────────────────

def make_manager(enabled=None, secret="test-secret-123", hass=None):
    if hass is None:
        hass = MagicMock()
    config = {
        CONF_ENABLED_CATEGORIES: enabled if enabled is not None else ALL_CATEGORIES,
        CONF_WEBHOOK_SECRET: secret,
    }
    push_cb = MagicMock()
    return WebhookManager(hass, "entry-123", config, push_cb), push_cb


def make_request(token: str | None = "test-secret-123", json_body: dict | None = None):
    """Build a minimal mock aiohttp.web.Request."""
    req = MagicMock()
    # query is a dict-like object
    req.query = {"token": token} if token is not None else {}
    # json() is async
    if json_body is None:
        req.json = AsyncMock(return_value={"key": "EVT_GW_WANTransition", "message": "WAN down"})
    else:
        req.json = AsyncMock(return_value=json_body)
    return req


# ── register_all ─────────────────────────────────────────────────────────────

class TestRegisterAll:
    def test_registers_one_webhook_per_enabled_category(self):
        manager, _ = make_manager()
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register") as mock_reg,
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            urls = manager.register_all()
        # One call per enabled category
        assert mock_reg.call_count == len(ALL_CATEGORIES)

    def test_skips_disabled_categories(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register") as mock_reg,
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            urls = manager.register_all()
        assert mock_reg.call_count == 1
        assert CATEGORY_NETWORK_WAN in urls
        assert CATEGORY_SECURITY_THREAT not in urls

    def test_url_includes_token_when_secret_set(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], secret="mysecret")
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            urls = manager.register_all()
        assert urls[CATEGORY_NETWORK_WAN] == "http://ha/hook/abc?token=mysecret"

    def test_url_has_no_token_when_secret_empty(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], secret="")
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            urls = manager.register_all()
        assert urls[CATEGORY_NETWORK_WAN] == "http://ha/hook/abc"

    def test_registered_list_populated(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            manager.register_all()
        assert len(manager._registered) == 1

    def test_returns_category_to_url_mapping(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            urls = manager.register_all()
        assert isinstance(urls, dict)
        assert CATEGORY_NETWORK_WAN in urls


# ── unregister_all ────────────────────────────────────────────────────────────

class TestUnregisterAll:
    def test_unregisters_all_registered_webhooks(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            manager.register_all()

        with patch("custom_components.unifi_alerts.webhook_handler.async_unregister") as mock_unreg:
            manager.unregister_all()
        assert mock_unreg.call_count == 1

    def test_clears_registered_list(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch("custom_components.unifi_alerts.webhook_handler.async_generate_url", return_value="http://ha/hook/abc"),
        ):
            manager.register_all()
        assert len(manager._registered) == 1

        with patch("custom_components.unifi_alerts.webhook_handler.async_unregister"):
            manager.unregister_all()
        assert len(manager._registered) == 0

    def test_suppresses_unregister_exceptions(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        manager._registered = ["some-webhook-id"]
        with patch(
            "custom_components.unifi_alerts.webhook_handler.async_unregister",
            side_effect=Exception("boom"),
        ):
            # Must not raise
            manager.unregister_all()
        assert len(manager._registered) == 0


# ── handler (token validation + dispatch) ────────────────────────────────────

class TestMakeHandler:
    """Tests for the closure returned by _make_handler."""

    @pytest.mark.asyncio
    async def test_valid_token_calls_push_callback(self):
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="tok123")
        await handler(manager._hass, "wh-id", req)
        push_cb.assert_called_once()
        call_category, call_alert = push_cb.call_args[0]
        assert call_category == CATEGORY_NETWORK_WAN

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self):
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token=None)
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self):
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="wrong-token")
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_secret_configured_accepts_any_request(self):
        """When secret is empty string, token check is skipped entirely.

        This is intentional: if the admin chose not to set a webhook secret
        (CONF_WEBHOOK_SECRET is empty), the integration operates without
        bearer-token auth.  The webhook is still local-only (local_only=True),
        so accepting token-less requests is a deliberate trade-off, not a bug.
        """
        manager, push_cb = make_manager(secret="")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "")
        req = make_request(token=None)
        response = await handler(manager._hass, "wh-id", req)
        # Should not return 401
        assert response is None
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_json_uses_empty_dict_fallback(self):
        """If the body can't be parsed as JSON, push_callback is still called with empty payload."""
        import json
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        req.json = AsyncMock(side_effect=json.JSONDecodeError("nope", "", 0))
        response = await handler(manager._hass, "wh-id", req)
        push_cb.assert_called_once()
        # Alert should have fallback message
        call_category, call_alert = push_cb.call_args[0]
        assert call_alert.message == "Unknown alert"

    @pytest.mark.asyncio
    async def test_alert_fields_populated_from_payload(self):
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(
            token="tok",
            json_body={
                "key": "EVT_GW_WANTransition",
                "message": "WAN offline",
                "device_name": "UDM-Pro",
                "severity": "critical",
            },
        )
        await handler(manager._hass, "wh-id", req)
        _, alert = push_cb.call_args[0]
        assert alert.message == "WAN offline"
        assert alert.device_name == "UDM-Pro"
        assert alert.severity == "critical"
        assert alert.key == "EVT_GW_WANTransition"
        assert alert.category == CATEGORY_NETWORK_WAN
