"""Tests for the UniFi HTTP client.

HTTP-hitting tests use aioresponses to mock at the aiohttp transport layer
(``aiohttp.ClientSession._request``) rather than hand-building fake response
objects. This means they exercise the real ``aiohttp.ClientSession``
request/response plumbing (headers, status codes, JSON parsing, exception
raising) instead of a fabricated surface that could drift from real aiohttp
behaviour, and assertions can be made against the outbound request itself
(URL, method, headers, body) via aioresponses' request history. See issue
#229.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp.resolver import ThreadedResolver
from aioresponses import aioresponses

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
from custom_components.unifi_alerts.unifi_client import (
    _PROBE_FAIL_LIMIT,
    UNIFI_OS_NETWORK_PREFIX,
    UniFiClient,
)

BASE_URL = "https://192.168.1.1"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
LOGOUT_URL = f"{BASE_URL}/api/auth/logout"


# Sessions created by make_client() during the current test, closed by the
# _close_client_sessions autouse fixture below. pytest-homeassistant-custom-component
# asserts no lingering threads/timers survive a test, and an unclosed
# aiohttp.ClientSession schedules its own cleanup on the loop's default
# executor, which trips that check — so every session made here must be
# closed before the test ends.
_created_sessions: list[aiohttp.ClientSession] = []


def make_client(config: dict | None = None) -> UniFiClient:
    """Build a UniFiClient wired to a real aiohttp.ClientSession.

    aioresponses patches ClientSession._request, so no real socket is ever
    opened here; using the real session (instead of a MagicMock) means these
    tests exercise actual aiohttp request/response plumbing rather than a
    hand-built double of it. The session is tracked for teardown by
    _close_client_sessions.

    Uses a TCPConnector pinned to ThreadedResolver rather than aiohttp's
    aiodns-backed default. No DNS lookup ever actually happens (aioresponses
    intercepts before the connector runs), but constructing and then closing
    an AsyncResolver spins up pycares' global shutdown thread on first use —
    a daemon thread that outlives the test and trips the HA test harness's
    "no lingering threads" check. ThreadedResolver has no such side effect.
    """
    connector = aiohttp.TCPConnector(resolver=ThreadedResolver())
    session = aiohttp.ClientSession(connector=connector)
    _created_sessions.append(session)
    cfg = config or {
        "username": "admin",
        "password": "password",
        "verify_ssl": False,
    }
    return UniFiClient(session, BASE_URL, cfg)


@pytest.fixture(autouse=True)
async def _close_client_sessions():
    """Close every aiohttp.ClientSession created via make_client() this test."""
    yield
    while _created_sessions:
        session = _created_sessions.pop()
        if not session.closed:
            await session.close()


def _list_alarm_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/list/alarm"


def _alarm_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/alarm"


def _stat_alarm_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/stat/alarm"


def _probe_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/count"


def _system_log_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/all"


def _find_calls(m: aioresponses, method: str, url: str) -> list:
    """Return the recorded request history for one (method, url) pair.

    Compares by string rather than by yarl.URL equality so this stays robust
    to aioresponses' internal key normalisation across versions.
    """
    calls: list = []
    for (recorded_method, recorded_url), call_list in m.requests.items():
        if recorded_method == method and str(recorded_url) == url:
            calls.extend(call_list)
    return calls


def _total_calls(m: aioresponses) -> int:
    return sum(len(v) for v in m.requests.values())


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


class TestFetchAlarms:
    """Tests for UniFiClient.fetch_alarms."""

    @pytest.mark.asyncio
    async def test_returns_non_archived_alarms(self):
        client = make_client()
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "archived": False},
                {"key": "EVT_AP_Disconnected", "archived": True},  # should be filtered
            ],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            alarms = await client.fetch_alarms()
        assert len(alarms) == 1
        assert alarms[0]["key"] == "EVT_GW_WANTransition"

    @pytest.mark.asyncio
    async def test_filters_out_archived_alarms(self):
        client = make_client()
        client._auth._authenticated = True
        body = {"meta": {"rc": "ok"}, "data": [{"key": "EVT_GW_WANTransition", "archived": True}]}
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            alarms = await client.fetch_alarms()
        assert alarms == []

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth_and_clears_authenticated(self):
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=401)
            with pytest.raises(InvalidAuthError):
                await client.fetch_alarms()
        assert client._auth._authenticated is False

    @pytest.mark.asyncio
    async def test_client_error_raises_cannot_connect(self):
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(_list_alarm_url(), exception=aiohttp.ClientConnectionError("unreachable"))
            with pytest.raises(CannotConnectError):
                await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_client_error_message_is_class_name_not_url(self):
        """CannotConnectError message must be the exception class name, not str(err).

        aiohttp exceptions can embed the controller URL (including credentials) in
        their string representation.  Using type(err).__name__ prevents credential
        leaks via HA log output.
        """
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(
                _list_alarm_url(),
                exception=aiohttp.ClientConnectionError("https://admin:secret@192.168.1.1/api"),
            )
            with pytest.raises(CannotConnectError) as exc_info:
                await client.fetch_alarms()
        assert "secret" not in str(exc_info.value)
        assert exc_info.value.args[0] == "ClientConnectionError"

    @pytest.mark.asyncio
    async def test_response_error_preserves_status_code_in_message(self):
        """A ClientResponseError (e.g. 503) must surface its status code in the error.

        Before this test existed, the handler wrapped all aiohttp errors as
        ``CannotConnectError(type(err).__name__)``, which produced the opaque
        'Cannot reach alarm endpoint: ClientResponseError' log line with no
        status code. Status code only — no URL — to avoid leaking credentials
        that may be embedded in a misconfigured controller URL.
        """
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=503)
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
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            await client.fetch_alarms()
            list_calls = _find_calls(m, "GET", _list_alarm_url())
            total = _total_calls(m)

        assert len(list_calls) == 1, "Expected exactly one GET to /list/alarm"
        # Only one call expected — /list/alarm worked, no fallback needed
        assert total == 1

    @pytest.mark.asyncio
    async def test_fetch_alarms_uses_proxy_network_path(self):
        """fetch_alarms must always use the /proxy/network prefix for all alarm paths."""
        client = make_client()
        client._auth._authenticated = True
        expected_url = _list_alarm_url()
        assert "/proxy/network/api/s/default/" in expected_url

        with aioresponses() as m:
            m.get(expected_url, status=200, payload={"meta": {"rc": "ok"}, "data": []})
            await client.fetch_alarms()
            calls = _find_calls(m, "GET", expected_url)

        assert len(calls) == 1, f"fetch_alarms must GET {expected_url} exactly once"

    @pytest.mark.asyncio
    async def test_falls_back_through_full_path_chain(self):
        """fetch_alarms must walk the full path chain when each preceding path is missing.

        Order is: /list/alarm (newest) → /alarm → /stat/alarm (oldest). A 404 on each
        of the first two must continue to the next; the third must succeed. This guards
        against future regressions if someone reorders or drops an entry from
        ``alarm_paths`` without updating both code and docs.
        """
        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=404)
            m.get(_alarm_url(), status=404)
            m.get(_stat_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            result = await client.fetch_alarms()

            assert len(_find_calls(m, "GET", _list_alarm_url())) == 1
            assert len(_find_calls(m, "GET", _alarm_url())) == 1
            assert len(_find_calls(m, "GET", _stat_alarm_url())) == 1

        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_next_path_on_404(self):
        """fetch_alarms must try the next path when the current one returns 404.

        Verifies the basic fallback contract for any single-step transition in the
        chain. The first path returns 404, the second returns success.
        """
        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=404)
            m.get(_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            result = await client.fetch_alarms()
            total = _total_calls(m)

        assert total == 2, "Expected exactly two GET calls (primary + fallback)"
        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_next_path_on_400_invalid_object(self):
        """fetch_alarms must try the next path on 400 api.err.InvalidObject.

        Some firmware returns 400 + api.err.InvalidObject for endpoint paths that don't
        exist on that firmware version (instead of the more conventional 404).  The
        integration must treat this the same as 404 and try the next path.
        """
        client = make_client()
        client._auth._authenticated = True
        invalid_body = {"meta": {"rc": "error", "msg": "api.err.InvalidObject"}, "data": []}

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=400, payload=invalid_body)
            m.get(_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            result = await client.fetch_alarms()
            total = _total_calls(m)

        assert total == 2, "Expected exactly two GET calls (primary + fallback)"
        assert result == []

    @pytest.mark.asyncio
    async def test_all_paths_404_raises_invalid_site_error(self):
        """When all alarm paths return 404, raise InvalidSiteError (subclass of CannotConnectError)."""
        from custom_components.unifi_alerts.unifi_client import InvalidSiteError

        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=404)
            m.get(_alarm_url(), status=404)
            m.get(_stat_alarm_url(), status=404)
            with pytest.raises(InvalidSiteError, match="not found on the controller"):
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
        client._auth._authenticated = True
        # Return 400 with a non-InvalidObject body so the path isn't treated as "not found"
        bad_body = {"meta": {"rc": "error", "msg": "api.err.Invalid"}, "data": []}

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=400, payload=bad_body)
            with pytest.raises(CannotConnectError) as exc_info:
                await client.fetch_alarms()

        message = str(exc_info.value)
        assert "400" in message
        assert "default" in message  # site name is mentioned so user knows what to check

    @pytest.mark.asyncio
    async def test_http_400_with_unparseable_body_still_raises_cannot_connect(self):
        """A 400 response whose body isn't valid JSON must not crash — CannotConnectError still raises.

        _try_fetch_alarms tries to parse the 400 body to detect api.err.InvalidObject
        (path-not-found) vs. a genuine rejection. If the body itself can't be parsed
        as JSON, that lookup must fail closed (treated as a genuine 400, not silently
        swallowed) rather than propagating the JSONDecodeError. Registering a raw,
        non-JSON ``body`` (rather than ``payload``) makes ``resp.json()`` raise
        naturally via real aiohttp JSON parsing.
        """
        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=400, body="not valid json")
            with pytest.raises(CannotConnectError) as exc_info:
                await client.fetch_alarms()

        message = str(exc_info.value)
        assert "400" in message
        assert "default" in message

    @pytest.mark.asyncio
    async def test_api_error_response_raises_cannot_connect(self):
        """HTTP 200 with meta.rc != 'ok' must raise CannotConnectError.

        The UniFi controller returns HTTP 200 even for API-level errors; only
        meta.rc distinguishes success from failure.  Silently returning [] would
        hide misconfigured site names and similar problems from the user.
        """
        client = make_client()
        client._auth._authenticated = True
        body = {"meta": {"rc": "error", "msg": "api.err.InvalidObject"}, "data": []}

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            with pytest.raises(CannotConnectError, match="api.err.InvalidObject"):
                await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_not_authenticated_calls_authenticate_first(self):
        """fetch_alarms must call authenticate() when not yet authenticated."""
        client = make_client()
        client._auth._authenticated = False
        body = {"meta": {"rc": "ok"}, "data": [{"key": "EVT_GW_WANTransition", "archived": False}]}

        authenticated_calls = []

        async def _mock_authenticate():
            client._auth._authenticated = True
            client._auth._method = "userpass"
            authenticated_calls.append(1)

        client.authenticate = _mock_authenticate

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            await client.fetch_alarms()

        assert len(authenticated_calls) == 1

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """A 3xx on an authenticated alarm fetch must raise CannotConnectError (no redirect)."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=301)
            with pytest.raises(CannotConnectError, match="redirect"):
                await client.fetch_alarms()

    @pytest.mark.asyncio
    async def test_sends_x_api_key_header_and_correct_url_method(self):
        """The outbound GET to /list/alarm must carry the X-API-Key header from apikey auth.

        Asserts against aioresponses' recorded request history (method, URL,
        headers) — i.e. the HTTP the client actually sent on the wire — rather
        than a mock's internal call_args, so this catches regressions in the
        real auth-header wiring, not just the client's internal call sequence.
        """
        client = make_client({"api_key": "s3cr3t-key", "verify_ssl": False})
        client._auth._method = "apikey"
        client._auth._authenticated = True

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            await client.fetch_alarms()
            calls = _find_calls(m, "GET", _list_alarm_url())

        assert len(calls) == 1, "Expected exactly one GET to /list/alarm"
        sent_headers = calls[0].kwargs.get("headers") or {}
        assert sent_headers.get("X-API-Key") == "s3cr3t-key"
        assert sent_headers.get("Accept") == "application/json"


