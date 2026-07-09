"""Shared HTTP-test helpers for UniFiClient tests.

HTTP-hitting tests use pytest-homeassistant-custom-component's aioclient_mock
fixture (AiohttpClientMocker) to mock at the aiohttp transport layer
(``aiohttp.ClientSession._request``). This is Home Assistant core's own test
double, used by HA core's integration test suites; it is structurally immune
to aiohttp internals changing underneath it (unlike aioresponses, which
constructs a real ``aiohttp.ClientResponse`` and broke on aiohttp 3.14 — see
issue #312). Assertions can still be made against the outbound request itself
(URL, method, headers, body) via the call recorder below. See issue #229 for
the original rationale that led to aioresponses, and #312 for the migration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.unifi_alerts.unifi_client import UNIFI_OS_NETWORK_PREFIX, UniFiClient

BASE_URL = "https://192.168.1.1"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
LOGOUT_URL = f"{BASE_URL}/api/auth/logout"


@dataclass
class RecordedCall:
    """One outbound HTTP request captured from the mocked ClientSession.

    aioclient_mock.mock_calls records only (method, url, data, headers), which
    drops kwargs tests need to assert on (e.g. ssl=), so requests are captured
    via a thin wrapper around ClientSession._request instead.
    """

    method: str
    url: str
    kwargs: dict[str, Any] = field(default_factory=dict)


_recorded_calls: list[RecordedCall] = []

# Sessions created by make_client() during the current test, closed by the
# _close_client_sessions autouse fixture below. pytest-homeassistant-custom-component
# asserts no lingering threads/timers survive a test, and an unclosed
# aiohttp.ClientSession schedules its own cleanup on the loop's default
# executor, which trips that check — so every session made here must be
# closed before the test ends.
_created_sessions: list = []


def make_client(aioclient_mock: AiohttpClientMocker, config: dict | None = None) -> UniFiClient:
    """Build a UniFiClient wired to aioclient_mock via a real aiohttp.ClientSession.

    aioclient_mock.create_session() builds a real aiohttp.ClientSession with its
    _request bound method replaced, so no real socket is ever opened and no
    connector/resolver setup is needed. The session is tracked for teardown by
    _close_client_sessions.
    """
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    mocked_request = session._request

    async def _recording_request(method: str, url: Any, **kwargs: Any):
        _recorded_calls.append(RecordedCall(method.upper(), str(url), kwargs))
        return await mocked_request(method, url, **kwargs)

    object.__setattr__(session, "_request", _recording_request)
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


@pytest.fixture(autouse=True)
def _clear_recorded_calls() -> Generator[None]:
    """Reset the outbound-request recorder between tests."""
    _recorded_calls.clear()
    yield
    _recorded_calls.clear()


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


def find_calls(method: str, url: str) -> list[RecordedCall]:
    """Return the recorded request history for one (method, url) pair."""
    return [c for c in _recorded_calls if c.method == method.upper() and c.url == url]


def total_calls() -> int:
    return len(_recorded_calls)


def queue_responses(
    aioclient_mock: AiohttpClientMocker,
    method: str,
    url: str,
    responses: list[dict[str, Any]],
) -> None:
    """Register a sequence of distinct responses for repeated calls to one (method, url).

    aioclient_mock never consumes a matched registration — every call to a
    given (method, url) is answered by the *first* matching registration
    forever. That makes it unsuitable, out of the box, for tests exercising a
    URL that must answer differently across successive calls (e.g. a
    transient failure followed by success, or successive pagination
    responses). This registers a single mock whose side_effect hands out
    ``responses`` one at a time, in order, one per call; a call made after the
    queue is exhausted raises AssertionError, same as an unmatched request
    would.
    """
    queue = list(responses)

    async def _next(method: str, url: Any, data: Any) -> AiohttpClientMockResponse:
        if not queue:
            raise AssertionError(f"No more queued responses for {method.upper()} {url}")
        return AiohttpClientMockResponse(method=method, url=url, **queue.pop(0))

    aioclient_mock.request(method, url, side_effect=_next)
