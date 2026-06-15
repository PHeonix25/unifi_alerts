"""Tests for the UniFi HTTP client."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_CLIENT,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_POWER,
    CATEGORY_SECURITY_FIREWALL,
    CATEGORY_SECURITY_HONEYPOT,
    CATEGORY_SECURITY_THREAT,
)
from custom_components.unifi_alerts.unifi_client import (
    _PROBE_FAIL_LIMIT,
    CannotConnectError,
    InvalidAuthError,
    UniFiClient,
)


def make_client(config: dict | None = None) -> UniFiClient:
    session = MagicMock()
    cfg = config or {
        "username": "admin",
        "password": "password",
        "verify_ssl": False,
    }
    return UniFiClient(session, "https://192.168.1.1", cfg)


class TestClassify:
    """Test the static _classify method for event key → category mapping."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            # Access points
            ("EVT_AP_Disconnected", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_Connected", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_Lost_Contact", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_Adopted", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_AutoReadopted", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_Restarted", CATEGORY_NETWORK_DEVICE),
            (
                "EVT_AP_RestartedUnknown",
                CATEGORY_NETWORK_DEVICE,
            ),  # matched by EVT_AP_Restarted prefix
            ("EVT_AP_Upgraded", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_UpgradeFailed", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_UpgradeScheduled", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_Isolated", CATEGORY_NETWORK_DEVICE),
            ("EVT_AP_Deleted", CATEGORY_NETWORK_DEVICE),
            # Switches
            ("EVT_SW_Connected", CATEGORY_NETWORK_DEVICE),
            ("EVT_SW_Lost_Contact", CATEGORY_NETWORK_DEVICE),
            ("EVT_SW_Adopted", CATEGORY_NETWORK_DEVICE),
            ("EVT_SW_AutoReadopted", CATEGORY_NETWORK_DEVICE),
            ("EVT_SW_Restarted", CATEGORY_NETWORK_DEVICE),
            (
                "EVT_SW_RestartedUnknown",
                CATEGORY_NETWORK_DEVICE,
            ),  # matched by EVT_SW_Restarted prefix
            ("EVT_SW_Upgraded", CATEGORY_NETWORK_DEVICE),
            ("EVT_SW_StpPortBlocking", CATEGORY_NETWORK_DEVICE),
            # Gateways
            ("EVT_GW_Connected", CATEGORY_NETWORK_DEVICE),
            ("EVT_GW_Lost_Contact", CATEGORY_NETWORK_DEVICE),
            ("EVT_GW_Adopted", CATEGORY_NETWORK_DEVICE),
            ("EVT_GW_Restarted", CATEGORY_NETWORK_DEVICE),
            (
                "EVT_GW_RestartedUnknown",
                CATEGORY_NETWORK_DEVICE,
            ),  # matched by EVT_GW_Restarted prefix
            ("EVT_GW_Upgraded", CATEGORY_NETWORK_DEVICE),
            # Dream Machine
            ("EVT_DM_Connected", CATEGORY_NETWORK_DEVICE),
            ("EVT_DM_Lost_Contact", CATEGORY_NETWORK_DEVICE),
            ("EVT_DM_Upgraded", CATEGORY_NETWORK_DEVICE),
            # Smart power / outlet devices
            ("EVT_XG_AutoReadopted", CATEGORY_NETWORK_DEVICE),
            ("EVT_XG_Connected", CATEGORY_NETWORK_DEVICE),
            ("EVT_XG_Lost_Contact", CATEGORY_NETWORK_DEVICE),
            # WAN
            ("EVT_GW_WANTransition", CATEGORY_NETWORK_WAN),
            ("EVT_GW_Failover", CATEGORY_NETWORK_WAN),
            # Clients — wireless users
            ("EVT_WU_Connected", CATEGORY_NETWORK_CLIENT),
            ("EVT_WU_Disconnected", CATEGORY_NETWORK_CLIENT),
            ("EVT_WU_Roam", CATEGORY_NETWORK_CLIENT),
            ("EVT_WU_RoamRadio", CATEGORY_NETWORK_CLIENT),  # matched by EVT_WU_Roam prefix
            # Clients — wireless guests
            ("EVT_WG_Connected", CATEGORY_NETWORK_CLIENT),
            ("EVT_WG_Disconnected", CATEGORY_NETWORK_CLIENT),
            ("EVT_WG_Roam", CATEGORY_NETWORK_CLIENT),
            ("EVT_WG_RoamRadio", CATEGORY_NETWORK_CLIENT),  # matched by EVT_WG_Roam prefix
            ("EVT_WG_AuthorizationEnded", CATEGORY_NETWORK_CLIENT),
            # Clients — wired users / LAN guests
            ("EVT_LU_Connected", CATEGORY_NETWORK_CLIENT),
            ("EVT_LU_Disconnected", CATEGORY_NETWORK_CLIENT),
            ("EVT_LG_Connected", CATEGORY_NETWORK_CLIENT),
            ("EVT_LG_Disconnected", CATEGORY_NETWORK_CLIENT),
            # Security: threat
            ("EVT_IPS_ThreatDetected", CATEGORY_SECURITY_THREAT),
            ("EVT_IPS_IpsAlert", CATEGORY_SECURITY_THREAT),
            ("EVT_IDS_Alert", CATEGORY_SECURITY_THREAT),
            ("EVT_AP_DetectRogueAP", CATEGORY_SECURITY_THREAT),
            ("EVT_AP_RadarDetected", CATEGORY_SECURITY_THREAT),
            ("EVT_SW_DetectRogueDHCP", CATEGORY_SECURITY_THREAT),
            # Security: honeypot
            ("EVT_GW_Honeypot", CATEGORY_SECURITY_HONEYPOT),
            ("EVT_GW_HoneypotDetected", CATEGORY_SECURITY_HONEYPOT),
            # Security: firewall
            ("EVT_GW_BlockedTraffic", CATEGORY_SECURITY_FIREWALL),
            ("EVT_LC_Blocked", CATEGORY_SECURITY_FIREWALL),
            ("EVT_WC_Blocked", CATEGORY_SECURITY_FIREWALL),
            # Power
            ("EVT_SW_PoEDisconnect", CATEGORY_POWER),
            ("EVT_SW_PoeDisconnect", CATEGORY_POWER),
            ("EVT_SW_PoeOverload", CATEGORY_POWER),
            ("EVT_SW_Overheat", CATEGORY_POWER),
            ("EVT_AP_PowerCycled", CATEGORY_POWER),
            ("EVT_GW_PowerLoss", CATEGORY_POWER),
            ("EVT_XG_OutletPowerCycle", CATEGORY_POWER),
            ("EVT_USP_RpsPowerDeniedByPsuOverload", CATEGORY_POWER),
            ("EVT_UPS_LowBattery", CATEGORY_POWER),  # matched by EVT_UPS_ prefix
        ],
    )
    def test_known_keys(self, key: str, expected: str):
        alarm = {"key": key}
        result = UniFiClient._classify(alarm)
        assert result == expected, f"Key {key!r} should map to {expected}, got {result}"

    def test_unknown_key_returns_none(self):
        alarm = {"key": "EVT_UNKNOWN_THING"}
        assert UniFiClient._classify(alarm) is None

    def test_missing_key_returns_none(self):
        alarm = {}
        assert UniFiClient._classify(alarm) is None


