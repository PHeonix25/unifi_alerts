"""Tests for the Clear watermark under controller/HA clock skew (#268).

Prior behaviour stamped the watermark from the HA host clock
(``datetime.now(UTC)``) while polled alarms carry ``received_at`` timestamps
parsed from the controller's own clock. When the two clocks disagree, that
mismatch either re-counts already-acknowledged alarms (controller fast) or
silently drops genuinely new ones (controller slow). The fix anchors the
watermark to the newest ``received_at`` already known for the category,
falling back to the HA clock only when nothing has ever been seen, making
the ``open_count``/``is_alerting`` comparison controller-clock vs
controller-clock, immune to skew in either direction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.unifi_alerts.const import CATEGORY_NETWORK_WAN
from custom_components.unifi_alerts.models import UniFiAlert

from .conftest import make_alert, make_coordinator, make_full_coordinator, make_hass_and_client


def _mock_store(coord) -> None:
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()


class TestClockSkewAcrossClear:
    """Controller clock offset must not affect open_count/is_alerting correctness."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "controller_offset",
        [
            pytest.param(timedelta(minutes=15), id="controller-clock-fast"),
            pytest.param(timedelta(minutes=-15), id="controller-clock-slow"),
        ],
    )
    async def test_clear_watermark_excludes_already_seen_alarms_regardless_of_skew(
        self, controller_offset
    ):
        """Clearing must exclude every alarm already known, whether the
        controller's clock is ahead of or behind the HA host clock.

        The controller's timeline is simulated by offsetting every
        ``received_at`` from a real "now" by ``controller_offset``: the
        offset itself never needs to be measured or corrected (out of scope
        per #268); only the comparison must be internally consistent.
        """
        controller_now = datetime.now(UTC) + controller_offset
        hass, client = make_hass_and_client()

        first_batch = [
            UniFiAlert(
                category=CATEGORY_NETWORK_WAN,
                message="first",
                received_at=controller_now - timedelta(minutes=10),
            ),
            UniFiAlert(
                category=CATEGORY_NETWORK_WAN,
                message="second",
                received_at=controller_now - timedelta(minutes=5),
            ),
        ]
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: first_batch})

        coord = make_full_coordinator(hass, client)
        _mock_store(coord)

        # First poll discovers both alarms.
        await coord._async_update_data()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is True
        assert state.open_count == 2

        # Clear: watermark must be anchored to the newest alarm already
        # known (controller_now - 5min), not to the real HA clock.
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is False
        assert state.last_cleared_at == controller_now - timedelta(minutes=5)

        # Re-polling the same (already-seen) alarms must not re-count them
        # or re-assert is_alerting, no matter which way the clock is skewed.
        await coord._async_update_data()
        assert state.open_count == 0
        assert state.is_alerting is False

        # A genuinely new alarm on the controller's own timeline must still
        # be picked up after Clear.
        new_alarm = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="new after clear",
            received_at=controller_now + timedelta(minutes=1),
        )
        client.categorise_alarms = AsyncMock(
            return_value={CATEGORY_NETWORK_WAN: [*first_batch, new_alarm]}
        )
        await coord._async_update_data()
        assert state.open_count == 1
        assert state.is_alerting is True
        assert state.last_alert is new_alarm

    @pytest.mark.asyncio
    async def test_clear_falls_back_to_ha_clock_when_nothing_ever_seen(self):
        """With no alarm ever observed, Clear must fall back to datetime.now(UTC)."""
        hass, client = make_hass_and_client()
        coord = make_full_coordinator(hass, client)
        _mock_store(coord)

        before = datetime.now(UTC)
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)
        after = datetime.now(UTC)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at is not None
        assert before <= state.last_cleared_at <= after

    @pytest.mark.asyncio
    async def test_webhook_push_advances_watermark_source_too(self):
        """push_alert (webhook path) must also feed last_alarm_received_at,
        so a Clear right after a webhook-only alert anchors to that alert's
        received_at rather than HA now."""
        coord = make_coordinator()
        _mock_store(coord)

        alert = make_alert(CATEGORY_NETWORK_WAN, "webhook alert")
        coord.push_alert(CATEGORY_NETWORK_WAN, alert)

        await coord.async_clear_category(CATEGORY_NETWORK_WAN)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at == alert.received_at
