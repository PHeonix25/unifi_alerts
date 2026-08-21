"""Tests for WebhookManager — registration, token auth, and alert dispatch."""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from yarl import URL

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
from custom_components.unifi_alerts.webhook_handler import WebhookManager, _extract_bearer_token

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


def make_request(
    token: str | None = "test-secret-123",
    json_body: dict | None = None,
    authorization: str | None = None,
):
    """Build a minimal mock aiohttp.web.Request.

    ``token`` populates the legacy ``?token=`` query param; ``authorization``
    populates the raw ``Authorization`` header value (e.g. ``"Bearer tok"``).
    Both default to "absent" so tests exercise exactly the auth path they ask for.
    """
    req = MagicMock()
    req.query = {"token": token} if token is not None else {}
    req.headers = {"Authorization": authorization} if authorization is not None else {}
    body_dict = (
        json_body
        if json_body is not None
        else {"key": "EVT_GW_WANTransition", "message": "WAN down"}
    )
    req.content.read = AsyncMock(return_value=json.dumps(body_dict).encode())
    return req


# ── register_all ─────────────────────────────────────────────────────────────


def _assert_call_count_matches_all_categories(urls, manager, mock_reg):
    assert mock_reg.call_count == len(ALL_CATEGORIES)


def _assert_only_enabled_category_registered(urls, manager, mock_reg):
    assert mock_reg.call_count == 1
    assert CATEGORY_NETWORK_WAN in urls
    assert CATEGORY_SECURITY_THREAT not in urls


def _assert_url_has_no_token(urls, manager, mock_reg):
    assert urls[CATEGORY_NETWORK_WAN] == "http://ha/hook/abc"


def _assert_registered_list_populated(urls, manager, mock_reg):
    assert len(manager._registered) == 1


def _assert_returns_dict_mapping(urls, manager, mock_reg):
    assert isinstance(urls, dict)
    assert CATEGORY_NETWORK_WAN in urls


# ── _extract_bearer_token ────────────────────────────────────────────────────


class TestExtractBearerToken:
    def test_extracts_token_from_bearer_header(self):
        assert _extract_bearer_token("Bearer tok123") == "tok123"

    def test_scheme_is_case_insensitive(self):
        assert _extract_bearer_token("bearer tok123") == "tok123"
        assert _extract_bearer_token("BEARER tok123") == "tok123"

    def test_empty_header_returns_empty_string(self):
        assert _extract_bearer_token("") == ""

    def test_non_bearer_scheme_returns_empty_string(self):
        assert _extract_bearer_token("Basic dXNlcjpwYXNz") == ""

    def test_bearer_with_no_token_returns_empty_string(self):
        assert _extract_bearer_token("Bearer") == ""

    def test_bearer_with_trailing_whitespace_is_stripped(self):
        assert _extract_bearer_token("Bearer  tok123 ") == "tok123"