class TestHeaders:
    def test_userpass_auth_no_api_key_header(self):
        client = make_client()
        client._auth_method = "userpass"
        headers = client._headers()
        assert "X-API-Key" not in headers

    def test_apikey_auth_adds_header(self):
        client = make_client({"api_key": "test-key-123", "verify_ssl": False})
        client._auth_method = "apikey"
        headers = client._headers()
        assert headers.get("X-API-Key") == "test-key-123"


def _make_response(status: int, headers: dict | None = None):
    """Build a minimal mock aiohttp response for use in async context managers."""
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield resp

    return _ctx


class TestLoginUserpass:
    """Tests for _login_userpass error handling."""

    @pytest.mark.asyncio
    async def test_http_400_raises_cannot_connect(self):
        """HTTP 400 from the controller must raise CannotConnectError, not InvalidAuthError.

        UCG-Ultra returns 400 for request format / endpoint mismatch — this is
        NOT a credentials problem, so we must not show 'invalid credentials'.
        """
        client = make_client()
        ctx = _make_response(400)
        client._session.post = ctx
        with pytest.raises(CannotConnectError):
            await client._login_userpass()

    @pytest.mark.asyncio
    async def test_login_client_error_message_is_class_name_not_url(self):
        """CannotConnectError from _login_userpass must use class name, not str(err).

        Same credential-leak prevention as fetch_alarms: aiohttp errors can embed
        the login URL (which may contain the password) in their string representation.
        """
        import aiohttp

        client = make_client()

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("https://admin:hunter2@192.168.1.1/api/login")
            yield

        client._session.post = _raise
        with pytest.raises(CannotConnectError) as exc_info:
            await client._login_userpass()
        assert "hunter2" not in str(exc_info.value)
        assert exc_info.value.args[0] == "ClientConnectionError"

    @pytest.mark.asyncio
    async def test_http_401_raises_invalid_auth(self):
        """HTTP 401 should still raise InvalidAuthError (bad credentials)."""
        client = make_client()
        ctx = _make_response(401)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await client._login_userpass()

    @pytest.mark.asyncio
    async def test_http_403_raises_invalid_auth(self):
        """HTTP 403 should still raise InvalidAuthError (bad credentials)."""
        client = make_client()
        ctx = _make_response(403)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await client._login_userpass()

    @pytest.mark.asyncio
    async def test_invalid_auth_error_carries_login_url(self):
        """InvalidAuthError raised must carry login_url attribute pointing to /api/auth/login."""
        client = make_client()
        ctx = _make_response(401)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError) as exc_info:
            await client._login_userpass()
        # UniFi OS path is the only path now.
        assert exc_info.value.login_url.endswith("/api/auth/login")

    @pytest.mark.asyncio
    async def test_success_returns_without_error(self):
        """HTTP 200 from the UniFi OS login path must succeed without raising."""
        client = make_client()
        ctx = _make_response(200)
        client._session.post = ctx
        # Should not raise
        await client._login_userpass()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """3xx from the login endpoint must raise CannotConnectError, not follow the redirect."""
        client = make_client()
        ctx = _make_response(302)
        client._session.post = ctx
        with pytest.raises(CannotConnectError, match="redirect"):
            await client._login_userpass()


class TestVerifyApiKey:
    """Tests for _verify_api_key — API key authentication and endpoint selection."""

    @pytest.mark.asyncio
    async def test_always_uses_proxy_network_prefix(self):
        """_verify_api_key must always use /proxy/network prefix."""
        client = make_client({"api_key": "my-key", "verify_ssl": False})

        captured_url: list[str] = []

        @asynccontextmanager
        async def _ctx(*args, **kwargs):
            captured_url.append(args[0] if args else "")
            resp = MagicMock()
            resp.status = 200
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            yield resp

        client._session.get = _ctx
        await client._verify_api_key()

        assert captured_url, "Expected at least one GET call"
        assert "/proxy/network" in captured_url[0], (
            f"Expected /proxy/network in URL, got: {captured_url[0]}"
        )

    @pytest.mark.asyncio
    async def test_404_raises_cannot_connect(self):
        """HTTP 404 from the API key endpoint must raise CannotConnectError, not bubble up."""
        client = make_client({"api_key": "my-key", "verify_ssl": False})
        ctx = _make_response(404)
        client._session.get = ctx

        with pytest.raises(CannotConnectError, match="API key endpoint not found"):
            await client._verify_api_key()

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth(self):
        """HTTP 401 from the API key endpoint must raise InvalidAuthError."""
        client = make_client({"api_key": "bad-key", "verify_ssl": False})
        ctx = _make_response(401)
        client._session.get = ctx

        with pytest.raises(InvalidAuthError):
            await client._verify_api_key()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """A 3xx from the API key endpoint must raise CannotConnectError (no redirect)."""
        client = make_client({"api_key": "my-key", "verify_ssl": False})
        ctx = _make_response(302)
        client._session.get = ctx

        with pytest.raises(CannotConnectError, match="redirect"):
            await client._verify_api_key()


