"""Tests for the UniFi HTTP client: classify, legacy fetch_alarms/categorise_alarms, auth, close, SSL.

Split by behaviour area (#283) alongside test_v2.py (the v2 system-log
probe/fetch path) in this package.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_CLIENT,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_POWER,
    CATEGORY_SECURITY_FIREWALL,
    CATEGORY_SECURITY_HONEYPOT,
    CATEGORY_SECURITY_THREAT,
)
from custom_components.unifi_alerts.unifi_auth import CannotConnectError, InvalidAuthError
from custom_components.unifi_alerts.unifi_client import UniFiClient

from .conftest import (
    alarm_url,
    find_calls,
    list_alarm_url,
    make_client,
    stat_alarm_url,
    system_log_url,
    total_calls,
)


class TestClassify:
    """Test the static _classify method for event key → category mapping."""

    @pytest.mark.parametrize(
        ("key", "expected"),
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


class TestFetchAlarms:
    """Tests for UniFiClient.fetch_alarms."""

    @pytest.mark.asyncio
    async def test_returns_non_archived_alarms(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "archived": False},
                {"key": "EVT_AP_Disconnected", "archived": True},  # should be filtered
            ],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        alarms = await client.fetch_alarms()
        assert len(alarms) == 1
        assert alarms[0]["key"] == "EVT_GW_WANTransition"

    @pytest.mark.asyncio
    async def test_filters_out_archived_alarms(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {"meta": {"rc": "ok"}, "data": [{"key": "EVT_GW_WANTransition", "archived": True}]}
        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        alarms = await client.fetch_alarms()
        assert alarms == []

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth(self, aioclient_mock: AiohttpClientMocker):
        """A 401 on the alarm fetch (revoked API key) must raise InvalidAuthError."""
        client = make_client(aioclient_mock)
        aioclient_mock.get(list_alarm_url(), status=401)
        with pytest.raises(InvalidAuthError):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_client_error_raises_cannot_connect(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        aioclient_mock.get(list_alarm_url(), exc=aiohttp.ClientConnectionError("unreachable"))
        with pytest.raises(CannotConnectError):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_client_error_message_is_class_name_not_url(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """CannotConnectError message must be the exception class name, not str(err).

        aiohttp exceptions can embed the controller URL (including credentials) in
        their string representation.  Using type(err).__name__ prevents credential
        leaks via HA log output.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        aioclient_mock.get(
            list_alarm_url(),
            exc=aiohttp.ClientConnectionError("https://admin:secret@192.168.1.1/api"),
        )
        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()
        assert "secret" not in str(exc_info.value)
        assert exc_info.value.args[0] == "ClientConnectionError"

    @pytest.mark.asyncio
    async def test_response_error_preserves_status_code_in_message(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """A ClientResponseError (e.g. 503) must surface its status code in the error.

        Before this test existed, the handler wrapped all aiohttp errors as
        ``CannotConnectError(type(err).__name__)``, which produced the opaque
        'Cannot reach alarm endpoint: ClientResponseError' log line with no
        status code. Status code only — no URL — to avoid leaking credentials
        that may be embedded in a misconfigured controller URL.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        aioclient_mock.get(list_alarm_url(), status=503)
        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()

        message = str(exc_info.value)
        assert "503" in message, f"Status code must be in the error message; got: {message!r}"
        assert "ClientResponseError" in message, (
            f"Exception class name must be in the error message; got: {message!r}"
        )

    @pytest.mark.asyncio
    async def test_tries_list_alarm_path_first(self, aioclient_mock: AiohttpClientMocker):
        """fetch_alarms must try /list/alarm before any older path.

        /list/alarm is the newest UniFi Network endpoint (9.x+); the older /alarm
        and /stat/alarm paths are kept as fallbacks so the integration keeps
        working on older firmware. See docs/UNIFI.md § "Alarm API endpoint".
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        aioclient_mock.get(list_alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        await client.fetch_alarms()
        list_calls = find_calls("GET", list_alarm_url())
        total = total_calls()

        assert len(list_calls) == 1, "Expected exactly one GET to /list/alarm"
        # Only one call expected — /list/alarm worked, no fallback needed
        assert total == 1

    @pytest.mark.asyncio
    async def test_fetch_alarms_uses_proxy_network_path(self, aioclient_mock: AiohttpClientMocker):
        """fetch_alarms must always use the /proxy/network prefix for all alarm paths."""
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        expected_url = list_alarm_url()
        assert "/proxy/network/api/s/default/" in expected_url

        aioclient_mock.get(expected_url, status=200, json={"meta": {"rc": "ok"}, "data": []})
        await client.fetch_alarms()
        calls = find_calls("GET", expected_url)

        assert len(calls) == 1, f"fetch_alarms must GET {expected_url} exactly once"

    @pytest.mark.asyncio
    async def test_falls_back_through_full_path_chain(self, aioclient_mock: AiohttpClientMocker):
        """fetch_alarms must walk the full path chain when each preceding path is missing.

        Order is: /list/alarm (newest) → /alarm → /stat/alarm (oldest). A 404 on each
        of the first two must continue to the next; the third must succeed. This guards
        against future regressions if someone reorders or drops an entry from
        ``alarm_paths`` without updating both code and docs.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True

        aioclient_mock.get(list_alarm_url(), status=404)
        aioclient_mock.get(alarm_url(), status=404)
        aioclient_mock.get(stat_alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        result = await client.fetch_alarms()

        assert len(find_calls("GET", list_alarm_url())) == 1
        assert len(find_calls("GET", alarm_url())) == 1
        assert len(find_calls("GET", stat_alarm_url())) == 1
        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_next_path_on_404(self, aioclient_mock: AiohttpClientMocker):
        """fetch_alarms must try the next path when the current one returns 404.

        Verifies the basic fallback contract for any single-step transition in the
        chain. The first path returns 404, the second returns success.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True

        aioclient_mock.get(list_alarm_url(), status=404)
        aioclient_mock.get(alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        result = await client.fetch_alarms()
        total = total_calls()

        assert total == 2, "Expected exactly two GET calls (primary + fallback)"
        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_next_path_on_400_invalid_object(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """fetch_alarms must try the next path on 400 api.err.InvalidObject.

        Some firmware returns 400 + api.err.InvalidObject for endpoint paths that don't
        exist on that firmware version (instead of the more conventional 404).  The
        integration must treat this the same as 404 and try the next path.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        invalid_body = {"meta": {"rc": "error", "msg": "api.err.InvalidObject"}, "data": []}

        aioclient_mock.get(list_alarm_url(), status=400, json=invalid_body)
        aioclient_mock.get(alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        result = await client.fetch_alarms()
        total = total_calls()

        assert total == 2, "Expected exactly two GET calls (primary + fallback)"
        assert result == []

    @pytest.mark.asyncio
    async def test_all_paths_404_raises_invalid_site_error(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """When all alarm paths return 404, raise InvalidSiteError (subclass of CannotConnectError)."""
        from custom_components.unifi_alerts.unifi_client import InvalidSiteError

        client = make_client(aioclient_mock)
        client._auth._authenticated = True

        aioclient_mock.get(list_alarm_url(), status=404)
        aioclient_mock.get(alarm_url(), status=404)
        aioclient_mock.get(stat_alarm_url(), status=404)
        with pytest.raises(InvalidSiteError, match="not found on the controller"):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_http_400_raises_cannot_connect_with_site_hint(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """HTTP 400 (non-InvalidObject) from the alarm endpoint raises CannotConnectError.

        A 400 with any error other than api.err.InvalidObject means a genuine rejection
        (e.g. wrong site name).  The error message must name the site so the user knows
        what to check.  api.err.InvalidObject is treated as "path not found" (see separate
        test) and causes a fallback rather than an immediate error.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        # Return 400 with a non-InvalidObject body so the path isn't treated as "not found"
        bad_body = {"meta": {"rc": "error", "msg": "api.err.Invalid"}, "data": []}

        aioclient_mock.get(list_alarm_url(), status=400, json=bad_body)
        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()

        message = str(exc_info.value)
        assert "400" in message
        assert "default" in message  # site name is mentioned so user knows what to check

    @pytest.mark.asyncio
    async def test_http_400_with_unparseable_body_still_raises_cannot_connect(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """A 400 response whose body isn't valid JSON must not crash — CannotConnectError still raises.

        _try_fetch_alarms tries to parse the 400 body to detect api.err.InvalidObject
        (path-not-found) vs. a genuine rejection. If the body itself can't be parsed
        as JSON, that lookup must fail closed (treated as a genuine 400, not silently
        swallowed) rather than propagating the JSONDecodeError. Registering a raw,
        non-JSON ``text`` (rather than ``json``) makes ``resp.json()`` raise naturally.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True

        aioclient_mock.get(list_alarm_url(), status=400, text="not valid json")
        with pytest.raises(CannotConnectError) as exc_info:
            await client.fetch_alarms()

        message = str(exc_info.value)
        assert "400" in message
        assert "default" in message

    @pytest.mark.asyncio
    async def test_api_error_response_raises_cannot_connect(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """HTTP 200 with meta.rc != 'ok' must raise CannotConnectError.

        The UniFi controller returns HTTP 200 even for API-level errors; only
        meta.rc distinguishes success from failure.  Silently returning [] would
        hide misconfigured site names and similar problems from the user.
        """
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {"meta": {"rc": "error", "msg": "api.err.InvalidObject"}, "data": []}

        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        with pytest.raises(CannotConnectError, match=r"api\.err\.InvalidObject"):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self, aioclient_mock: AiohttpClientMocker):
        """A 3xx on an authenticated alarm fetch must raise CannotConnectError (no redirect)."""
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        aioclient_mock.get(list_alarm_url(), status=301)
        with pytest.raises(CannotConnectError, match="redirect"):
            await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_sends_x_api_key_header_and_correct_url_method(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """The outbound GET to /list/alarm must carry the X-API-Key header from apikey auth.

        Asserts against the recorded request history (method, URL, headers) —
        i.e. the HTTP the client actually sent to aiohttp — rather than a
        mock's internal call_args, so this catches regressions in the real
        auth-header wiring, not just the client's internal call sequence.
        """
        client = make_client(aioclient_mock, {"api_key": "s3cr3t-key", "verify_ssl": False})
        client._auth._method = "apikey"
        client._auth._authenticated = True

        aioclient_mock.get(list_alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        await client.fetch_alarms()
        calls = find_calls("GET", list_alarm_url())

        assert len(calls) == 1, "Expected exactly one GET to /list/alarm"
        sent_headers = calls[0].kwargs.get("headers") or {}
        assert sent_headers.get("X-API-Key") == "s3cr3t-key"
        assert sent_headers.get("Accept") == "application/json"


class TestCategoriseAlarms:
    """Tests for UniFiClient.categorise_alarms."""

    @pytest.mark.asyncio
    async def test_groups_alarms_by_category(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "msg": "WAN down", "archived": False},
                {"key": "EVT_IPS_ThreatDetected", "msg": "Threat", "archived": False},
                {"key": "EVT_GW_Failover", "msg": "Failover", "archived": False},
            ],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        result = await client.categorise_alarms()

        assert CATEGORY_NETWORK_WAN in result
        assert CATEGORY_SECURITY_THREAT in result
        assert len(result[CATEGORY_NETWORK_WAN]) == 2  # both WAN events

    @pytest.mark.asyncio
    async def test_skips_unclassified_alarms(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_UNKNOWN_THING", "msg": "who knows", "archived": False},
            ],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        result = await client.categorise_alarms()
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_alarm_list_returns_empty_dict(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        aioclient_mock.get(list_alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        result = await client.categorise_alarms()
        assert result == {}

    @pytest.mark.asyncio
    async def test_unrecognised_keys_tracked_on_unclassified_alarm(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """categorise_alarms() must record unclassified alarm keys in unrecognised_keys."""
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_MYSTERY_DEVICE_FELL_OVER", "msg": "wat", "archived": False},
                {"key": "EVT_MYSTERY_DEVICE_FELL_OVER", "msg": "again", "archived": False},
                {"key": "EVT_ANOTHER_UNKNOWN", "msg": "hmm", "archived": False},
            ],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        await client.categorise_alarms()

        assert client.unrecognised_keys == {
            "EVT_MYSTERY_DEVICE_FELL_OVER": 2,
            "EVT_ANOTHER_UNKNOWN": 1,
        }

    @pytest.mark.asyncio
    async def test_unrecognised_keys_reset_between_calls(self, aioclient_mock: AiohttpClientMocker):
        """unrecognised_keys reflects only the most recent categorise_alarms() call."""
        client = make_client(aioclient_mock)
        client._auth._authenticated = True

        body1 = {
            "meta": {"rc": "ok"},
            "data": [{"key": "EVT_UNKNOWN_FIRST", "msg": ".", "archived": False}],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body1)
        await client.categorise_alarms()
        assert "EVT_UNKNOWN_FIRST" in client.unrecognised_keys

        aioclient_mock.clear_requests()
        body2 = {
            "meta": {"rc": "ok"},
            "data": [{"key": "EVT_UNKNOWN_SECOND", "msg": ".", "archived": False}],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body2)
        await client.categorise_alarms()

        # Only the second call's keys remain
        assert "EVT_UNKNOWN_SECOND" in client.unrecognised_keys
        assert "EVT_UNKNOWN_FIRST" not in client.unrecognised_keys

    @pytest.mark.asyncio
    async def test_unrecognised_keys_empty_when_all_classified(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """unrecognised_keys is empty when all alarms map to a category."""
        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "msg": "WAN down", "archived": False},
            ],
        }
        aioclient_mock.get(list_alarm_url(), status=200, json=body)
        await client.categorise_alarms()

        assert client.unrecognised_keys == {}


class TestAuthenticate:
    """Tests for UniFiClient.authenticate — delegates to UniFiAuth.authenticate().

    API-key verification is UniFiAuth's own behaviour and is covered by
    tests/unit/test_unifi_auth.py. These tests only cover what UniFiClient
    itself is responsible for: delegating to self._auth and resetting
    probe-backoff state on every successful verification.

    UniFiAuth is a composed collaborator here (not HTTP), so these stay on
    MagicMock/AsyncMock — out of scope for the aioclient_mock conversion.
    """

    @pytest.mark.asyncio
    async def test_delegates_to_auth(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth.authenticate = AsyncMock(return_value=None)

        result = await client.authenticate()

        assert result is None
        client._auth.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_propagates_auth_failure(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock)
        client._auth.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

        with pytest.raises(InvalidAuthError):
            await client.authenticate()


class TestClose:
    """close() is a stateless no-op: API-key auth has no session to log out."""

    @pytest.mark.asyncio
    async def test_close_makes_no_requests(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock, {"api_key": "k", "verify_ssl": False})

        # Nothing is registered on the mock — if close() made any request,
        # aioclient_mock would raise AssertionError for the unmatched call.
        await client.close()
        assert total_calls() == 0

    @pytest.mark.asyncio
    async def test_close_does_not_raise(self, aioclient_mock: AiohttpClientMocker):
        client = make_client(aioclient_mock, {"api_key": "k", "verify_ssl": False})
        # No pytest.raises — close() must always be safe to await.
        await client.close()


class TestSslFailOpen:
    """Verify that a missing CONF_VERIFY_SSL key falls back to DEFAULT_VERIFY_SSL (True).

    The fix changed all five ssl=self._config.get(CONF_VERIFY_SSL, False) call sites to
    use DEFAULT_VERIFY_SSL (True) as the fallback.  A missing key must now fail *closed*
    (SSL ON) rather than silently disabling certificate verification.
    """

    @pytest.mark.asyncio
    async def test_absent_verify_ssl_key_defaults_to_true_in_fetch_alarms(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """When CONF_VERIFY_SSL is absent from config, _try_fetch_alarms must pass ssl=True.

        Constructs a config dict with no verify_ssl key and asserts, via the
        recorded request history, that the ssl kwarg forwarded on the outbound
        request is DEFAULT_VERIFY_SSL (True), not False.
        """
        from custom_components.unifi_alerts.const import DEFAULT_VERIFY_SSL

        # Config deliberately omits verify_ssl
        config = {"username": "admin", "password": "secret"}
        client = make_client(aioclient_mock, config)
        client._auth._authenticated = True

        aioclient_mock.get(list_alarm_url(), status=200, json={"meta": {"rc": "ok"}, "data": []})
        await client.fetch_alarms()
        calls = find_calls("GET", list_alarm_url())

        assert len(calls) == 1, "Expected exactly one GET call"
        sent_ssl = calls[0].kwargs.get("ssl")
        assert sent_ssl is DEFAULT_VERIFY_SSL, (
            f"Expected ssl={DEFAULT_VERIFY_SSL!r} (DEFAULT_VERIFY_SSL) when key is absent, "
            f"got {sent_ssl!r}"
        )
        assert sent_ssl is True, "DEFAULT_VERIFY_SSL must be True — fail closed"


class TestSslCertificateError:
    """SslCertificateError is raised on TLS certificate failures, not CannotConnectError.

    Auth-layer certificate handling (_verify_api_key) is UniFiAuth's own
    behaviour and is covered by tests/unit/test_unifi_auth.py.
    These tests cover UniFiClient's own request paths.
    """

    @pytest.mark.asyncio
    async def test_try_fetch_alarms_raises_ssl_cert_error(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """aiohttp.ClientConnectorCertificateError in _try_fetch_alarms must raise SslCertificateError."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client(aioclient_mock)
        client._auth._authenticated = True
        url = "https://192.168.1.1/api/alarm"

        aioclient_mock.get(
            url,
            exc=aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock()),
        )
        with pytest.raises(SslCertificateError):
            await client._try_fetch_alarms(url, "default")

    @pytest.mark.asyncio
    async def test_fetch_system_log_alarms_raises_ssl_cert_error(
        self, aioclient_mock: AiohttpClientMocker
    ):
        """aiohttp.ClientConnectorCertificateError in fetch_system_log_alarms must raise SslCertificateError."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client(aioclient_mock)
        client._auth._authenticated = True

        aioclient_mock.post(
            system_log_url(),
            exc=aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock()),
        )
        with pytest.raises(SslCertificateError):
            await client.fetch_system_log_alarms()
