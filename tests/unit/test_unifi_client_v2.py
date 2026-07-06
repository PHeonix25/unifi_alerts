"""Tests for the UniFi HTTP client's v2 system-log probe and fetch path.

Split out of test_unifi_client.py (#283) by behaviour area. See
test_unifi_client_legacy.py for classify/legacy-fetch/auth/close/SSL.
"""

from __future__ import annotations

from datetime import timedelta

import aiohttp
import pytest
from aioresponses import aioresponses
from conftest import (
    UNIFI_CLIENT_LOGIN_URL,
    find_calls,
    make_unifi_client,
    probe_url,
    system_log_url,
    total_calls,
)

from custom_components.unifi_alerts.unifi_auth import CannotConnectError, InvalidAuthError
from custom_components.unifi_alerts.unifi_client import _PROBE_FAIL_LIMIT

# Pinned business-rule value for the probe backoff window. Deliberately NOT
# imported as `_PROBE_RETRY_AFTER` from unifi_client — importing the constant
# under test would make any assertion against it tautological (change the
# constant, both sides of the comparison move together, and a genuine
# regression in the backoff duration would still pass).
_EXPECTED_PROBE_RETRY_AFTER = timedelta(hours=1)


class TestProbeSystemLogEndpoint:
    """Tests for UniFiClient.probe_system_log_endpoint."""

    @pytest.mark.asyncio
    async def test_probe_returns_true_on_200(self):
        """HTTP 200 from /system-log/count must return True and set _has_system_log=True."""
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(probe_url(), status=200, payload={"categories": []})
            result = await client.probe_system_log_endpoint()
        assert result is True
        assert client._has_system_log is True

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_404(self):
        """HTTP 404 from /system-log/count must return False and set _has_system_log=False."""
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(probe_url(), status=404)
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
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(probe_url(), status=403)
            result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_500_does_not_cache(self):
        """HTTP 5xx is treated as transient: returns False without caching."""
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(probe_url(), status=503)
            result = await client.probe_system_log_endpoint()
        assert result is False
        assert client._has_system_log is None

    @pytest.mark.asyncio
    async def test_probe_returns_false_on_network_error_does_not_cache(self):
        """aiohttp.ClientError during probe must return False, not raise, and not cache."""
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(probe_url(), exception=aiohttp.ClientConnectionError("unreachable"))
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
        client = make_unifi_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(probe_url(), status=503)
            m.post(probe_url(), status=200, payload={})

            first = await client.probe_system_log_endpoint()
            assert first is False
            assert client._has_system_log is None, "Transient failure must not cache"

            second = await client.probe_system_log_endpoint()
            assert second is True
            assert client._has_system_log is True

    @pytest.mark.asyncio
    async def test_probe_is_cached_after_true(self):
        """Second call must not hit the network when _has_system_log is True."""
        client = make_unifi_client()
        client._auth._authenticated = True
        client._has_system_log = True  # pre-set the cache

        with aioresponses() as m:
            # Nothing registered — a network hit here would raise and fail the test.
            result = await client.probe_system_log_endpoint()
            assert total_calls(m) == 0, "Network must not be hit when result is cached"
        assert result is True

    @pytest.mark.asyncio
    async def test_probe_is_cached_after_false(self):
        """Second call must not hit the network when _has_system_log is False."""
        client = make_unifi_client()
        client._auth._authenticated = True
        client._has_system_log = False  # pre-set the cache

        with aioresponses() as m:
            result = await client.probe_system_log_endpoint()
            assert total_calls(m) == 0, "Network must not be hit when result is cached"
        assert result is False

    @pytest.mark.asyncio
    async def test_probe_url_includes_v2_and_site(self):
        """Probe URL must include /v2/api/site/{site}/system-log/count."""
        client = make_unifi_client()
        client._auth._authenticated = True
        expected_url = probe_url(site="mysite")

        with aioresponses() as m:
            m.post(expected_url, status=200, payload={})
            await client.probe_system_log_endpoint(site="mysite")
            calls = find_calls(m, "POST", expected_url)

        assert len(calls) == 1, "Expected one POST call"
        assert "v2/api/site/mysite/system-log/count" in expected_url

    @pytest.mark.asyncio
    async def test_probe_backoff_triggers_after_fail_limit(self):
        """After _PROBE_FAIL_LIMIT consecutive transient failures the probe caches False
        and sets a backoff deadline so subsequent polls skip the network entirely."""
        from datetime import UTC, datetime

        client = make_unifi_client()
        client._auth._authenticated = True

        before = datetime.now(UTC)
        with aioresponses() as m:
            m.post(probe_url(), status=503, repeat=True)
            for _ in range(_PROBE_FAIL_LIMIT):
                result = await client.probe_system_log_endpoint()
                assert result is False
        after = datetime.now(UTC)

        # After the threshold the cache must be False and a backoff deadline set.
        assert client._has_system_log is False
        assert client._probe_backoff_until is not None
        assert client._probe_fail_count == _PROBE_FAIL_LIMIT
        # Assert the actual deadline duration, not just its presence — a wrong
        # _PROBE_RETRY_AFTER value (e.g. minutes instead of hours) would still
        # satisfy `is not None` and pass the rest of the suite.
        assert (
            before + _EXPECTED_PROBE_RETRY_AFTER
            <= client._probe_backoff_until
            <= after + _EXPECTED_PROBE_RETRY_AFTER
        )

    @pytest.mark.asyncio
    async def test_probe_during_backoff_skips_network(self):
        """Once in backoff, probes must return False without making a network call."""
        from datetime import UTC, datetime, timedelta

        client = make_unifi_client()
        client._auth._authenticated = True
        client._has_system_log = False
        client._probe_backoff_until = datetime.now(UTC) + timedelta(hours=1)

        with aioresponses() as m:
            result = await client.probe_system_log_endpoint()
            assert total_calls(m) == 0, "Network must not be hit during backoff"
        assert result is False

    @pytest.mark.asyncio
    async def test_probe_retries_after_backoff_expires(self):
        """Once the backoff window expires, the next probe must hit the network
        and, if successful, set cache=True and clear backoff state."""
        from datetime import UTC, datetime, timedelta

        client = make_unifi_client()
        client._auth._authenticated = True
        # Simulate an expired backoff (deadline in the past).
        client._has_system_log = False
        client._probe_backoff_until = datetime.now(UTC) - timedelta(seconds=1)
        client._probe_fail_count = _PROBE_FAIL_LIMIT

        with aioresponses() as m:
            m.post(probe_url(), status=200, payload={})
            result = await client.probe_system_log_endpoint()

        assert result is True
        assert client._has_system_log is True
        assert client._probe_backoff_until is None
        assert client._probe_fail_count == 0

    @pytest.mark.asyncio
    async def test_probe_404_does_not_set_backoff(self):
        """A definitive 404 must set cache=False without a backoff deadline
        (the endpoint will never appear on this controller)."""
        client = make_unifi_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(probe_url(), status=404)
            result = await client.probe_system_log_endpoint()

        assert result is False
        assert client._has_system_log is False
        assert client._probe_backoff_until is None

    @pytest.mark.asyncio
    async def test_probe_backoff_via_network_error(self):
        """Repeated aiohttp.ClientError failures must also trigger the backoff
        after reaching _PROBE_FAIL_LIMIT."""
        from datetime import UTC, datetime

        client = make_unifi_client()
        client._auth._authenticated = True

        before = datetime.now(UTC)
        with aioresponses() as m:
            m.post(
                probe_url(),
                exception=aiohttp.ClientConnectionError("unreachable"),
                repeat=True,
            )
            for _ in range(_PROBE_FAIL_LIMIT):
                result = await client.probe_system_log_endpoint()
                assert result is False
        after = datetime.now(UTC)

        assert client._has_system_log is False
        assert client._probe_backoff_until is not None
        assert (
            before + _EXPECTED_PROBE_RETRY_AFTER
            <= client._probe_backoff_until
            <= after + _EXPECTED_PROBE_RETRY_AFTER
        )

    @pytest.mark.asyncio
    async def test_reauth_clears_probe_backoff(self):
        """A successful authenticate() must clear the probe-backoff state so the
        next probe call actually hits the network instead of returning the cached
        False from backoff."""
        from datetime import UTC, datetime, timedelta

        client = make_unifi_client()
        # Simulate an active backoff (e.g. credentials were bad, probe kept failing)
        client._has_system_log = False
        client._probe_fail_count = _PROBE_FAIL_LIMIT
        client._probe_backoff_until = datetime.now(UTC) + timedelta(hours=1)

        with aioresponses() as m:
            m.post(UNIFI_CLIENT_LOGIN_URL, status=200)
            await client.authenticate()

        # Backoff state must be cleared
        assert client._probe_backoff_until is None
        assert client._probe_fail_count == 0
        assert client._has_system_log is None  # re-probed on next poll

    @pytest.mark.asyncio
    async def test_reauth_does_not_reset_confirmed_true(self):
        """If _has_system_log is True (v2 endpoint confirmed), re-auth must not
        reset it to None - there's nothing to re-probe."""
        client = make_unifi_client()
        client._has_system_log = True
        client._probe_fail_count = 0
        client._probe_backoff_until = None

        with aioresponses() as m:
            m.post(UNIFI_CLIENT_LOGIN_URL, status=200)
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
        client = make_unifi_client()
        client._auth._authenticated = True
        events = [
            {"key": "THREAT_BLOCKED", "status": "NEW", "timestamp": 1778025612345},
            {"key": "THREAT_BLOCKED", "status": "ARCHIVED", "timestamp": 1778025612000},
        ]
        with aioresponses() as m:
            m.post(system_log_url(), status=200, payload=self._page_body(events, total_pages=1))
            result = await client.fetch_system_log_alarms()
        assert len(result) == 1
        assert result[0]["status"] == "NEW"

    @pytest.mark.asyncio
    async def test_paginates_until_total_pages_exhausted(self):
        """Must fetch pages until total_page_count is reached."""
        client = make_unifi_client()
        client._auth._authenticated = True
        event = {"key": "K", "status": "NEW", "timestamp": 1000}

        with aioresponses() as m:
            m.post(system_log_url(), status=200, payload=self._page_body([event], 3, page=0))
            m.post(system_log_url(), status=200, payload=self._page_body([event], 3, page=1))
            m.post(system_log_url(), status=200, payload=self._page_body([event], 3, page=2))
            result = await client.fetch_system_log_alarms()
            total = total_calls(m)

        assert total == 3
        assert len(result) == 3  # one NEW event per page

    @pytest.mark.asyncio
    async def test_stops_at_max_pages_cap(self):
        """Must stop after MAX_SYSTEM_LOG_PAGES even if total_page_count is larger."""
        from custom_components.unifi_alerts.const import MAX_SYSTEM_LOG_PAGES

        client = make_unifi_client()
        client._auth._authenticated = True
        event = {"key": "K", "status": "NEW", "timestamp": 1000}
        # total_page_count is intentionally larger than MAX_SYSTEM_LOG_PAGES
        body = self._page_body([event], total_pages=9999, page=0)

        with aioresponses() as m:
            m.post(system_log_url(), status=200, payload=body, repeat=True)
            await client.fetch_system_log_alarms()
            total = total_calls(m)

        assert total == MAX_SYSTEM_LOG_PAGES, (
            f"Expected exactly {MAX_SYSTEM_LOG_PAGES} page fetches; got {total}"
        )

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self):
        """Must stop when a page returns an empty data list."""
        client = make_unifi_client()
        client._auth._authenticated = True
        event = {"key": "K", "status": "NEW", "timestamp": 1000}

        with aioresponses() as m:
            # large total_page_count — early stop must come from the empty page
            m.post(system_log_url(), status=200, payload=self._page_body([event], 99, page=0))
            m.post(system_log_url(), status=200, payload=self._page_body([], 99, page=1))
            result = await client.fetch_system_log_alarms()
            total = total_calls(m)

        assert total == 2  # first page + one empty page
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_passes_timestamp_from_as_epoch_ms(self):
        """timestampFrom must be epoch milliseconds derived from the since datetime."""
        from datetime import UTC, datetime

        client = make_unifi_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(system_log_url(), status=200, payload=self._page_body([], 1, page=0))
            since = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
            expected_ms = int(since.timestamp() * 1000)
            await client.fetch_system_log_alarms(since=since)
            calls = find_calls(m, "POST", system_log_url())

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

        client = make_unifi_client()
        client._auth._authenticated = True

        with aioresponses() as m:
            m.post(system_log_url(), status=200, payload=self._page_body([], 1, page=0))
            await client.fetch_system_log_alarms(since=None)
            calls = find_calls(m, "POST", system_log_url())

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
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(system_log_url(), status=401)
            with pytest.raises(InvalidAuthError):
                await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_network_error_raises_cannot_connect(self):
        """aiohttp.ClientError during fetch must raise CannotConnectError."""
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(system_log_url(), exception=aiohttp.ClientConnectionError("unreachable"))
            with pytest.raises(CannotConnectError):
                await client.fetch_system_log_alarms()

    @pytest.mark.asyncio
    async def test_redirect_raises_cannot_connect(self):
        """3xx from the system-log endpoint must raise CannotConnectError."""
        client = make_unifi_client()
        client._auth._authenticated = True
        with aioresponses() as m:
            m.post(system_log_url(), status=301)
            with pytest.raises(CannotConnectError, match="redirect"):
                await client.fetch_system_log_alarms()