def _make_json_response(status: int, body: dict | None = None):
    """Build a mock aiohttp response that returns JSON body."""
    resp = MagicMock()
    resp.status = status
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value=body or {})

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield resp

    return _ctx, resp


class TestFetchAlarms:
    """Tests for UniFiClient.fetch_alarms."""

    @pytest.mark.asyncio
    async def test_returns_non_archived_alarms(self):
        client = make_client()
        client._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "archived": False},
                {"key": "EVT_AP_Disconnected", "archived": True},  # should be filtered
            ],
        }
        ctx, _ = _make_json_response(200, body)
        client._session.get = ctx
        alarms = await client.fetch_alarms()
        assert len(alarms) == 1
        assert alarms[0]["key"] == "EVT_GW_WANTransition"

    @pytest.mark.asyncio
    async def test_filters_out_archived_alarms(self):
        client = make_client()
        client._authenticated = True
        body = {"meta": {"rc": "ok"}, "data": [{"key": "EVT_GW_WANTransition", "archived": True}]}
        ctx, _ = _make_json_response(200, body)
        client._session.get = ctx
        alarms = await client.fetch_alarms()
        assert alarms == []

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth_and_clears_authenticated(self):
        client = make_client()
        client._authenticated = True
        ctx = _make_response(401)
        client._session.get = ctx
        with pytest.raises(InvalidAuthError):
            await client.fetch_alarms()
        assert client._authenticated is False

    @pytest.mark.asyncio
    async def test_client_error_raises_cannot_connect(self):
        import aiohttp

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("unreachable")
            yield  # make it a generator

        client._session.get = _raise
        with pytest.raises(CannotConnectError):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_client_error_message_is_class_name_not_url(self):
        """CannotConnectError message must be the exception class name, not str(err).

        aiohttp exceptions can embed the controller URL (including credentials) in
        their string representation.  Using type(err).__name__ prevents credential
        leaks via HA log output.
        """
        import aiohttp

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("https://admin:secret@192.168.1.1/api")
            yield

        client._session.get = _raise
        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()
        assert "secret" not in str(exc_info.value)
        assert exc_info.value.args[0] == "ClientConnectionError"

    @pytest.mark.asyncio
    async def test_response_error_preserves_status_code_in_message(self):
        """A ClientResponseError (e.g. 404) must surface its status code in the error.

        Before this test existed, the handler wrapped all aiohttp errors as
        ``CannotConnectError(type(err).__name__)``, which produced the opaque
        'Cannot reach alarm endpoint: ClientResponseError' log line with no
        status code. Status code only — no URL — to avoid leaking credentials
        that may be embedded in a misconfigured controller URL.
        """
        import aiohttp

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _ctx(*args, **kwargs):
            resp = MagicMock()
            resp.status = 503
            resp.headers = {}
            resp.raise_for_status = MagicMock(
                side_effect=aiohttp.ClientResponseError(
                    request_info=MagicMock(),
                    history=(),
                    status=503,
                    message="Service Unavailable",
                )
            )
            yield resp

        client._session.get = _ctx
        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()

        message = str(exc_info.value)
        assert "503" in message, f"Status code must be in the error message; got: {message!r}"
        assert "ClientResponseError" in message, (
            f"Exception class name must be in the error message; got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_tries_list_alarm_path_first(self):
        """fetch_alarms must try /list/alarm before any older path.

        /list/alarm is the newest UniFi Network endpoint (9.x+); the older /alarm
        and /stat/alarm paths are kept as fallbacks so the integration keeps
        working on older firmware. See docs/UNIFI.md § "Alarm API endpoint".
        """
        client = make_client()
        client._authenticated = True

        captured_urls: list[str] = []

        @asynccontextmanager
        async def _tracking_get(*args, **kwargs):
            captured_urls.append(args[0] if args else "")
            resp = MagicMock()
            resp.status = 200
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value={"meta": {"rc": "ok"}, "data": []})
            yield resp

        client._session.get = _tracking_get
        await client.fetch_alarms()

        assert captured_urls, "Expected at least one GET call"
        first_url = captured_urls[0]
        assert first_url.endswith("/list/alarm"), (
            f"First URL tried must end with /list/alarm; got: {first_url}"
        )
        # Only one call expected — /list/alarm worked, no fallback needed
        assert len(captured_urls) == 1

    @pytest.mark.asyncio
    async def test_fetch_alarms_uses_proxy_network_path(self):
        """fetch_alarms must always use the /proxy/network prefix for all alarm paths."""
        client = make_client()
        client._authenticated = True

        captured_urls: list[str] = []

        @asynccontextmanager
        async def _tracking_get(*args, **kwargs):
            captured_urls.append(args[0] if args else "")
            resp = MagicMock()
            resp.status = 200
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value={"meta": {"rc": "ok"}, "data": []})
            yield resp

        client._session.get = _tracking_get
        await client.fetch_alarms()

        assert captured_urls, "Expected at least one GET call"
        first_url = captured_urls[0]
        assert "/proxy/network/api/s/default/" in first_url, (
            f"fetch_alarms must use /proxy/network path; got: {first_url}"
        )

    @pytest.mark.asyncio
    async def test_falls_back_through_full_path_chain(self):
        """fetch_alarms must walk the full path chain when each preceding path is missing.

        Order is: /list/alarm (newest) → /alarm → /stat/alarm (oldest). A 404 on each
        of the first two must continue to the next; the third must succeed. This guards
        against future regressions if someone reorders or drops an entry from
        ``alarm_paths`` without updating both code and docs.
        """
        client = make_client()
        client._authenticated = True

        captured_urls: list[str] = []

        @asynccontextmanager
        async def _404_404_then_200(*args, **kwargs):
            captured_urls.append(args[0] if args else "")
            call_index = len(captured_urls)
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if call_index < 3:
                resp.status = 404
            else:
                resp.status = 200
                resp.json = AsyncMock(return_value={"meta": {"rc": "ok"}, "data": []})
            yield resp

        client._session.get = _404_404_then_200
        result = await client.fetch_alarms()

        assert len(captured_urls) == 3, (
            f"Expected exactly three GET calls walking the chain; got {len(captured_urls)}"
        )
        assert captured_urls[0].endswith("/list/alarm")
        assert captured_urls[1].endswith("/alarm") and not captured_urls[1].endswith("/list/alarm")
        assert captured_urls[2].endswith("/stat/alarm")
        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_next_path_on_404(self):
        """fetch_alarms must try the next path when the current one returns 404.

        Verifies the basic fallback contract for any single-step transition in the
        chain. The first path returns 404, the second returns success.
        """
        client = make_client()
        client._authenticated = True

        call_count = [0]

        @asynccontextmanager
        async def _404_then_200(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                resp.status = 404
                resp.headers = {}
                resp.raise_for_status = MagicMock()
            else:
                resp.status = 200
                resp.headers = {}
                resp.raise_for_status = MagicMock()
                resp.json = AsyncMock(return_value={"meta": {"rc": "ok"}, "data": []})
            yield resp

        client._session.get = _404_then_200
        result = await client.fetch_alarms()

        assert call_count[0] == 2, "Expected exactly two GET calls (primary + fallback)"
        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_next_path_on_400_invalid_object(self):
        """fetch_alarms must try the next path on 400 api.err.InvalidObject.

        Some firmware returns 400 + api.err.InvalidObject for endpoint paths that don't
        exist on that firmware version (instead of the more conventional 404).  The
        integration must treat this the same as 404 and try the next path.
        """
        client = make_client()
        client._authenticated = True

        call_count = [0]
        invalid_body = {"meta": {"rc": "error", "msg": "api.err.InvalidObject"}, "data": []}

        @asynccontextmanager
        async def _invalid_object_then_200(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                resp.status = 400
                resp.headers = {}
                resp.raise_for_status = MagicMock()
                resp.json = AsyncMock(return_value=invalid_body)
            else:
                resp.status = 200
                resp.headers = {}
                resp.raise_for_status = MagicMock()
                resp.json = AsyncMock(return_value={"meta": {"rc": "ok"}, "data": []})
            yield resp

        client._session.get = _invalid_object_then_200
        result = await client.fetch_alarms()

        assert call_count[0] == 2, "Expected exactly two GET calls (primary + fallback)"
        assert result == []

    @pytest.mark.asyncio
    async def test_all_paths_404_raises_cannot_connect(self):
        """When all alarm paths return 404, raise CannotConnectError with the tried paths."""
        client = make_client()
        client._authenticated = True
        ctx = _make_response(404)
        client._session.get = ctx

        with pytest.raises(CannotConnectError, match="Could not find the alarm endpoint"):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_http_400_raises_cannot_connect_with_site_hint(self):
        """HTTP 400 (non-InvalidObject) from the alarm endpoint raises CannotConnectError.

        A 400 with any error other than api.err.InvalidObject means a genuine rejection
        (e.g. wrong site name).  The error message must name the site so the user knows
        what to check.  api.err.InvalidObject is treated as "path not found" (see separate
        test) and causes a fallback rather than an immediate error.
        """
        client = make_client()
        client._authenticated = True
        # Return 400 with a non-InvalidObject body so neither path is treated as "not found"
        bad_body = {"meta": {"rc": "error", "msg": "api.err.Invalid"}, "data": []}

        @asynccontextmanager
        async def _400_bad(*args, **kwargs):
            resp = MagicMock()
            resp.status = 400
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value=bad_body)
            yield resp

        client._session.get = _400_bad

        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()

        message = str(exc_info.value)
        assert "400" in message
        assert "default" in message  # site name is mentioned so user knows what to check

    @pytest.mark.asyncio
    async def test_api_error_response_raises_cannot_connect(self):
        """HTTP 200 with meta.rc != 'ok' must raise CannotConnectError.

        The UniFi controller returns HTTP 200 even for API-level errors; only
        meta.rc distinguishes success from failure.  Silently returning [] would
        hide misconfigured site names and similar problems from the user.
        """
        client = make_client()
        client._authenticated = True
        body = {"meta": {"rc": "error", "msg": "api.err.InvalidObject"}, "data": []}
        ctx, _ = _make_json_response(200, body)
        client._session.get = ctx
        with pytest.raises(CannotConnectError, match="api.err.InvalidObject"):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_not_authenticated_calls_authenticate_first(self):
        """fetch_alarms must call authenticate() when not yet authenticated."""
        client = make_client()
        client._authenticated = False
        # authenticate() is called; after it the client should be marked as authenticated
        # so we patch authenticate to set _authenticated=True and return
        body = {"meta": {"rc": "ok"}, "data": [{"key": "EVT_GW_WANTransition", "archived": False}]}
        ctx, _ = _make_json_response(200, body)
        client._session.get = ctx

        authenticated_calls = []

        async def _mock_authenticate():
            client._authenticated = True
            client._auth_method = "userpass"
            authenticated_calls.append(1)

        client.authenticate = _mock_authenticate
        await client.fetch_alarms()
        assert len(authenticated_calls) == 1

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """A 3xx on an authenticated alarm fetch must raise CannotConnectError (no redirect)."""
        client = make_client()
        client._authenticated = True
        ctx = _make_response(301)
        client._session.get = ctx
        with pytest.raises(CannotConnectError, match="redirect"):
            await client.fetch_alarms()


class TestCategoriseAlarms:
    """Tests for UniFiClient.categorise_alarms."""

    @pytest.mark.asyncio
    async def test_groups_alarms_by_category(self):
        client = make_client()
        client._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "msg": "WAN down", "archived": False},
                {"key": "EVT_IPS_ThreatDetected", "msg": "Threat", "archived": False},
                {"key": "EVT_GW_Failover", "msg": "Failover", "archived": False},
            ],
        }
        ctx, _ = _make_json_response(200, body)
        client._session.get = ctx
        result = await client.categorise_alarms()
        from custom_components.unifi_alerts.const import (
            CATEGORY_NETWORK_WAN,
            CATEGORY_SECURITY_THREAT,
        )

        assert CATEGORY_NETWORK_WAN in result
        assert CATEGORY_SECURITY_THREAT in result
        assert len(result[CATEGORY_NETWORK_WAN]) == 2  # both WAN events

    @pytest.mark.asyncio
    async def test_skips_unclassified_alarms(self):
        client = make_client()
        client._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_UNKNOWN_THING", "msg": "who knows", "archived": False},
            ],
        }
        ctx, _ = _make_json_response(200, body)
        client._session.get = ctx
        result = await client.categorise_alarms()
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_alarm_list_returns_empty_dict(self):
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_json_response(200, {"meta": {"rc": "ok"}, "data": []})
        client._session.get = ctx
        result = await client.categorise_alarms()
        assert result == {}