class TestCategoriseAlarms:
    """Tests for UniFiClient.categorise_alarms."""

    @pytest.mark.asyncio
    async def test_groups_alarms_by_category(self):
        client = make_client()
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "msg": "WAN down", "archived": False},
                {"key": "EVT_IPS_ThreatDetected", "msg": "Threat", "archived": False},
                {"key": "EVT_GW_Failover", "msg": "Failover", "archived": False},
            ],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            result = await client.categorise_alarms()

        assert CATEGORY_NETWORK_WAN in result
        assert CATEGORY_SECURITY_THREAT in result
        assert len(result[CATEGORY_NETWORK_WAN]) == 2  # both WAN events

    @pytest.mark.asyncio
    async def test_skips_unclassified_alarms(self):
        client = make_client()
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_UNKNOWN_THING", "msg": "who knows", "archived": False},
            ],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            result = await client.categorise_alarms()
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_alarm_list_returns_empty_dict(self):
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            result = await client.categorise_alarms()
        assert result == {}

    @pytest.mark.asyncio
    async def test_unrecognised_keys_tracked_on_unclassified_alarm(self):
        """categorise_alarms() must record unclassified alarm keys in unrecognised_keys."""
        client = make_client()
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_MYSTERY_DEVICE_FELL_OVER", "msg": "wat", "archived": False},
                {"key": "EVT_MYSTERY_DEVICE_FELL_OVER", "msg": "again", "archived": False},
                {"key": "EVT_ANOTHER_UNKNOWN", "msg": "hmm", "archived": False},
            ],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            await client.categorise_alarms()

        assert client.unrecognised_keys == {
            "EVT_MYSTERY_DEVICE_FELL_OVER": 2,
            "EVT_ANOTHER_UNKNOWN": 1,
        }

    @pytest.mark.asyncio
    async def test_unrecognised_keys_reset_between_calls(self):
        """unrecognised_keys reflects only the most recent categorise_alarms() call."""
        client = make_client()
        client._auth._authenticated = True

        body1 = {
            "meta": {"rc": "ok"},
            "data": [{"key": "EVT_UNKNOWN_FIRST", "msg": ".", "archived": False}],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body1)
            await client.categorise_alarms()
        assert "EVT_UNKNOWN_FIRST" in client.unrecognised_keys

        body2 = {
            "meta": {"rc": "ok"},
            "data": [{"key": "EVT_UNKNOWN_SECOND", "msg": ".", "archived": False}],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body2)
            await client.categorise_alarms()

        # Only the second call's keys remain
        assert "EVT_UNKNOWN_SECOND" in client.unrecognised_keys
        assert "EVT_UNKNOWN_FIRST" not in client.unrecognised_keys

    @pytest.mark.asyncio
    async def test_unrecognised_keys_empty_when_all_classified(self):
        """unrecognised_keys is empty when all alarms map to a category."""
        client = make_client()
        client._auth._authenticated = True
        body = {
            "meta": {"rc": "ok"},
            "data": [
                {"key": "EVT_GW_WANTransition", "msg": "WAN down", "archived": False},
            ],
        }
        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload=body)
            await client.categorise_alarms()

        assert client.unrecognised_keys == {}


