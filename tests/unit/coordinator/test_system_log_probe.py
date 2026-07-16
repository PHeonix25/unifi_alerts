"""Tests for UniFiAlertsCoordinator._probe_has_system_log: caching and backoff.

UniFiClient.probe_system_log_endpoint() is a single stateless HTTP call
(True/False/None per call, no caching — see tests/unit/unifi_client/test_v2.py).
Caching the result across poll cycles and backing off after repeated
transient outcomes is the coordinator's concern (#240); these tests exercise
that behaviour directly against _probe_has_system_log(), mocking the client's
single-call probe method.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.unifi_alerts.coordinator import _PROBE_FAIL_LIMIT
from custom_components.unifi_alerts.coordinator import (
    _PROBE_RETRY_AFTER as _ACTUAL_PROBE_RETRY_AFTER,
)

from .conftest import make_full_coordinator, make_hass_and_client

# Pinned business-rule value for the probe backoff window. Deliberately NOT
# compared against the imported constant alone — asserting the deadline lands
# in a window derived from the same value would be tautological if the
# constant itself regressed (e.g. minutes instead of hours), so the test
# below also sanity-checks the constant against a hardcoded expectation.
_EXPECTED_PROBE_RETRY_AFTER = timedelta(hours=1)


def test_probe_retry_after_is_one_hour():
    """Pin the backoff window so a regression here is caught explicitly."""
    assert _ACTUAL_PROBE_RETRY_AFTER == _EXPECTED_PROBE_RETRY_AFTER


class TestProbeCaching:
    @pytest.mark.asyncio
    async def test_true_is_cached(self):
        """Once the probe returns True, subsequent calls must not hit the client again."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        coord = make_full_coordinator(hass, client)

        first = await coord._probe_has_system_log()
        second = await coord._probe_has_system_log()

        assert first is True
        assert second is True
        client.probe_system_log_endpoint.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_definitive_false_is_cached(self):
        """A definitive False (404) must be cached with no backoff deadline."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=False)
        coord = make_full_coordinator(hass, client)

        first = await coord._probe_has_system_log()
        second = await coord._probe_has_system_log()

        assert first is False
        assert second is False
        assert coord._probe_backoff_until is None
        client.probe_system_log_endpoint.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transient_none_is_not_cached(self):
        """A single transient outcome (None) must not be cached; the next call re-probes."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        coord = make_full_coordinator(hass, client)

        first = await coord._probe_has_system_log()
        second = await coord._probe_has_system_log()

        assert first is False
        assert second is False
        assert coord._has_system_log is None
        assert client.probe_system_log_endpoint.await_count == 2

    @pytest.mark.asyncio
    async def test_transient_then_success_ends_cached_true(self):
        """A transient failure followed by success must end with the cache at True."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(side_effect=[None, True])
        coord = make_full_coordinator(hass, client)

        first = await coord._probe_has_system_log()
        assert first is False
        assert coord._has_system_log is None, "Transient failure must not cache"

        second = await coord._probe_has_system_log()
        assert second is True
        assert coord._has_system_log is True


class TestProbeBackoff:
    @pytest.mark.asyncio
    async def test_backoff_triggers_after_fail_limit(self):
        """After _PROBE_FAIL_LIMIT consecutive transient outcomes, the cache pins to
        False and a backoff deadline is set so subsequent polls skip the client entirely."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        coord = make_full_coordinator(hass, client)

        before = datetime.now(UTC)
        for _ in range(_PROBE_FAIL_LIMIT):
            result = await coord._probe_has_system_log()
            assert result is False
        after = datetime.now(UTC)

        assert coord._has_system_log is False
        assert coord._probe_backoff_until is not None
        assert coord._probe_fail_count == _PROBE_FAIL_LIMIT
        assert (
            before + _EXPECTED_PROBE_RETRY_AFTER
            <= coord._probe_backoff_until
            <= after + _EXPECTED_PROBE_RETRY_AFTER
        )
        assert client.probe_system_log_endpoint.await_count == _PROBE_FAIL_LIMIT

    @pytest.mark.asyncio
    async def test_during_backoff_skips_the_client(self):
        """Once in backoff, probes must return False without calling the client."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        coord = make_full_coordinator(hass, client)
        coord._has_system_log = False
        coord._probe_backoff_until = datetime.now(UTC) + timedelta(hours=1)

        result = await coord._probe_has_system_log()

        assert result is False
        client.probe_system_log_endpoint.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retries_after_backoff_expires(self):
        """Once the backoff window expires, the next probe must call the client
        and, if successful, cache True and clear backoff state."""
        hass, client = make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        coord = make_full_coordinator(hass, client)
        coord._has_system_log = False
        coord._probe_backoff_until = datetime.now(UTC) - timedelta(seconds=1)
        coord._probe_fail_count = _PROBE_FAIL_LIMIT

        result = await coord._probe_has_system_log()

        assert result is True
        assert coord._has_system_log is True
        assert coord._probe_backoff_until is None
        assert coord._probe_fail_count == 0
        client.probe_system_log_endpoint.assert_awaited_once()
