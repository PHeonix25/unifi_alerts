"""Shared HTTP-test helpers for UniFiClient tests.

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

from collections.abc import Generator

import aiohttp
import pytest
from aiohttp.resolver import ThreadedResolver
from aioresponses import aioresponses

from custom_components.unifi_alerts.unifi_client import UNIFI_OS_NETWORK_PREFIX, UniFiClient

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
async def _close_client_sessions() -> Generator[None]:
    """Close every aiohttp.ClientSession created via make_client() this test."""
    yield
    while _created_sessions:
        session = _created_sessions.pop()
        if not session.closed:
            await session.close()


def list_alarm_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/list/alarm"


def alarm_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/alarm"


def stat_alarm_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/api/s/{site}/stat/alarm"


def probe_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/count"


def system_log_url(site: str = "default") -> str:
    return f"{BASE_URL}{UNIFI_OS_NETWORK_PREFIX}/v2/api/site/{site}/system-log/all"


def find_calls(m: aioresponses, method: str, url: str) -> list:
    """Return the recorded request history for one (method, url) pair.

    Compares by string rather than by yarl.URL equality so this stays robust
    to aioresponses' internal key normalisation across versions.
    """
    calls: list = []
    for (recorded_method, recorded_url), call_list in m.requests.items():
        if recorded_method == method and str(recorded_url) == url:
            calls.extend(call_list)
    return calls


def total_calls(m: aioresponses) -> int:
    return sum(len(v) for v in m.requests.values())