class TestAuthenticate:
    """Tests for UniFiClient.authenticate — delegates to UniFiAuth.authenticate().

    Method auto-detection and fallback are UniFiAuth's own behaviour and are
    covered by tests/unit/test_unifi_auth.py. These tests only cover what
    UniFiClient itself is responsible for: delegating to self._auth and
    resetting probe-backoff state on every successful authentication.

    UniFiAuth is a composed collaborator here (not HTTP), so these stay on
    MagicMock/AsyncMock — out of scope for the aioresponses conversion.
    """

    @pytest.mark.asyncio
    async def test_delegates_to_auth_and_returns_its_result(self):
        client = make_client()
        client._auth.authenticate = AsyncMock(return_value="apikey")

        result = await client.authenticate()

        assert result == "apikey"
        client._auth.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_propagates_auth_failure(self):
        client = make_client()
        client._auth.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

        with pytest.raises(InvalidAuthError):
            await client.authenticate()


class TestClose:
    """Tests for UniFiClient.close — logout behavior."""

    @pytest.mark.asyncio
    async def test_userpass_auth_posts_to_unifi_os_logout_path(self):
        """close() must POST to /api/auth/logout (UniFi OS path only)."""
        client = make_client()
        client._auth._method = "userpass"
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(LOGOUT_URL, status=200)
            await client.close()
            calls = _find_calls(m, "POST", LOGOUT_URL)

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_apikey_auth_does_not_post_logout(self):
        client = make_client({"api_key": "k", "verify_ssl": False})
        client._auth._method = "apikey"
        client._auth._authenticated = True

        with aioresponses() as m:
            # Nothing registered — if close() posted anywhere, aioresponses
            # would raise for the unmatched request and fail this test.
            await client.close()
            assert _total_calls(m) == 0

    @pytest.mark.asyncio
    async def test_not_authenticated_does_not_post_logout(self):
        client = make_client()
        client._auth._method = "userpass"
        client._auth._authenticated = False

        with aioresponses() as m:
            await client.close()
            assert _total_calls(m) == 0

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
        client._auth._method = "userpass"
        client._auth._authenticated = True
        secret_marker = "controller.local: 401 Unauthorized — api_key=secret"

        with aioresponses() as m:
            m.post(LOGOUT_URL, exception=ConnectionResetError(secret_marker))
            with caplog.at_level(
                logging.WARNING, logger="custom_components.unifi_alerts.unifi_client"
            ):
                await client.close()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ConnectionResetError" in r.getMessage() for r in warnings)
        assert all(secret_marker not in r.getMessage() for r in warnings)

    @pytest.mark.asyncio
    async def test_logout_failure_does_not_propagate(self):
        """close() must never raise on a realistic logout failure — best-effort.

        Only network/connection failures (aiohttp.ClientError, OSError,
        TimeoutError) are absorbed; a genuine bug (e.g. RuntimeError from our
        own code) is intentionally allowed to propagate so it isn't hidden.
        """
        import aiohttp

        client = make_client()
        client._auth._method = "userpass"
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(LOGOUT_URL, exception=aiohttp.ClientConnectionError("boom"))
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

        Constructs a config dict with no verify_ssl key and asserts, via
        aioresponses' request history, that the ssl kwarg forwarded on the
        outbound request is DEFAULT_VERIFY_SSL (True), not False.
        """
        from custom_components.unifi_alerts.const import DEFAULT_VERIFY_SSL

        # Config deliberately omits verify_ssl
        config = {"username": "admin", "password": "secret"}
        client = make_client(config)
        client._auth._authenticated = True

        with aioresponses() as m:
            m.get(_list_alarm_url(), status=200, payload={"meta": {"rc": "ok"}, "data": []})
            await client.fetch_alarms()
            calls = _find_calls(m, "GET", _list_alarm_url())

        assert len(calls) == 1, "Expected exactly one GET call"
        sent_ssl = calls[0].kwargs.get("ssl")
        assert sent_ssl is DEFAULT_VERIFY_SSL, (
            f"Expected ssl={DEFAULT_VERIFY_SSL!r} (DEFAULT_VERIFY_SSL) when key is absent, "
            f"got {sent_ssl!r}"
        )
        assert sent_ssl is True, "DEFAULT_VERIFY_SSL must be True — fail closed"


class TestSslCertificateError:
    """SslCertificateError is raised on TLS certificate failures, not CannotConnectError.

    Auth-layer certificate handling (_verify_api_key, _login_userpass) is
    UniFiAuth's own behaviour and is covered by tests/unit/test_unifi_auth.py.
    These tests cover UniFiClient's own request paths.
    """

    @pytest.mark.asyncio
    async def test_try_fetch_alarms_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in _try_fetch_alarms must raise SslCertificateError."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client()
        client._auth._authenticated = True
        url = "https://192.168.1.1/api/alarm"

        with aioresponses() as m:
            m.get(
                url,
                exception=aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock()),
            )
            with pytest.raises(SslCertificateError):
                await client._try_fetch_alarms(url, "default")

    @pytest.mark.asyncio
    async def test_fetch_system_log_alarms_raises_ssl_cert_error(self):
        """aiohttp.ClientConnectorCertificateError in fetch_system_log_alarms must raise SslCertificateError."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(
                _system_log_url(),
                exception=aiohttp.ClientConnectorCertificateError(MagicMock(), MagicMock()),
            )
            with pytest.raises(SslCertificateError):
                await client.fetch_system_log_alarms()


