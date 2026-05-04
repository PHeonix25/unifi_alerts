"""Tests for WebhookManager — registration, token auth, and alert dispatch."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    CONF_ENABLED_CATEGORIES,
    CONF_WEBHOOK_ID_SUFFIX,
    CONF_WEBHOOK_SECRET,
    WEBHOOK_ID_PREFIX,
    WEBHOOK_MAX_BODY_BYTES,
    webhook_id_for_category,
)
from custom_components.unifi_alerts.webhook_handler import WebhookManager

# ── helpers ──────────────────────────────────────────────────────────────────


def make_manager(enabled=None, secret="test-secret-123", hass=None, suffix=""):
    if hass is None:
        hass = MagicMock()
    config = {
        CONF_ENABLED_CATEGORIES: enabled if enabled is not None else ALL_CATEGORIES,
        CONF_WEBHOOK_SECRET: secret,
        CONF_WEBHOOK_ID_SUFFIX: suffix,
    }
    push_cb = MagicMock()
    return WebhookManager(hass, "entry-123", config, push_cb), push_cb


def make_request(token: str | None = "test-secret-123", json_body: dict | None = None):
    """Build a minimal mock aiohttp.web.Request."""
    req = MagicMock()
    req.query = {"token": token} if token is not None else {}
    body_dict = json_body if json_body is not None else {"key": "EVT_GW_WANTransition", "message": "WAN down"}
    req.content.read = AsyncMock(return_value=json.dumps(body_dict).encode())
    return req


# ── register_all ─────────────────────────────────────────────────────────────


class TestRegisterAll:
    def test_registers_one_webhook_per_enabled_category(self):
        manager, _ = make_manager()
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register") as mock_reg,
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            manager.register_all()
        # One call per enabled category
        assert mock_reg.call_count == len(ALL_CATEGORIES)

    def test_skips_disabled_categories(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register") as mock_reg,
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()
        assert mock_reg.call_count == 1
        assert CATEGORY_NETWORK_WAN in urls
        assert CATEGORY_SECURITY_THREAT not in urls

    def test_url_includes_token_when_secret_set(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], secret="mysecret")
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()
        assert urls[CATEGORY_NETWORK_WAN] == "http://ha/hook/abc?token=mysecret"

    def test_url_has_no_token_when_secret_empty(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], secret="")
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()
        assert urls[CATEGORY_NETWORK_WAN] == "http://ha/hook/abc"

    def test_registered_list_populated(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            manager.register_all()
        assert len(manager._registered) == 1

    def test_returns_category_to_url_mapping(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
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
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            manager.register_all()

        with patch("custom_components.unifi_alerts.webhook_handler.async_unregister") as mock_unreg:
            manager.unregister_all()
        assert mock_unreg.call_count == 1

    def test_clears_registered_list(self):
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
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
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        req.content.read = AsyncMock(return_value=b"not valid json {{")
        await handler(manager._hass, "wh-id", req)
        push_cb.assert_called_once()
        # Alert should have fallback message
        call_category, call_alert = push_cb.call_args[0]
        assert call_alert.message == "Unknown alert"

    @pytest.mark.asyncio
    async def test_oversized_body_returns_413(self):
        """A webhook body larger than WEBHOOK_MAX_BODY_BYTES must be rejected with HTTP 413."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        req.content.read = AsyncMock(return_value=b"x" * (WEBHOOK_MAX_BODY_BYTES + 1))
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 413
        push_cb.assert_not_called()

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


# ── multi-entry webhook ID isolation (red-green pair for the collision fix) ──


class TestMultiEntryWebhookIdIsolation:
    """Two config entries must not collide on webhook IDs.

    Pre-fix, ``webhook_id_for_category(cat)`` returned ``unifi_alerts_{cat}``
    regardless of entry. Two entries silently overwrote each other's handlers.
    The fix introduces ``CONF_WEBHOOK_ID_SUFFIX`` (generated per-entry by the
    config flow) so each entry's webhook IDs are distinct.

    These tests exercise the collision via two real ``WebhookManager``
    instances — without the suffix they collide; with the suffix they don't.
    """

    def test_two_managers_with_distinct_suffixes_register_distinct_ids(self):
        hass1 = MagicMock()
        hass2 = MagicMock()
        m1, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], suffix="aaaa1111", hass=hass1)
        m2, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], suffix="bbbb2222", hass=hass2)

        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                side_effect=lambda hass, wid: f"http://ha/hook/{wid}",
            ),
        ):
            urls1 = m1.register_all()
            urls2 = m2.register_all()

        # Webhook IDs must differ between the two entries
        assert m1._registered != m2._registered
        assert m1._registered[0] == f"{WEBHOOK_ID_PREFIX}aaaa1111_{CATEGORY_NETWORK_WAN}"
        assert m2._registered[0] == f"{WEBHOOK_ID_PREFIX}bbbb2222_{CATEGORY_NETWORK_WAN}"
        # Generated URLs reflect the distinct IDs
        assert urls1[CATEGORY_NETWORK_WAN] != urls2[CATEGORY_NETWORK_WAN]

    def test_legacy_no_suffix_uses_unprefixed_id(self):
        """Existing entries created before the suffix shipped pass suffix='' —
        they fall back to the legacy ``unifi_alerts_{cat}`` format so their
        already-configured Alarm Manager URLs keep working."""
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN], suffix="")
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register"),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/legacy",
            ),
        ):
            manager.register_all()
        assert manager._registered[0] == f"{WEBHOOK_ID_PREFIX}{CATEGORY_NETWORK_WAN}"

    def test_webhook_id_for_category_function_signature(self):
        """The helper accepts an optional suffix and produces stable IDs."""
        assert webhook_id_for_category(CATEGORY_NETWORK_WAN) == f"{WEBHOOK_ID_PREFIX}network_wan"
        assert (
            webhook_id_for_category(CATEGORY_NETWORK_WAN, "deadbeef")
            == f"{WEBHOOK_ID_PREFIX}deadbeef_network_wan"
        )