class TestRegisterAll:
    @pytest.mark.parametrize(
        ("enabled", "secret", "check"),
        [
            pytest.param(
                None,
                "test-secret-123",
                _assert_call_count_matches_all_categories,
                id="one-call-per-enabled-category",
            ),
            pytest.param(
                [CATEGORY_NETWORK_WAN],
                "test-secret-123",
                _assert_only_enabled_category_registered,
                id="skips-disabled-categories",
            ),
            pytest.param(
                [CATEGORY_NETWORK_WAN],
                "mysecret",
                _assert_url_has_no_token,
                id="url-has-no-token-when-secret-set",
            ),
            pytest.param(
                [CATEGORY_NETWORK_WAN],
                "",
                _assert_url_has_no_token,
                id="url-has-no-token-when-secret-empty",
            ),
            pytest.param(
                [CATEGORY_NETWORK_WAN],
                "test-secret-123",
                _assert_registered_list_populated,
                id="registered-list-populated",
            ),
            pytest.param(
                [CATEGORY_NETWORK_WAN],
                "test-secret-123",
                _assert_returns_dict_mapping,
                id="returns-category-to-url-mapping",
            ),
        ],
    )
    def test_register_all(self, enabled, secret, check):
        manager, _ = make_manager(enabled=enabled, secret=secret)
        with (
            patch("custom_components.unifi_alerts.webhook_handler.async_register") as mock_reg,
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()
        check(urls, manager, mock_reg)


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
        call_category, _call_alert = push_cb.call_args[0]
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
    async def test_valid_bearer_header_calls_push_callback(self):
        """Authorization: Bearer <secret> must be accepted (#176 preferred form)."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token=None, authorization="Bearer tok123")
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_bearer_header_case_insensitive_scheme(self):
        """RFC 6750: the Bearer scheme name is case-insensitive."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token=None, authorization="bearer tok123")
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrong_bearer_header_and_no_query_returns_401(self):
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token=None, authorization="Bearer wrong-token")
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_header_and_wrong_query_returns_401(self):
        """Full 401 matrix: both auth forms present but both wrong."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="wrong-query", authorization="Bearer wrong-header")
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_both_header_and_query_returns_401(self):
        """Full 401 matrix: neither auth form present."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token=None, authorization=None)
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_correct_header_with_wrong_query_is_accepted(self):
        """Either form independently authorises the request — header wins here."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="wrong-query", authorization="Bearer tok123")
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_correct_query_with_wrong_header_is_accepted(self):
        """Either form independently authorises the request — legacy query wins here."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="tok123", authorization="Bearer wrong-header")
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_secret_returns_500(self):
        """When secret is empty string, handler must fail closed with HTTP 500.

        Pre-v1.7 the empty-secret case silently accepted any request.  The
        VERSION 3 migration backfills a secret for every entry that lacks one,
        so reaching this branch in production means something went wrong.  The
        handler now rejects the request rather than accepting it.
        """
        manager, push_cb = make_manager(secret="")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "")
        req = make_request(token=None)
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 500
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_secret_coerced_to_empty_returns_500(self):
        """A secret of None (e.g. .get() returning None) must also return HTTP 500.

        The handler receives the secret via _make_handler(category, secret)
        where secret is already resolved from config.get(CONF_WEBHOOK_SECRET, "").
        If somehow None slips through, the not-secret branch still fires.
        """
        manager, push_cb = make_manager(secret="")
        # Simulate the handler being created with None cast to empty string
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, None or "")
        req = make_request(token=None)
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 500
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        """A body that fails JSON parsing must be rejected with HTTP 400; push_callback not called."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        req.content.read = AsyncMock(return_value=b"not valid json {{")
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 400
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_utf8_returns_400(self):
        """A body that fails UTF-8 decoding must be rejected with HTTP 400; push_callback not called."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")
        req.content.read = AsyncMock(return_value=b"\xff\xfe invalid utf-8")
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 400
        push_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_json_accepted(self):
        """A well-formed JSON body must be accepted (200/None) and push_callback called."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok", json_body={"message": "WAN down"})
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()

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


# ── empty / no-field body contract (#124) ────────────────────────────────────


class TestEmptyBodyContract:
    """Valid but empty or no-field bodies are accepted and produce 'Unknown alert'."""

    @pytest.mark.asyncio
    async def test_empty_json_object_calls_push_callback(self):
        """An authenticated POST with an empty JSON object must call push_callback."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok", json_body={})
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_json_object_produces_unknown_alert(self):
        """An empty JSON body must produce an alert with the 'Unknown alert' fallback message."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok", json_body={})
        await handler(manager._hass, "wh-id", req)
        _, alert = push_cb.call_args[0]
        assert alert.message == "Unknown alert"

    @pytest.mark.asyncio
    async def test_no_recognised_fields_calls_push_callback(self):
        """A body with no recognised alert fields must still call push_callback."""
        manager, push_cb = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok", json_body={"internal_id": "abc123", "ts": 1234567890})
        response = await handler(manager._hass, "wh-id", req)
        assert response is None
        push_cb.assert_called_once()
        _, alert = push_cb.call_args[0]
        assert alert.message == "Unknown alert"


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
    async def test_uses_hmac_compare_digest_for_both_token_checks(self):
        """Both the header and query token comparisons must go through
        ``hmac.compare_digest``.

        We can't time-measure a side-channel in a unit test, but we can assert
        that the implementation actually calls ``hmac.compare_digest`` rather
        than ``==`` / ``!=`` so the hardening can't silently regress. Both
        checks must run (not be short-circuited) so the header-absent /
        query-present case and the header-present / query-absent case take
        the same code path.
        """
        manager, _ = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(token="tok123", authorization="Bearer tok123")
        with patch(
            "custom_components.unifi_alerts.webhook_handler.hmac.compare_digest",
            return_value=True,
        ) as mock_cmp:
            await handler(manager._hass, "wh-id", req)
        assert mock_cmp.call_count == 2
        mock_cmp.assert_any_call("tok123", "tok123")  # header token vs secret
        mock_cmp.assert_any_call("tok123", "tok123")  # query token vs secret


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
        assert "Malformed webhook body" in warning_msg
        assert "JSONDecodeError" in warning_args
        # push_callback must NOT be called — we return 400 instead
        push_cb.assert_not_called()

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
        # push_callback must NOT be called — we return 400 instead
        push_cb.assert_not_called()


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
                raise ValueError("Handler is already defined!")
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
                side_effect=ValueError("Handler is already defined!"),
            ),
            patch(
                "custom_components.unifi_alerts.webhook_handler.async_generate_url",
                return_value="http://ha/hook/abc",
            ),
        ):
            urls = manager.register_all()
        assert manager._registered == []
        assert urls == {}


class TestSeverityGateUnreachableBeforeAuth:
    """Token auth must reject before the severity gate (which lives in
    coordinator.push_alert) is ever reached."""

    @pytest.mark.asyncio
    async def test_invalid_token_with_otherwise_accepted_alert_returns_401_and_skips_push(self):
        """An invalid-token request carrying a high-severity (otherwise-accepted)
        alert must still be rejected with 401 before push_callback (and therefore
        the coordinator's severity gate) is ever invoked."""
        manager, push_cb = make_manager(secret="tok123")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok123")
        req = make_request(
            token="wrong-token",
            json_body={
                "key": "EVT_GW_WANTransition",
                "message": "WAN down",
                "severity": "VERY_HIGH",
            },
        )
        response = await handler(manager._hass, "wh-id", req)
        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()


class TestWebhookSecretRotatedRepairIssue:
    """Repair issue lifecycle: created on rotation, cleared on first successful webhook."""

    @pytest.mark.asyncio
    async def test_valid_webhook_deletes_rotation_repair_issue(self):
        """A successfully authenticated webhook must delete the webhook_secret_rotated issue."""
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok")

        with patch(
            "custom_components.unifi_alerts.webhook_handler.ir.async_delete_issue"
        ) as mock_del:
            await handler(manager._hass, "wh-id", req)

        mock_del.assert_called_once_with(
            manager._hass,
            "unifi_alerts",
            "webhook_secret_rotated_entry-123",
        )

    @pytest.mark.asyncio
    async def test_rejected_webhook_does_not_delete_rotation_issue(self):
        """A rejected webhook (wrong token) must NOT delete the repair issue."""
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="wrong-token")

        with patch(
            "custom_components.unifi_alerts.webhook_handler.ir.async_delete_issue"
        ) as mock_del:
            await handler(manager._hass, "wh-id", req)

        mock_del.assert_not_called()