class TestProbeSystemLogEndpoint:
    """Tests for UniFiClient.probe_system_log_endpoint."""

    @pytest.mark.asyncio
    async def test_probe_returns_true_on_200(self):
        """HTTP 200 from /system-log/count must return True and set _has_system_log=True."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_probe_url(), status=200, payload={"categories": []})
            result = await client.probe_system_log_endpoint()
        assert result is True
        assert client._has_system_log is True

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_404(self):
        """HTTP 404 from /system-log/count must return False and set _has_system_log=False."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_probe_url(), status=404)
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
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_probe_url(), status=403)
            result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_500_does_not_cache(self):
        """HTTP 5xx is treated as transient: returns False without caching."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_probe_url(), status=503)
            result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_network_error_does_not_cache(self):
        """aiohttp.ClientError during probe must return False, not raise, and not cache."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_probe_url(), exception=aiohttp.ClientConnectionError("unreachable"))
            result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_retries_after_transient_failure(self):
        """A 5xx followed by a 200 must end with cache=True (transient does not pin to legacy).

        Registers two responses for the same URL without repeat=True: aioresponses
        consumes them FIFO in call order, so the first probe gets 503 and the
        second gets 200.
        """
        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(_probe_url(), status=503)
            m.post(_probe_url(), status=200, payload={})

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
        client._auth._authenticated = True
        client._has_system_log = True  # pre-set the cache

        with aioresponses() as m:
            # Nothing registered — a network hit here would raise and fail the test.
            result = await client.probe_system_log_endpoint()
            assert _total_calls(m) == 0, "Network must not be hit when result is cached"
        assert result is True

    @pytest.mark.asyncio
    async def test_probe_is_cached_after_false(self):
        """Second call must not hit the network when _has_system_log is False."""
        client = make_client()
        client._auth._authenticated = True
        client._has_system_log = False  # pre-set the cache

        with aioresponses() as m:
            result = await client.probe_system_log_endpoint()
            assert _total_calls(m) == 0, "Network must not be hit when result is cached"
        assert result is False

    @pytest.mark.asyncio
    async def test_probe_url_includes_v2_and_site(self):
        """Probe URL must include /v2/api/site/{site}/system-log/count."""
        client = make_client()
        client._auth._authenticated = True
        expected_url = _probe_url(site="mysite")

        with aioresponses() as m:
            m.post(expected_url, status=200, payload={})
            await client.probe_system_log_endpoint(site="mysite")
            calls = _find_calls(m, "POST", expected_url)

        assert len(calls) == 1, "Expected one POST call"
        assert "v2/api/site/mysite/system-log/count" in expected_url

    @pytest.mark.asyncio
    async def test_probe_backoff_triggers_after_fail_limit(self):
        """After _PROBE_FAIL_LIMIT consecutive transient failures the probe caches False
        and sets a backoff deadline so subsequent polls skip the network entirely."""
        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(_probe_url(), status=503, repeat=True)
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
        client._auth._authenticated = True
        client._has_system_log = False
        client._probe_backoff_until = datetime.now(UTC) + timedelta(hours=1)

        with aioresponses() as m:
            result = await client.probe_system_log_endpoint()
            assert _total_calls(m) == 0, "Network must not be hit during backoff"
        assert result is False

    @pytest.mark.asyncio
    async def test_probe_retries_after_backoff_expires(self):
        """Once the backoff window expires, the next probe must hit the network
        and, if successful, set cache=True and clear backoff state."""
        from datetime import UTC, datetime, timedelta

        client = make_client()
        client._auth._authenticated = True
        # Simulate an expired backoff (deadline in the past).
        client._has_system_log = False
        client._probe_backoff_until = datetime.now(UTC) - timedelta(seconds=1)
        client._probe_fail_count = _PROBE_FAIL_LIMIT

        with aioresponses() as m:
            m.post(_probe_url(), status=200, payload={})
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
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(_probe_url(), status=404)
            result = await client.probe_system_log_endpoint()

        assert result is False
        assert client._has_system_log is False
        assert client._probe_backoff_until is None

    @pytest.mark.asyncio
    async def test_probe_backoff_via_network_error(self):
        """Repeated aiohttp.ClientError failures must also trigger the backoff
        after reaching _PROBE_FAIL_LIMIT."""
        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(
                _probe_url(),
                exception=aiohttp.ClientConnectionError("unreachable"),
                repeat=True,
            )
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

        with aioresponses() as m:
            m.post(LOGIN_URL, status=200)
            await client.authenticate()

        # Backoff state must be cleared
        assert client._probe_backoff_until is None
        assert client._probe_fail_count == 0
        assert client._has_system_log is None  # re-probed on next poll

    @pytest.mark.asyncio
    async def test_reauth_does_not_reset_confirmed_true(self):
        """If _has_system_log is True (v2 endpoint confirmed), re-auth must not
        reset it to None - there's nothing to re-probe."""
        client = make_client()
        client._has_system_log = True
        client._probe_fail_count = 0
        client._probe_backoff_until = None

        with aioresponses() as m:
            m.post(LOGIN_URL, status=200)
            await client.authenticate()

        assert client._has_system_log is True