class TestAuthenticate:
    """Tests for UniFiClient.authenticate — auth method selection and fallback."""

    @pytest.mark.asyncio
    async def test_apikey_method_used_when_configured(self):
        client = make_client({"api_key": "my-key", "auth_method": "apikey", "verify_ssl": False})

        verify_calls = []

        async def _mock_verify():
            verify_calls.append(1)

        client._verify_api_key = _mock_verify
        result = await client.authenticate()
        assert result == "apikey"
        assert len(verify_calls) == 1

    @pytest.mark.asyncio
    async def test_apikey_fallback_to_userpass_when_key_invalid(self):
        """If api_key present but method not explicitly set to apikey, fall back to userpass on InvalidAuthError."""
        client = make_client({"api_key": "bad-key", "verify_ssl": False})

        async def _bad_verify():
            raise InvalidAuthError("bad key")

        userpass_calls = []

        async def _mock_login():
            userpass_calls.append(1)

        client._verify_api_key = _bad_verify
        client._login_userpass = _mock_login
        result = await client.authenticate()
        assert result == "userpass"
        assert len(userpass_calls) == 1

    @pytest.mark.asyncio
    async def test_explicit_apikey_method_does_not_fallback(self):
        """If auth_method=apikey is explicit, InvalidAuthError must propagate (no fallback)."""
        client = make_client({"api_key": "bad-key", "auth_method": "apikey", "verify_ssl": False})

        async def _bad_verify():
            raise InvalidAuthError("bad key")

        client._verify_api_key = _bad_verify
        with pytest.raises(InvalidAuthError):
            await client.authenticate()