class TestWebhookLegacyQueryAuthRepairIssue:
    """Repair issue lifecycle for the ?token= deprecation nudge (#176)."""

    @pytest.mark.asyncio
    async def test_query_only_auth_raises_legacy_issue(self):
        """A webhook authenticated via the query param only must raise the nudge issue."""
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="tok", authorization=None)

        with patch(
            "custom_components.unifi_alerts.webhook_handler.ir.async_create_issue"
        ) as mock_create:
            await handler(manager._hass, "wh-id", req)

        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        assert args[2] == "webhook_legacy_query_auth_entry-123"
        assert kwargs["translation_key"] == "webhook_legacy_query_auth"

    @pytest.mark.asyncio
    async def test_header_auth_deletes_legacy_issue(self):
        """A webhook authenticated via the header must clear the nudge issue."""
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token=None, authorization="Bearer tok")

        with patch(
            "custom_components.unifi_alerts.webhook_handler.ir.async_delete_issue"
        ) as mock_del:
            await handler(manager._hass, "wh-id", req)

        mock_del.assert_any_call(
            manager._hass,
            "unifi_alerts",
            "webhook_legacy_query_auth_entry-123",
        )

    @pytest.mark.asyncio
    async def test_header_auth_does_not_raise_legacy_issue(self):
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token=None, authorization="Bearer tok")

        with patch(
            "custom_components.unifi_alerts.webhook_handler.ir.async_create_issue"
        ) as mock_create:
            await handler(manager._hass, "wh-id", req)

        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejected_webhook_does_not_raise_legacy_issue(self):
        manager, _ = make_manager(secret="tok")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "tok")
        req = make_request(token="wrong-token", authorization=None)

        with patch(
            "custom_components.unifi_alerts.webhook_handler.ir.async_create_issue"
        ) as mock_create:
            await handler(manager._hass, "wh-id", req)

        mock_create.assert_not_called()