class TestFetchSystemLogAlarms:
    """Tests for UniFiClient.fetch_system_log_alarms."""

    def _page_body(self, events: list[dict], total_pages: int, page: int = 0) -> dict:
        """Build the JSON body for one system-log/all page response."""
        return {
            "data": events,
            "page_number": page,
            "total_element_count": len(events),
            "total_page_count": total_pages,
        }

    @pytest.mark.asyncio
    async def test_returns_new_events_only(self):
        """Only events with status='NEW' must be returned; others are filtered."""
        client = make_client()
        client._auth._authenticated = True
        events = [
            {"key": "THREAT_BLOCKED", "status": "NEW", "timestamp": 1778025612345},
            {"key": "THREAT_BLOCKED", "status": "ARCHIVED", "timestamp": 1778025612000},
        ]
        with aioresponses() as m:
            m.post(_system_log_url(), status=200, payload=self._page_body(events, total_pages=1))
            result = await client.fetch_system_log_alarms()
        assert len(result) == 1
        assert result[0]["status"] == "NEW"

    @pytest.mark.asyncio
    async def test_paginates_until_total_pages_exhausted(self):
        """Must fetch pages until total_page_count is reached."""
        client = make_client()
        client._auth._authenticated = True
        event = {"key": "K", "status": "NEW", "timestamp": 1000}

        with aioresponses() as m:
            m.post(_system_log_url(), status=200, payload=self._page_body([event], 3, page=0))
            m.post(_system_log_url(), status=200, payload=self._page_body([event], 3, page=1))
            m.post(_system_log_url(), status=200, payload=self._page_body([event], 3, page=2))
            result = await client.fetch_system_log_alarms()
            total = _total_calls(m)

        assert total == 3
        assert len(result) == 3  # one NEW event per page

    @pytest.mark.asyncio
    async def test_stops_at_max_pages_cap(self):
        """Must stop after MAX_SYSTEM_LOG_PAGES even if total_page_count is larger."""
        from custom_components.unifi_alerts.const import MAX_SYSTEM_LOG_PAGES

        client = make_client()
        client._auth._authenticated = True
        event = {"key": "K", "status": "NEW", "timestamp": 1000}
        # total_page_count is intentionally larger than MAX_SYSTEM_LOG_PAGES
        body = self._page_body([event], total_pages=9999, page=0)

        with aioresponses() as m:
            m.post(_system_log_url(), status=200, payload=body, repeat=True)
            await client.fetch_system_log_alarms()
            total = _total_calls(m)

        assert total == MAX_SYSTEM_LOG_PAGES, (
            f"Expected exactly {MAX_SYSTEM_LOG_PAGES} page fetches; got {total}"
        )

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self):
        """Must stop when a page returns an empty data list."""
        client = make_client()
        client._auth._authenticated = True
        event = {"key": "K", "status": "NEW", "timestamp": 1000}

        with aioresponses() as m:
            # large total_page_count — early stop must come from the empty page
            m.post(_system_log_url(), status=200, payload=self._page_body([event], 99, page=0))
            m.post(_system_log_url(), status=200, payload=self._page_body([], 99, page=1))
            result = await client.fetch_system_log_alarms()
            total = _total_calls(m)

        assert total == 2  # first page + one empty page
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_passes_timestamp_from_as_epoch_ms(self):
        """timestampFrom must be epoch milliseconds derived from the since datetime."""
        from datetime import UTC, datetime

        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(_system_log_url(), status=200, payload=self._page_body([], 1, page=0))
            since = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            expected_ms = int(since.timestamp() * 1000)
            await client.fetch_system_log_alarms(since=since)
            calls = _find_calls(m, "POST", _system_log_url())

        assert len(calls) == 1, "Expected at least one POST call"
        sent_json = calls[0].kwargs.get("json") or {}
        assert sent_json.get("timestampFrom") == expected_ms, (
            f"Expected timestampFrom={expected_ms}, got {sent_json.get('timestampFrom')}"
        )

    @pytest.mark.asyncio
    async def test_uses_default_lookback_when_no_since(self):
        """When since=None, timestampFrom must be approximately now - DEFAULT lookback."""
        from datetime import UTC, datetime, timedelta

        from custom_components.unifi_alerts.const import DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS

        client = make_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(_system_log_url(), status=200, payload=self._page_body([], 1, page=0))
            await client.fetch_system_log_alarms(since=None)
            calls = _find_calls(m, "POST", _system_log_url())

        expected_approx_ms = int(
            (datetime.now(UTC) - timedelta(hours=DEFAULT_SYSTEM_LOG_LOOKBACK_HOURS)).timestamp()
            * 1000
        )
        actual_ms = calls[0].kwargs.get("json", {}).get("timestampFrom")
        # Allow 5-second slack for test execution time
        assert abs(actual_ms - expected_approx_ms) < 5000, (
            f"timestampFrom {actual_ms} deviates too far from expected {expected_approx_ms}"
        )

    @pytest.mark.asyncio
    async def test_401_raises_invalid_auth(self):
        """HTTP 401 during system-log fetch must raise InvalidAuthError."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_system_log_url(), status=401)
            with pytest.raises(InvalidAuthError):
                await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_network_error_raises_cannot_connect(self):
        """aiohttp.ClientError during fetch must raise CannotConnectError."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_system_log_url(), exception=aiohttp.ClientConnectionError("unreachable"))
            with pytest.raises(CannotConnectError):
                await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """3xx from the system-log endpoint must raise CannotConnectError."""
        client = make_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(_system_log_url(), status=301)
            with pytest.raises(CannotConnectError, match="redirect"):
                await client.fetch_system_log_alarms()