class TestClose:
    """Tests for UniFiClient.close — logout behavior.

    close() calls ``await session.post(url, ...)`` without an async-with block,
    so the mock must be a plain AsyncMock (coroutine), not an asynccontextmanager.
    """

    @pytest.mark.asyncio
    async def test_userpass_auth_posts_to_unifi_os_logout_path(self):
        """close() must POST to /api/auth/logout (UniFi OS path only)."""
        client = make_client()
        client._auth_method = "userpass"
        client._authenticated = True
        client._session.post = AsyncMock()
        await client.close()
        client._session.post.assert_awaited_once()
        url_called = client._session.post.call_args[0][0]
        assert "/api/auth/logout" in url_called

    @pytest.mark.asyncio
    async def test_apikey_auth_does_not_post_logout(self):
        client = make_client({"api_key": "k", "verify_ssl": False})
        client._auth_method = "apikey"
        client._authenticated = True
        client._session.post = AsyncMock()
        await client.close()
        client._session.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_authenticated_does_not_post_logout(self):
        client = make_client()
        client._auth_method = "userpass"
        client._authenticated = False
        client._session.post = AsyncMock()
        await client.close()
        client._session.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logout_failure_logs_warning_with_class_name_only(self, caplog):
        """A failed logout must log at WARNING with the exception class name only.

        The previous `contextlib.suppress(Exception)` swallowed the error silently,
        leaving operators no diagnostic and the session token live on the controller.
        We log the class name (not str(err)) to avoid surfacing controller response
        bodies that may include sensitive fragments.
        """
        import logging

        client = make_client()
        client._auth_method = "userpass"
        client._authenticated = True
        secret_marker = "controller.local: 401 Unauthorized — api_key=secret"
        client._session.post = AsyncMock(side_effect=ConnectionResetError(secret_marker))

        with caplog.at_level(logging.WARNING, logger="custom_components.unifi_alerts.unifi_client"):
            await client.close()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ConnectionResetError" in r.getMessage() for r in warnings)
        assert all(secret_marker not in r.getMessage() for r in warnings)

    @pytest.mark.asyncio
    async def test_logout_failure_does_not_propagate(self):
        """close() must never raise — failed logout is best-effort."""
        client = make_client()
        client._auth_method = "userpass"
        client._authenticated = True
        client._session.post = AsyncMock(side_effect=RuntimeError("boom"))

        # No pytest.raises — close() must absorb the failure.
        await client.close()