class TestRequestUrlNeverLogged:
    """The legacy ``?token=`` query param (kept during the #176 deprecation
    window) means a webhook secret can appear in the request URL. Nothing in
    the handler logs ``request.url`` today, but nothing structurally prevents
    a future change from doing so by accident. These tests give a request a
    real ``request.url`` carrying the token in its query string and assert,
    via ``caplog``, that the token value never appears in any log record
    emitted by the malformed-body path or the auth-failure path.
    """

    TOKEN = "s3cr3t-webhook-token-f8a41c9e"

    def _request_with_url_token(
        self,
        url_token: str,
        query_token: str | None = None,
        json_body: dict | None = None,
    ):
        """Build a mock request whose ``.url`` carries ``?token=<url_token>``.

        ``request.query`` (used by the handler for auth) defaults to the same
        token so the request is internally consistent, matching how aiohttp
        derives ``request.query`` from ``request.url`` in production.
        """
        req = make_request(
            token=query_token if query_token is not None else url_token,
            json_body=json_body,
        )
        req.url = URL(f"http://homeassistant.local:8123/api/webhook/abc123?token={url_token}")
        return req

    @pytest.mark.asyncio
    async def test_malformed_body_path_never_logs_token(self, caplog):
        """Malformed body, authenticated via the token-bearing URL."""
        manager, push_cb = make_manager(secret=self.TOKEN)
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, self.TOKEN)
        req = self._request_with_url_token(self.TOKEN)
        req.content.read = AsyncMock(return_value=b"not valid json {{")

        with caplog.at_level(
            logging.DEBUG, logger="custom_components.unifi_alerts.webhook_handler"
        ):
            response = await handler(manager._hass, "wh-id", req)

        assert response is not None
        assert response.status == 400
        push_cb.assert_not_called()
        assert self.TOKEN not in caplog.text
        assert str(req.url) not in caplog.text
        for record in caplog.records:
            assert self.TOKEN not in record.getMessage()

    @pytest.mark.asyncio
    async def test_auth_failure_path_never_logs_token(self, caplog):
        """Auth failure: the URL carries a wrong/attacker-supplied token."""
        manager, push_cb = make_manager(secret="the-real-secret")
        handler = manager._make_handler(CATEGORY_NETWORK_WAN, "the-real-secret")
        req = self._request_with_url_token(self.TOKEN)

        with caplog.at_level(
            logging.DEBUG, logger="custom_components.unifi_alerts.webhook_handler"
        ):
            response = await handler(manager._hass, "wh-id", req)

        assert response is not None
        assert response.status == 401
        push_cb.assert_not_called()
        assert self.TOKEN not in caplog.text
        assert str(req.url) not in caplog.text
        for record in caplog.records:
            assert self.TOKEN not in record.getMessage()
