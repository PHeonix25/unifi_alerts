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
    async def test_returns_false_when_csrf_token_absent(self):
        """Should return False when x-csrf-token is not in response headers, even if HTTP 200."""
        client = make_client()
        ctx = _make_response(200, headers={})
        client._session.get = ctx
        result = await client._detect_unifi_os()
        assert result is False

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
            "data": [
                {"key": "EVT_GW_WANTransition", "archived": False},
                {"key": "EVT_AP_Disconnected", "archived": True},  # should be filtered
            ]
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
        body = {"data": [{"key": "EVT_GW_WANTransition", "archived": True}]}
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
    async def test_not_authenticated_calls_authenticate_first(self):
        """fetch_alarms must call authenticate() when not yet authenticated."""
        client = make_client()
        client._authenticated = False
        # authenticate() is called; after it the client should be marked as authenticated
        # so we patch authenticate to set _authenticated=True and return
        body = {"data": [{"key": "EVT_GW_WANTransition", "archived": False}]}
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
            "data": [
                {"key": "EVT_GW_WANTransition", "msg": "WAN down", "archived": False},
                {"key": "EVT_IPS_ThreatDetected", "msg": "Threat", "archived": False},
                {"key": "EVT_GW_Failover", "msg": "Failover", "archived": False},
            ]
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
            "data": [
                {"key": "EVT_UNKNOWN_THING", "msg": "who knows", "archived": False},
            ]
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
        ctx, _ = _make_json_response(200, {"data": []})
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