class TestSslFailOpen:
    """Verify that a missing CONF_VERIFY_SSL key falls back to DEFAULT_VERIFY_SSL (True).

    The fix changed all five ssl=self._config.get(CONF_VERIFY_SSL, False) call sites to
    use DEFAULT_VERIFY_SSL (True) as the fallback.  A missing key must now fail *closed*
    (SSL ON) rather than silently disabling certificate verification.
    """

    @pytest.mark.asyncio
    async def test_absent_verify_ssl_key_defaults_to_true_in_fetch_alarms(self):
        """When CONF_VERIFY_SSL is absent from config, _try_fetch_alarms must pass ssl=True.

        Constructs a config dict with no verify_ssl key and asserts that the ssl kwarg
        forwarded to the mock session is DEFAULT_VERIFY_SSL (True), not False.
        """
        from custom_components.unifi_alerts.const import DEFAULT_VERIFY_SSL

        # Config deliberately omits verify_ssl
        config = {"username": "admin", "password": "secret"}
        client = make_client(config)
        client._authenticated = True

        captured_ssl: list = []

        @asynccontextmanager
        async def _tracking_get(*args, **kwargs):
            captured_ssl.append(kwargs.get("ssl"))
            resp = MagicMock()
            resp.status = 200
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value={"meta": {"rc": "ok"}, "data": []})
            yield resp

        client._session.get = _tracking_get
        await client.fetch_alarms()

        assert captured_ssl, "Expected at least one GET call"
        assert captured_ssl[0] is DEFAULT_VERIFY_SSL, (
            f"Expected ssl={DEFAULT_VERIFY_SSL!r} (DEFAULT_VERIFY_SSL) when key is absent, "
            f"got {captured_ssl[0]!r}"
        )
        assert captured_ssl[0] is True, "DEFAULT_VERIFY_SSL must be True — fail closed"


def _make_post_json_response(status: int, body: dict | None = None):
    """Build a mock aiohttp POST response that returns JSON body."""
    resp = MagicMock()
    resp.status = status
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value=body or {})

    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        yield resp

    return _ctx, resp


class TestSslCertificateError:
    """SslCertificateError is raised on TLS certificate failures, not CannotConnectError."""

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in _verify_api_key must raise SslCertificateError."""
        import aiohttp

        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client({"api_key": "test-key", "verify_ssl": True})

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock())
            yield  # type: ignore[misc]

        client._session.get = _raise
        with pytest.raises(SslCertificateError):
            await client._verify_api_key()

    @pytest.mark.asyncio
    async def test_login_userpass_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in _login_userpass must raise SslCertificateError."""
        import aiohttp

        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client()

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock())
            yield  # type: ignore[misc]

        client._session.post = _raise
        with pytest.raises(SslCertificateError):
            await client._login_userpass()

    @pytest.mark.asyncio
    async def test_try_fetch_alarms_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in _try_fetch_alarms must raise SslCertificateError."""
        import aiohttp

        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock())
            yield  # type: ignore[misc]

        client._session.get = _raise
        with pytest.raises(SslCertificateError):
            await client._try_fetch_alarms("https://192.168.1.1/api/alarm", "default")

    @pytest.mark.asyncio
    async def test_fetch_system_log_alarms_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in fetch_system_log_alarms must raise SslCertificateError."""
        import aiohttp

        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock())
            yield  # type: ignore[misc]

        client._session.post = _raise
        with pytest.raises(SslCertificateError):
            await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_verify_api_key_generic_client_error_raises_cannot_connect(self):
        """A generic aiohttp.ClientError in _verify_api_key must raise CannotConnectError."""
        import aiohttp

        client = make_client({"api_key": "test-key", "verify_ssl": True})

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("connection refused")
            yield  # type: ignore[misc]

        client._session.get = _raise
        with pytest.raises(CannotConnectError):
            await client._verify_api_key()

    @pytest.mark.asyncio
    async def test_ssl_cert_error_is_subclass_of_cannot_connect(self):
        from custom_components.unifi_alerts.unifi_client import (
            CannotConnectError,
            SslCertificateError,
        )

        assert issubclass(SslCertificateError, CannotConnectError)


