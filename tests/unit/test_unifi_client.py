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


class TestNetworkPath:
    def test_non_unifi_os_path_unchanged(self):
        client = make_client()
        client._is_unifi_os = False
        assert client._network_path("/api/s/default/alarm") == "/api/s/default/alarm"

    def test_unifi_os_adds_proxy_prefix(self):
        client = make_client()
        client._is_unifi_os = True
        assert client._network_path("/api/s/default/alarm") == "/proxy/network/api/s/default/alarm"


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


class TestDetectUnifiOs:
    """Tests for _detect_unifi_os."""

    @pytest.mark.asyncio
    async def test_returns_true_when_csrf_token_present(self):
        """Should return True when the response (possibly after redirect) has x-csrf-token."""
        client = make_client()
        ctx = _make_response(200, headers={"x-csrf-token": "abc123"})
        client._session.get = ctx
        result = await client._detect_unifi_os()
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_csrf_token_absent_and_system_probe_fails(self):
        """Should return False when x-csrf-token absent and /api/system probe returns non-200."""
        client = make_client()

        @asynccontextmanager
        async def _ctx(*args, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.status = 404  # neither / nor /api/system indicates UniFi OS
            yield resp

        client._session.get = _ctx
        result = await client._detect_unifi_os()
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_fallback_system_probe_200(self):
        """Should return True when x-csrf-token absent but /api/system returns 200."""
        client = make_client()

        call_count = [0]

        @asynccontextmanager
        async def _ctx(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.headers = {}
            resp.status = 200  # / has no csrf token; /api/system returns 200 → UniFi OS
            yield resp

        client._session.get = _ctx
        result = await client._detect_unifi_os()
        assert result is True
        assert call_count[0] == 2  # primary probe + fallback probe

    @pytest.mark.asyncio
    async def test_follows_redirects(self):
        """allow_redirects=True: final response after redirect is inspected."""
        client = make_client()
        # Simulate: after following redirect the final response has the token
        ctx = _make_response(200, headers={"x-csrf-token": "redirected-token"})
        client._session.get = ctx
        result = await client._detect_unifi_os()
        assert result is True

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        """Network errors during detection should return False (graceful fallback)."""
        import aiohttp

        client = make_client()

        @asynccontextmanager
        async def _raise(*args, **kwargs):
            raise aiohttp.ClientConnectionError("unreachable")
            yield  # make it a generator

        client._session.get = _raise
        result = await client._detect_unifi_os()
        assert result is False


class TestLoginUserpass:
    """Tests for _login_userpass error handling."""

    @pytest.mark.asyncio
    async def test_http_400_raises_cannot_connect(self):
        """HTTP 400 from the controller must raise CannotConnectError, not InvalidAuthError.

        UCG-Ultra returns 400 for request format / endpoint mismatch — this is
        NOT a credentials problem, so we must not show 'invalid credentials'.
        """
        client = make_client()
        client._is_unifi_os = False
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
        client._is_unifi_os = False

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
        client._is_unifi_os = False
        ctx = _make_response(401)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await client._login_userpass()

    @pytest.mark.asyncio
    async def test_http_403_raises_invalid_auth(self):
        """HTTP 403 should still raise InvalidAuthError (bad credentials)."""
        client = make_client()
        client._is_unifi_os = False
        ctx = _make_response(403)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError):
            await client._login_userpass()

    @pytest.mark.asyncio
    async def test_invalid_auth_error_carries_login_url(self):
        """InvalidAuthError raised after both paths fail must carry login_url attribute."""
        client = make_client()
        client._is_unifi_os = False
        ctx = _make_response(401)
        client._session.post = ctx
        with pytest.raises(InvalidAuthError) as exc_info:
            await client._login_userpass()
        # Alternate path (/api/auth/login) is the last tried for a non-OS client.
        assert exc_info.value.login_url.endswith("/api/auth/login")

    @pytest.mark.asyncio
    async def test_fallback_path_succeeds_on_ucg_ultra(self):
        """When the primary path returns 401, the alternate path is tried.

        Simulates a UCG-Ultra where _is_unifi_os=False (detection miss), so the
        primary path is /api/login (returns 401) and the fallback /api/auth/login
        succeeds (returns 200).
        """
        client = make_client()
        client._is_unifi_os = False

        responses = iter([401, 200])

        @asynccontextmanager
        async def _varying_post(*args, **kwargs):
            status = next(responses)
            resp = MagicMock()
            resp.status = status
            resp.raise_for_status = MagicMock()
            yield resp

        client._session.post = _varying_post
        # Should not raise — the fallback path succeeded
        await client._login_userpass()


class TestVerifyApiKey:
    """Tests for _verify_api_key — API key authentication and endpoint selection."""

    @pytest.mark.asyncio
    async def test_always_uses_proxy_network_prefix(self):
        """_verify_api_key must always use /proxy/network regardless of OS detection result.

        API keys are UniFi OS-only, so the /proxy/network prefix is always correct.
        Trusting _detect_unifi_os here caused 404s on UCG-Ultra and reverse proxies.
        """
        client = make_client({"api_key": "my-key", "verify_ssl": False})
        client._is_unifi_os = False  # simulate failed OS detection

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
        client._is_unifi_os = False
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
        client._is_unifi_os = False
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
        client._is_unifi_os = True

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
    async def test_tries_bare_alarm_path_first(self):
        """fetch_alarms must try bare /alarm before the /stat/alarm fallback.

        /alarm is more universally supported across firmware versions; /stat/alarm
        is kept as a fallback for firmware that only exposes that variant.
        """
        client = make_client()
        client._authenticated = True
        client._is_unifi_os = True

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
        assert first_url.endswith("/alarm") and not first_url.endswith("/stat/alarm"), (
            f"First URL tried must end with bare /alarm; got: {first_url}"
        )
        # Only one call expected — /alarm worked, no fallback needed
        assert len(captured_urls) == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_stat_alarm_on_404(self):
        """fetch_alarms must try /stat/alarm when bare /alarm returns 404.

        Some controller firmware versions expose /stat/alarm but not bare /alarm.
        The fallback ensures the integration works across firmware versions.
        """
        client = make_client()
        client._authenticated = True
        client._is_unifi_os = True

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
    async def test_falls_back_to_stat_alarm_on_400_invalid_object(self):
        """fetch_alarms must try /stat/alarm when bare /alarm returns 400 api.err.InvalidObject.

        Some firmware returns 400 + api.err.InvalidObject for endpoint paths that don't
        exist on that firmware version (instead of the more conventional 404).  The
        integration must treat this the same as 404 and try the next path.
        """
        client = make_client()
        client._authenticated = True
        client._is_unifi_os = True

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
        client._is_unifi_os = True
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
        client._is_unifi_os = True
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
        client._is_unifi_os = False
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


class TestCategoriseAlarms:
    """Tests for UniFiClient.categorise_alarms."""

    @pytest.mark.asyncio
    async def test_groups_alarms_by_category(self):
        client = make_client()
        client._authenticated = True
        client._is_unifi_os = False
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
        client._is_unifi_os = False
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
        client._is_unifi_os = False
        ctx, _ = _make_json_response(200, {"meta": {"rc": "ok"}, "data": []})
        client._session.get = ctx
        result = await client.categorise_alarms()
        assert result == {}


class TestAuthenticate:
    """Tests for UniFiClient.authenticate — auth method selection and fallback."""

    @pytest.mark.asyncio
    async def test_apikey_method_used_when_configured(self):
        client = make_client({"api_key": "my-key", "auth_method": "apikey", "verify_ssl": False})
        ctx_detect = _make_response(200, headers={})  # not UniFi OS
        client._session.get = ctx_detect

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
        ctx_detect = _make_response(200, headers={})
        client._session.get = ctx_detect

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
        ctx_detect = _make_response(200, headers={})
        client._session.get = ctx_detect

        async def _bad_verify():
            raise InvalidAuthError("bad key")

        client._verify_api_key = _bad_verify
        with pytest.raises(InvalidAuthError):
            await client.authenticate()

    @pytest.mark.asyncio
    async def test_apikey_success_coerces_is_unifi_os_true(self):
        """Successful API-key auth must force _is_unifi_os=True.

        API keys are UniFi OS-only by construction, so a successful verify proves
        the controller is UniFi OS — even if _detect_unifi_os() returned a false
        negative (e.g. UCG-Ultra with no x-csrf-token and /api/system not 200).
        Without this coercion, later network calls like fetch_alarms() would
        drop the /proxy/network prefix and 404 on the very controller that just
        accepted the API key.
        """
        from custom_components.unifi_alerts.const import AUTH_METHOD_APIKEY

        client = make_client(
            {"api_key": "my-key", "auth_method": AUTH_METHOD_APIKEY, "verify_ssl": False}
        )
        client._is_unifi_os = False  # simulate detection false-negative

        async def _detect_returns_false() -> bool:
            return False

        client._detect_unifi_os = _detect_returns_false  # type: ignore[method-assign]
        client._verify_api_key = AsyncMock()  # verify succeeds

        # Re-set to None so authenticate() runs detection (which returns False)
        client._is_unifi_os = None
        result = await client.authenticate()

        assert result == AUTH_METHOD_APIKEY
        assert client._is_unifi_os is True, (
            "API-key success must override false-negative OS detection"
        )

    @pytest.mark.asyncio
    async def test_fetch_alarms_after_apikey_auth_uses_proxy_path(self):
        """End-to-end: detection false-negative → API-key auth → fetch_alarms hits /proxy/network.

        Reproduces the reported 'Cannot reach alarm endpoint: ClientResponseError' bug:
        detection says non-OS, API-key auth succeeds (hard-coded to /proxy/network), then
        fetch_alarms must use /proxy/network too (not the bare /api/s/... path).
        """
        from custom_components.unifi_alerts.const import AUTH_METHOD_APIKEY

        client = make_client(
            {"api_key": "my-key", "auth_method": AUTH_METHOD_APIKEY, "verify_ssl": False}
        )

        async def _detect_returns_false() -> bool:
            return False

        client._detect_unifi_os = _detect_returns_false  # type: ignore[method-assign]
        client._verify_api_key = AsyncMock()

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

        await client.authenticate()
        await client.fetch_alarms()

        assert captured_urls, "Expected at least one GET call to the alarm endpoint"
        alarm_url = captured_urls[-1]
        assert "/proxy/network/api/s/default/" in alarm_url and "/alarm" in alarm_url, (
            f"After API-key auth, fetch_alarms must use /proxy/network path; got: {alarm_url}"
        )


class TestClose:
    """Tests for UniFiClient.close — logout behavior.

    close() calls ``await session.post(url, ...)`` without an async-with block,
    so the mock must be a plain AsyncMock (coroutine), not an asynccontextmanager.
    """

    @pytest.mark.asyncio
    async def test_userpass_auth_posts_logout(self):
        client = make_client()
        client._auth_method = "userpass"
        client._authenticated = True
        client._is_unifi_os = False
        client._session.post = AsyncMock()
        await client.close()
        client._session.post.assert_awaited_once()
        url_called = client._session.post.call_args[0][0]
        assert "/api/logout" in url_called

    @pytest.mark.asyncio
    async def test_unifi_os_userpass_uses_different_logout_path(self):
        client = make_client()
        client._auth_method = "userpass"
        client._authenticated = True
        client._is_unifi_os = True
        client._session.post = AsyncMock()
        await client.close()
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


class TestIsUnifiOsPersistence:
    """Tests for the CONF_IS_UNIFI_OS persistence behaviour."""

    def test_is_unifi_os_none_when_not_in_config(self):
        """When CONF_IS_UNIFI_OS is absent from config, _is_unifi_os starts as None."""
        client = make_client()
        assert client._is_unifi_os is None

    def test_is_unifi_os_loaded_from_config_true(self):
        """When CONF_IS_UNIFI_OS=True is in config, _is_unifi_os is pre-set to True."""
        from custom_components.unifi_alerts.const import CONF_IS_UNIFI_OS

        client = make_client({**{"username": "admin", "password": "pw", "verify_ssl": False}, CONF_IS_UNIFI_OS: True})
        assert client._is_unifi_os is True

    def test_is_unifi_os_loaded_from_config_false(self):
        """When CONF_IS_UNIFI_OS=False is in config, _is_unifi_os is pre-set to False."""
        from custom_components.unifi_alerts.const import CONF_IS_UNIFI_OS

        client = make_client({**{"username": "admin", "password": "pw", "verify_ssl": False}, CONF_IS_UNIFI_OS: False})
        assert client._is_unifi_os is False

    @pytest.mark.asyncio
    async def test_skips_detection_when_is_unifi_os_in_config(self):
        """authenticate() must not call _detect_unifi_os() when CONF_IS_UNIFI_OS is pre-set."""
        from custom_components.unifi_alerts.const import AUTH_METHOD_APIKEY, CONF_IS_UNIFI_OS

        config = {
            "api_key": "test-key",
            "auth_method": AUTH_METHOD_APIKEY,
            "verify_ssl": False,
            CONF_IS_UNIFI_OS: True,
        }
        client = make_client(config)
        assert client._is_unifi_os is True

        detection_calls: list[int] = []

        async def _no_detect() -> bool:
            detection_calls.append(1)
            return False

        client._detect_unifi_os = _no_detect  # type: ignore[method-assign]
        client._verify_api_key = AsyncMock()
        await client.authenticate()

        assert detection_calls == [], "_detect_unifi_os must not be called when value is loaded from config"
        assert client._is_unifi_os is True  # stored value preserved, not overwritten

    @pytest.mark.asyncio
    async def test_runs_detection_when_is_unifi_os_not_in_config(self):
        """authenticate() must call _detect_unifi_os() when _is_unifi_os is None."""
        from custom_components.unifi_alerts.const import AUTH_METHOD_APIKEY

        client = make_client({"api_key": "test-key", "auth_method": AUTH_METHOD_APIKEY, "verify_ssl": False})
        assert client._is_unifi_os is None

        detection_calls: list[int] = []

        async def _mock_detect() -> bool:
            detection_calls.append(1)
            return True

        client._detect_unifi_os = _mock_detect  # type: ignore[method-assign]
        client._verify_api_key = AsyncMock()
        await client.authenticate()

        assert len(detection_calls) == 1
        assert client._is_unifi_os is True