# ── HMAC token comparison (timing-attack hardening) ──────────────────────────


class TestHmacTokenComparison:
    @pytest.mark.asyncio
    async def test_uses_hmac_compare_digest_for_token_check(self):
        """The token comparison must go through ``hmac.compare_digest``.

        We can't time-measure a side-channel in a unit test, but we can assert
        that the implementation actually calls ``hmac.compare_digest`` rather
        than ``==`` / ``!=`` so the hardening can't silently regress.
        """
        manager, _ = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="tok123")
        with patch(
            "custom_components.unifi_alerts.webhook_handler.hmac.compare_digest",
            return_value=True,
        ) as mock_cmp:
            await handler(manager._hass, "wh-id", req)
        mock_cmp.assert_called_once_with("tok123", "tok123")


# ── decode-error logging (no longer silent) ──────────────────────────────────


class TestDecodeErrorLogging:
    @pytest.mark.asyncio
    async def test_malformed_json_logs_warning_with_class_name(self):
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        req.content.read = AsyncMock(return_value=b"not valid json {{")
        with patch("custom_components.unifi_alerts.webhook_handler._LOGGER") as mock_logger:
            await handler(manager._hass, "wh-id", req)
        # Warning was emitted at least once with the JSONDecodeError class name
        assert mock_logger.warning.called
        warning_msg = mock_logger.warning.call_args[0][0]
        warning_args = mock_logger.warning.call_args[0][1:]
        assert "decode failed" in warning_msg
        assert "JSONDecodeError" in warning_args
        # push_callback is still invoked with the empty-payload fallback
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_utf8_logs_warning(self):
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        # Invalid UTF-8: lone continuation byte
        req.content.read = AsyncMock(return_value=b"\x80\x81\x82")
        with patch("custom_components.unifi_alerts.webhook_handler._LOGGER") as mock_logger:
            await handler(manager._hass, "wh-id", req)
        assert mock_logger.warning.called
        push_cb.assert_called_once()


# ── DEBUG payload narrowing ──────────────────────────────────────────────────


class TestDebugPayloadNarrowing:
    @pytest.mark.asyncio
    async def test_debug_log_only_includes_safe_fields(self):
        """Arbitrary controller fields (e.g. client MAC, IP) must not be logged."""
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        sensitive_payload = {
            "key": "EVT_GW_WANTransition",
            "message": "WAN port went offline",
            "device_name": "UDM-Pro",
            "severity": "critical",
            # Fields that must NOT appear in DEBUG output:
            "client_mac": "aa:bb:cc:dd:ee:ff",
            "client_ip": "10.0.0.42",
            "internal_token": "should-never-be-logged",
        }
        req = make_request(token="tok", json_body=sensitive_payload)
        with (
            patch("custom_components.unifi_alerts.webhook_handler._LOGGER") as mock_logger,
        ):
            mock_logger.isEnabledFor.return_value = True
            await handler(manager._hass, "wh-id", req)
        assert mock_logger.debug.called
        debug_call = mock_logger.debug.call_args
        logged_payload = debug_call[0][2]
        assert "client_mac" not in logged_payload
        assert "client_ip" not in logged_payload
        assert "internal_token" not in logged_payload
        # Safe fields ARE included
        assert logged_payload.get("key") == "EVT_GW_WANTransition"
        assert logged_payload.get("device_name") == "UDM-Pro"
        assert logged_payload.get("severity") == "critical"


# ── register_all() per-iteration error handling ──────────────────────────────


class TestRegisterAllRollback:
    def test_one_failed_registration_does_not_abort_the_rest(self):
        """If async_register raises for one category, others must still register."""
        manager, _ = make_manager(enabled=ALL_CATEGORIES)
        call_count = {"n": 0}

        def selective_fail(*args, **kwargs):
            # Fail on the second registration only
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom: HA registry rejected this id")
            return None

        with (
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_register",
                side_effect=selective_fail,
            ),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()

        # 7 categories attempted, 1 failed → 6 successfully registered, all
        # tracked so unregister_all() can clean them up later.
        assert len(manager._registered) == len(ALL_CATEGORIES) - 1
        assert len(urls) == len(ALL_CATEGORIES) - 1

    def test_failed_registration_is_not_tracked_in_registered(self):
        """A failed async_register must NOT add the webhook_id to ``_registered`` —
        otherwise unregister_all() would call async_unregister on something that
        was never registered, generating spurious errors at unload time."""
        manager, _ = make_manager(enabled=[CATEGORY_NETWORK_WAN])
        with (
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_register",
                side_effect=RuntimeError("nope"),
            ),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()
        assert manager._registered == []
        assert urls == {}