class TestProbeSystemLogEndpoint:
    """Tests for UniFiClient.probe_system_log_endpoint."""

    @pytest.mark.asyncio
    async def test_probe_returns_true_on_200(self):
        """HTTP 200 from /system-log/count must return True and set _has_system_log=True."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(200, {"categories": []})
        client._session.post = ctx
        result = await client.probe_system_log_endpoint()
        assert result is True
        assert client._has_system_log is True

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_404(self):
        """HTTP 404 from /system-log/count must return False and set _has_system_log=False."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(404)
        client._session.post = ctx
        result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is False

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_403_does_not_cache(self):
        """HTTP 403 (non-definitive) must return False this call but leave the cache None.

        Only 404 is treated as a definitive "endpoint not implemented" response.
        Other 4xx codes may be transient (e.g., temporary permission state) and
        re-probing on the next poll is preferable to pinning to legacy mode.
        """
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(403)
        client._session.post = ctx
        result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_500_does_not_cache(self):
        """HTTP 5xx is treated as transient: returns False without caching."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(503)
        client._session.post = ctx
        result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_network_error_does_not_cache(self):
        """aiohttp.ClientError during probe must return False, not raise, and not cache."""
        import aiohttp

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("unreachable")
            yield

        client._session.post = _raise
        result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_retries_after_transient_failure(self):
        """A 5xx followed by a 200 must end with cache=True (transient does not pin to legacy)."""
        client = make_client()
        client._authenticated = True

        responses = [503, 200]

        @asynccontextmanager
        async def _stub(*args, **kwargs):
            resp = MagicMock()
            resp.status = responses.pop(0)
            resp.json = AsyncMock(return_value={})
            yield resp

        client._session.post = _stub
        first = await client.probe_system_log_endpoint()
        assert first is False
        assert client._has_system_log is None, "Transient failure must not cache"
        second = await client.probe_system_log_endpoint()
        assert second is True
        assert client._has_system_log is True

    @pytest.mark.asyncio
    async def test_probe_is_cached_after_true(self):
        """Second call must not hit the network when _has_system_log is True."""
        client = make_client()
        client._authenticated = True
        client._has_system_log = True  # pre-set the cache

        call_count = [0]

        @asynccontextmanager
        async def _counting(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status = 200
            resp.json = AsyncMock(return_value={})
            yield resp

        client._session.post = _counting
        result = await client.probe_system_log_endpoint()
        assert result is True
        assert call_count[0] == 0, "Network must not be hit when result is cached"

    @pytest.mark.asyncio
    async def test_probe_is_cached_after_false(self):
        """Second call must not hit the network when _has_system_log is False."""
        client = make_client()
        client._authenticated = True
        client._has_system_log = False  # pre-set the cache

        call_count = [0]

        @asynccontextmanager
        async def _counting(*args, **kwargs):
            call_count[0] += 1
            yield MagicMock()

        client._session.post = _counting
        result = await client.probe_system_log_endpoint()
        assert result is False
        assert call_count[0] == 0, "Network must not be hit when result is cached"

    @pytest.mark.asyncio
    async def test_probe_url_includes_v2_and_site(self):
        """Probe URL must include /v2/api/site/{site}/system-log/count."""
        client = make_client()
        client._authenticated = True

        captured_url: list[str] = []

        @asynccontextmanager
        async def _tracking(*args, **kwargs):
            captured_url.append(args[0] if args else "")
            resp = MagicMock()
            resp.status = 200
            resp.json = AsyncMock(return_value={})
            yield resp

        client._session.post = _tracking
        await client.probe_system_log_endpoint(site="mysite")

        assert captured_url, "Expected one POST call"
        assert "v2/api/site/mysite/system-log/count" in captured_url[0]

    @pytest.mark.asyncio
    async def test_probe_backoff_triggers_after_fail_limit(self):
        """After _PROBE_FAIL_LIMIT consecutive transient failures the probe caches False
        and sets a backoff deadline so subsequent polls skip the network entirely."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(503)

        call_count = [0]

        @asynccontextmanager
        async def _always_503(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status = 503
            resp.json = AsyncMock(return_value={})
            yield resp

        client._session.post = _always_503
        for _ in range(_PROBE_FAIL_LIMIT):
            result = await client.probe_system_log_endpoint()
            assert result is False

        # After the threshold the cache must be False and a backoff deadline set.
        assert client._has_system_log is False
        assert client._probe_backoff_until is not None
        assert client._probe_fail_count == _PROBE_FAIL_LIMIT

    @pytest.mark.asyncio
    async def test_probe_during_backoff_skips_network(self):
        """Once in backoff, probes must return False without making a network call."""
        from datetime import UTC, datetime, timedelta

        client = make_client()
        client._authenticated = True
        client._has_system_log = False
        client._probe_backoff_until = datetime.now(UTC) + timedelta(hours=1)

        call_count = [0]

        @asynccontextmanager
        async def _should_not_be_called(*args, **kwargs):
            call_count[0] += 1
            yield MagicMock()

        client._session.post = _should_not_be_called
        result = await client.probe_system_log_endpoint()
        assert result is False
        assert call_count[0] == 0, "Network must not be hit during backoff"

    @pytest.mark.asyncio
    async def test_probe_retries_after_backoff_expires(self):
        """Once the backoff window expires, the next probe must hit the network
        and, if successful, set cache=True and clear backoff state."""
        from datetime import UTC, datetime, timedelta

        client = make_client()
        client._authenticated = True
        # Simulate an expired backoff (deadline in the past).
        client._has_system_log = False
        client._probe_backoff_until = datetime.now(UTC) - timedelta(seconds=1)
        client._probe_fail_count = _PROBE_FAIL_LIMIT

        ctx, _ = _make_post_json_response(200, {})
        client._session.post = ctx

        result = await client.probe_system_log_endpoint()
        assert result is True
        assert client._has_system_log is True
        assert client._probe_backoff_until is None
        assert client._probe_fail_count == 0

    @pytest.mark.asyncio
    async def test_probe_404_does_not_set_backoff(self):
        """A definitive 404 must set cache=False without a backoff deadline
        (the endpoint will never appear on this controller)."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(404)
        client._session.post = ctx

        result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is False
        assert client._probe_backoff_until is None

    @pytest.mark.asyncio
    async def test_probe_backoff_via_network_error(self):
        """Repeated aiohttp.ClientError failures must also trigger the backoff
        after reaching _PROBE_FAIL_LIMIT."""
        import aiohttp

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _always_fail(*args, **kwargs):
            raise aiohttp.ClientConnectionError("unreachable")
            yield

        client._session.post = _always_fail
        for _ in range(_PROBE_FAIL_LIMIT):
            result = await client.probe_system_log_endpoint()
            assert result is False

        assert client._has_system_log is False
        assert client._probe_backoff_until is not None

    @pytest.mark.asyncio
    async def test_reauth_clears_probe_backoff(self):
        """A successful authenticate() must clear the probe-backoff state so the
        next probe call actually hits the network instead of returning the cached
        False from backoff."""
        from datetime import UTC, datetime, timedelta

        client = make_client()
        # Simulate an active backoff (e.g. credentials were bad, probe kept failing)
        client._has_system_log = False
        client._probe_fail_count = _PROBE_FAIL_LIMIT
        client._probe_backoff_until = datetime.now(UTC) + timedelta(hours=1)

        # Authenticate succeeds (200 from the login endpoint)
        login_ctx = _make_response(200)
        client._session.post = login_ctx
        await client.authenticate()

        # Backoff state must be cleared
        assert client._probe_backoff_until is None
        assert client._probe_fail_count == 0
        assert client._has_system_log is None  # re-probed on next poll

    @pytest.mark.asyncio
    async def test_reauth_does_not_reset_confirmed_true(self):
        """If _has_system_log is True (v2 endpoint confirmed), re-auth must not
        reset it to None - there's nothing to re-probe."""
        from datetime import timedelta

        client = make_client()
        client._has_system_log = True
        client._probe_fail_count = 0
        client._probe_backoff_until = None

        login_ctx = _make_response(200)
        client._session.post = login_ctx
        await client.authenticate()

        assert client._has_system_log is True


class TestFetchSystemLogAlarms:
    """Tests for UniFiClient.fetch_system_log_alarms."""

    def _make_page_response(self, events: list[dict], total_pages: int, page: int = 0):
        """Build a mock POST response for one system-log/all page."""
        body = {
            "data": events,
            "page_number": page,
            "total_element_count": len(events),
            "total_page_count": total_pages,
        }
        ctx, resp = _make_post_json_response(200, body)
        return ctx, resp

    @pytest.mark.asyncio
    async def test_returns_new_events_only(self):
        """Only events with status='NEW' must be returned; others are filtered."""
        client = make_client()
        client._authenticated = True
        events = [
            {"key": "THREAT_BLOCKED", "status": "NEW", "timestamp": 1778025612345},
            {"key": "THREAT_BLOCKED", "status": "ARCHIVED", "timestamp": 1778025612000},
        ]
        ctx, _ = self._make_page_response(events, total_pages=1)
        client._session.post = ctx
        result = await client.fetch_system_log_alarms()
        assert len(result) == 1
        assert result[0]["status"] == "NEW"

    @pytest.mark.asyncio
    async def test_paginates_until_total_pages_exhausted(self):
        """Must fetch pages until total_page_count is reached."""
        client = make_client()
        client._authenticated = True

        call_count = [0]

        @asynccontextmanager
        async def _paginated(*args, **kwargs):
            call_count[0] += 1
            page = call_count[0] - 1
            body = {
                "data": [{"key": "K", "status": "NEW", "timestamp": 1000}],
                "page_number": page,
                "total_element_count": 3,
                "total_page_count": 3,
            }
            resp = MagicMock()
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value=body)
            yield resp

        client._session.post = _paginated
        result = await client.fetch_system_log_alarms()
        assert call_count[0] == 3
        assert len(result) == 3  # one NEW event per page

    @pytest.mark.asyncio
    async def test_stops_at_max_pages_cap(self):
        """Must stop after MAX_SYSTEM_LOG_PAGES even if total_page_count is larger."""
        from custom_components.unifi_alerts.const import MAX_SYSTEM_LOG_PAGES

        client = make_client()
        client._authenticated = True

        call_count = [0]

        @asynccontextmanager
        async def _many_pages(*args, **kwargs):
            call_count[0] += 1
            body = {
                "data": [{"key": "K", "status": "NEW", "timestamp": 1000}],
                "page_number": call_count[0] - 1,
                "total_element_count": 9999,
                "total_page_count": 9999,  # more than MAX_SYSTEM_LOG_PAGES
            }
            resp = MagicMock()
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value=body)
            yield resp

        client._session.post = _many_pages
        await client.fetch_system_log_alarms()
        assert call_count[0] == MAX_SYSTEM_LOG_PAGES, (
            f"Expected exactly {MAX_SYSTEM_LOG_PAGES} page fetches; got {call_count[0]}"
        )

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self):
        """Must stop when a page returns an empty data list."""
        client = make_client()
        client._authenticated = True

        call_count = [0]

        @asynccontextmanager
        async def _empty_second_page(*args, **kwargs):
            call_count[0] += 1
            data = [{"key": "K", "status": "NEW", "timestamp": 1000}] if call_count[0] == 1 else []
            body = {
                "data": data,
                "page_number": call_count[0] - 1,
                "total_element_count": 1,
                "total_page_count": 99,  # large total — early stop on empty page
            }
            resp = MagicMock()
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value=body)
            yield resp

        client._session.post = _empty_second_page
        result = await client.fetch_system_log_alarms()
        assert call_count[0] == 2  # first page + one empty page
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_passes_timestamp_from_as_epoch_ms(self):
        """timestampFrom must be epoch milliseconds derived from the since datetime."""
        from datetime import UTC, datetime

        client = make_client()
        client._authenticated = True

        captured_body: list[dict] = []

        @asynccontextmanager
        async def _capturing(*args, **kwargs):
            captured_body.append(kwargs.get("json", {}))
            body = {"data": [], "page_number": 0, "total_element_count": 0, "total_page_count": 1}
            resp = MagicMock()
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value=body)
            yield resp

        client._session.post = _capturing

        since = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        expected_ms = int(since.timestamp() * 1000)
        await client.fetch_system_log_alarms(since=since)

        assert captured_body, "Expected at least one POST call"
        assert captured_body[0]["timestampFrom"] == expected_ms, (
            f"Expected timestampFrom={expected_ms}, got {captured_body[0].get('timestampFrom')}"
        )

    @pytest.mark.asyncio
    async def test_uses_default_lookback_when_no_since(self):
        """When since=None, timestampFrom must be approximately now - DEFAULT lookback."""
        from datetime import UTC, datetime, timedelta

        from custom_components.unifi_alerts.const import DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS

        client = make_client()
        client._authenticated = True

        captured_body: list[dict] = []

        @asynccontextmanager
        async def _capturing(*args, **kwargs):
            captured_body.append(kwargs.get("json", {}))
            body = {"data": [], "page_number": 0, "total_element_count": 0, "total_page_count": 1}
            resp = MagicMock()
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.json = AsyncMock(return_value=body)
            yield resp

        client._session.post = _capturing
        await client.fetch_system_log_alarms(since=None)

        expected_approx_ms = int(
            (datetime.now(UTC) - timedelta(hours=DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS)).timestamp()
            * 1000
        )
        actual_ms = captured_body[0]["timestampFrom"]
        # Allow 5-second slack for test execution time
        assert abs(actual_ms - expected_approx_ms) < 5000, (
            f"timestampFrom {actual_ms} deviates too far from expected {expected_approx_ms}"
        )

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth(self):
        """HTTP 401 during system-log fetch must raise InvalidAuthError."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(401)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_network_error_raises_cannot_connect(self):
        """aiohttp.ClientError during fetch must raise CannotConnectError."""
        import aiohttp

        client = make_client()
        client._authenticated = True

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("unreachable")
            yield

        client._session.post = _raise
        with pytest.raises(CannotConnectError):
            await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """3xx from the system-log endpoint must raise CannotConnectError."""
        client = make_client()
        client._authenticated = True
        ctx, _ = _make_post_json_response(301)
        client._session.post = ctx
        with pytest.raises(CannotConnectError, match="redirect"):
            await client.fetch_system_log_alarms()
