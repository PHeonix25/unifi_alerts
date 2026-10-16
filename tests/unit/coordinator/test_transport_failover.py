"""Multi-poll transport failover tests for UniFiAlertsCoordinator (#387).

These drive full ``_async_update_data()`` polls against a mocked client to pin
down how the coordinator moves between the v2 system-log transport and the
legacy alarm transport over time. Single-call dispatch and the probe
cache/backoff internals are covered in ``test_polling.py`` and
``test_system_log_probe.py``; this module covers the sequences:

- A transient v2 probe failure falls back to legacy for that poll, keeps using
  legacy through the probe backoff window, and returns to v2 once the probe
  recovers (legacy endpoint still alive).
- Once the client has confirmed the legacy endpoint is dead (UniFi Network
  10.6+, #406), the coordinator never falls back to it: transient v2 trouble
  fails or retries on v2 instead.
- Once v2 is confirmed, a failing v2 fetch fails that poll (``UpdateFailed``)
  and the next poll retries v2; there is no mid-poll switch to legacy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.unifi_alerts.const import CATEGORY_SECURITY_THREAT
from custom_components.unifi_alerts.coordinator import _PROBE_FAIL_LIMIT
from custom_components.unifi_alerts.models import UniFiAlert
from custom_components.unifi_alerts.unifi_auth import CannotConnectError, InvalidAuthError
from custom_components.unifi_alerts.unifi_client import AlarmEndpointUnavailableError

from .conftest import make_full_coordinator, make_hass_and_client

# Distinct counts per transport so a test can tell which one fed a poll.
LEGACY_OPEN_COUNT = 1
V2_OPEN_COUNT = 2


def _legacy_result() -> dict[str, list[UniFiAlert]]:
    """One security alarm, as returned by the legacy ``categorise_alarms()``."""
    return {
        CATEGORY_SECURITY_THREAT: [
            UniFiAlert(
                category=CATEGORY_SECURITY_THREAT,
                message="legacy alarm",
                received_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        ]
    }


def _v2_events() -> list[dict]:
    """Two NEW security events, as returned by ``fetch_system_log_alarms()``."""
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    return [
        {
            "key": "THREAT_BLOCKED",
            "category": "SECURITY",
            "status": "NEW",
            "timestamp": now_ms - offset,
            "message_raw": "Threat blocked.",
            "parameters": {},
            "severity": "HIGH",
        }
        for offset in (60_000, 120_000)
    ]


def _make_coordinator(*, legacy_dead: bool = False):
    """Build a coordinator whose client serves both transports.

    ``discovered_alarm_url`` reports a cached legacy URL so
    ``resolved_transport`` reads "legacy" while v2 is not confirmed.
    """
    hass, client = make_hass_and_client()
    client.categorise_alarms = AsyncMock(return_value=_legacy_result())
    client.unrecognised_keys = {}
    client.fetch_system_log_alarms = AsyncMock(return_value=_v2_events())
    client.legacy_alarm_endpoint_confirmed_unavailable.return_value = legacy_dead
    client.discovered_alarm_url = lambda site: (
        None if legacy_dead else "https://192.168.1.1/proxy/network/api/s/default/list/alarm"
    )
    return make_full_coordinator(hass, client), client


def _open_count(coord) -> int:
    return coord.get_category_state(CATEGORY_SECURITY_THREAT).open_count


class TestTransientV2FailureWithLiveLegacy:
    """v2 probe trouble while the legacy endpoint still works."""

    @pytest.mark.asyncio
    async def test_transient_probe_failure_uses_legacy_then_returns_to_v2(self):
        """A single failed probe serves that poll from legacy; the next poll re-probes and uses v2."""
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(side_effect=[None, True])

        await coord._async_update_data()

        assert _open_count(coord) == LEGACY_OPEN_COUNT
        client.categorise_alarms.assert_awaited_once()
        client.fetch_system_log_alarms.assert_not_awaited()
        assert coord.resolved_transport == "legacy"

        await coord._async_update_data()

        assert _open_count(coord) == V2_OPEN_COUNT
        client.fetch_system_log_alarms.assert_awaited_once()
        # Legacy was not consulted again once v2 answered the probe.
        client.categorise_alarms.assert_awaited_once()
        assert coord.resolved_transport == "v2"

    @pytest.mark.asyncio
    async def test_polls_keep_using_legacy_through_backoff_without_reprobing(self):
        """After the probe-failure limit, polls stay on legacy and stop hitting the probe."""
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        extra_polls_in_backoff = 3

        for _ in range(_PROBE_FAIL_LIMIT + extra_polls_in_backoff):
            await coord._async_update_data()
            assert _open_count(coord) == LEGACY_OPEN_COUNT

        # Probed once per poll until the limit tripped, then not at all.
        assert client.probe_system_log_endpoint.await_count == _PROBE_FAIL_LIMIT
        assert client.categorise_alarms.await_count == _PROBE_FAIL_LIMIT + extra_polls_in_backoff
        client.fetch_system_log_alarms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_v2_resumes_when_backoff_expires_and_probe_succeeds(self):
        """Once the backoff window opens and the probe succeeds, polls move to v2 and stay there."""
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        for _ in range(_PROBE_FAIL_LIMIT):
            await coord._async_update_data()
        assert coord._probe_backoff_until is not None
        legacy_polls_so_far = client.categorise_alarms.await_count

        # The controller's v2 endpoint is healthy again and the backoff has run out.
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        coord._probe_backoff_until = datetime.now(UTC) - timedelta(seconds=1)

        await coord._async_update_data()
        await coord._async_update_data()

        assert _open_count(coord) == V2_OPEN_COUNT
        assert client.fetch_system_log_alarms.await_count == 2
        # No further legacy polls, and v2 is cached so the probe ran exactly once.
        assert client.categorise_alarms.await_count == legacy_polls_so_far
        client.probe_system_log_endpoint.assert_awaited_once()
        assert coord.resolved_transport == "v2"

    @pytest.mark.asyncio
    async def test_still_failing_probe_after_backoff_expiry_returns_to_legacy(self):
        """An expired backoff that re-probes into another transient failure keeps polling legacy."""
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        for _ in range(_PROBE_FAIL_LIMIT):
            await coord._async_update_data()
        coord._probe_backoff_until = datetime.now(UTC) - timedelta(seconds=1)
        probes_before = client.probe_system_log_endpoint.await_count

        await coord._async_update_data()

        assert client.probe_system_log_endpoint.await_count == probes_before + 1
        assert _open_count(coord) == LEGACY_OPEN_COUNT
        client.fetch_system_log_alarms.assert_not_awaited()


class TestDeadLegacyIsNeverAFallback:
    """The legacy endpoint is confirmed gone (UniFi Network 10.6+, #406)."""

    @pytest.mark.asyncio
    async def test_transient_probe_failures_stay_on_v2_through_and_past_backoff(self):
        """Repeated probe failures must not push polls onto the dead legacy path.

        Before #406 the backoff pinned polls to legacy for an hour, so on 10.6+
        firmware every poll failed. Now each poll fetches from v2 directly.
        """
        coord, client = _make_coordinator(legacy_dead=True)
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        polls = _PROBE_FAIL_LIMIT + 3

        for _ in range(polls):
            await coord._async_update_data()
            assert _open_count(coord) == V2_OPEN_COUNT

        client.categorise_alarms.assert_not_awaited()
        assert client.fetch_system_log_alarms.await_count == polls

    @pytest.mark.asyncio
    async def test_v2_fetch_failure_fails_the_poll_and_does_not_touch_legacy(self):
        """A transient v2 fetch error with dead legacy raises UpdateFailed, keeps the last
        known counts, never calls legacy, and the next poll recovers on v2."""
        coord, client = _make_coordinator(legacy_dead=True)
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        client.fetch_system_log_alarms = AsyncMock(
            side_effect=[_v2_events(), CannotConnectError("TimeoutError"), _v2_events()]
        )

        await coord._async_update_data()
        assert _open_count(coord) == V2_OPEN_COUNT

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        assert _open_count(coord) == V2_OPEN_COUNT, "failed poll must not zero the last known count"
        client.categorise_alarms.assert_not_awaited()

        await coord._async_update_data()
        assert _open_count(coord) == V2_OPEN_COUNT
        client.categorise_alarms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_found_dead_mid_life_switches_to_v2_and_sticks(self):
        """Legacy is tried once, discovered dead, and never tried again on later polls.

        Models UniFiClient: the first ``categorise_alarms()`` exhausts the probe
        chain, records the site as confirmed-dead, and raises.
        """
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(return_value=None)
        confirmed_dead = {"value": False}

        async def legacy_discovery(site):
            confirmed_dead["value"] = True
            raise AlarmEndpointUnavailableError("no legacy alarm endpoint")

        client.categorise_alarms = AsyncMock(side_effect=legacy_discovery)
        client.legacy_alarm_endpoint_confirmed_unavailable.side_effect = lambda site: (
            confirmed_dead["value"]
        )

        await coord._async_update_data()
        assert _open_count(coord) == V2_OPEN_COUNT

        await coord._async_update_data()
        await coord._async_update_data()

        assert _open_count(coord) == V2_OPEN_COUNT
        client.categorise_alarms.assert_awaited_once()
        assert client.fetch_system_log_alarms.await_count == 3


class TestConfirmedV2Failure:
    """v2 has answered the probe, then a later fetch fails."""

    @pytest.mark.asyncio
    async def test_fetch_failure_fails_the_poll_instead_of_switching_to_legacy(self):
        """With v2 confirmed, a failing fetch raises UpdateFailed even though legacy is alive.

        This is the current design, not the issue-text expectation ("v2 times out
        -> fall back to legacy"): legacy is chosen only when the probe says v2 is
        unavailable. The v2 verdict is cached, so the next poll goes straight back
        to v2 without re-probing or touching legacy.
        """
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            side_effect=[CannotConnectError("TimeoutError"), _v2_events()]
        )

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        client.categorise_alarms.assert_not_awaited()

        await coord._async_update_data()

        assert _open_count(coord) == V2_OPEN_COUNT
        client.categorise_alarms.assert_not_awaited()
        client.probe_system_log_endpoint.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v2_auth_rejection_requests_reauth_without_legacy_fallback(self):
        """A 401 from the v2 fetch must trigger reauth, not be masked by a legacy fallback."""
        coord, client = _make_coordinator()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(side_effect=InvalidAuthError("401"))

        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

        client.categorise_alarms.assert_not_awaited()
