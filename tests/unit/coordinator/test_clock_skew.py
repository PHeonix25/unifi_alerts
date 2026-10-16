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
from custom_components.unifi_alerts.coordinator import UniFiAlertsCoordinator
from custom_components.unifi_alerts.models import CategoryState, UniFiAlert

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

    @pytest.mark.asyncio
    async def test_naive_polled_timestamp_does_not_crash_watermark_tracking(self):
        """A naive (tz-less) ``received_at`` from a polled alarm must not raise
        when compared against an already-aware ``last_alarm_received_at``.

        Regression: production alarms are always tz-aware, but polling after
        an already-alerting webhook push exercised a bare `>` comparison
        between whatever the poll returned and the webhook-derived (aware)
        watermark source, raising ``TypeError: can't compare offset-naive and
        offset-aware datetimes`` if the two ever disagreed on tzinfo.
        """
        hass, client = make_hass_and_client()
        naive_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="naive timestamp",
            received_at=datetime(2024, 1, 1, 10, 0),  # no tzinfo
        )
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [naive_alert]})
        coord = make_full_coordinator(hass, client)

        webhook_alert = make_alert(CATEGORY_NETWORK_WAN, "webhook alert")
        coord.push_alert(CATEGORY_NETWORK_WAN, webhook_alert)

        # Must not raise.
        await coord._async_update_data()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_alarm_received_at == webhook_alert.received_at


class TestWatermarkSourceEdgeCases:
    """Direct coverage of the branches that only trigger on out-of-order timestamps."""

    def test_apply_alert_does_not_regress_last_alarm_received_at_on_older_alert(self):
        """A later-arriving alert with an older received_at must not move
        last_alarm_received_at backwards."""
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        newer = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="newer",
            received_at=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        )
        older = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="older",
            received_at=datetime(2024, 6, 1, 11, 0, tzinfo=UTC),
        )

        state.apply_alert(newer)
        state.apply_alert(older)

        assert state.last_alarm_received_at == newer.received_at

    def test_track_newest_seen_noop_on_empty_alerts(self):
        """_track_newest_seen must leave last_alarm_received_at untouched
        when handed an empty alert list."""
        state = CategoryState(category=CATEGORY_NETWORK_WAN)

        UniFiAlertsCoordinator._track_newest_seen(state, [])

        assert state.last_alarm_received_at is None


class TestFutureAndPastTimestamps:
    """Alerts dated in the past, present and future (#387)."""

    @pytest.mark.asyncio
    async def test_polled_past_present_future_alarms_are_all_counted(self):
        """Alarms an hour old, current, and an hour ahead of HA all count as open;
        the future one becomes the active alert and the Clear watermark."""
        now = datetime.now(UTC)
        past = UniFiAlert(
            category=CATEGORY_NETWORK_WAN, message="past", received_at=now - timedelta(hours=1)
        )
        present = UniFiAlert(category=CATEGORY_NETWORK_WAN, message="present", received_at=now)
        future = UniFiAlert(
            category=CATEGORY_NETWORK_WAN, message="future", received_at=now + timedelta(hours=1)
        )
        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(
            return_value={CATEGORY_NETWORK_WAN: [past, future, present]}
        )
        coord = make_full_coordinator(hass, client)
        _mock_store(coord)

        await coord._async_update_data()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 3
        assert state.is_alerting is True
        assert state.last_alert is future
        assert state.last_alarm_received_at == future.received_at

        await coord.async_clear_category(CATEGORY_NETWORK_WAN)

        assert state.last_cleared_at == future.received_at
        await coord._async_update_data()
        assert state.open_count == 0
        assert state.is_alerting is False

    @pytest.mark.asyncio
    async def test_alarm_older_than_future_watermark_is_not_recounted(self):
        """After Clear anchors to a future-dated alarm, a genuinely newer alarm still counts
        while one a second older than the watermark does not."""
        watermark = datetime.now(UTC) + timedelta(hours=1)
        anchor = UniFiAlert(category=CATEGORY_NETWORK_WAN, message="anchor", received_at=watermark)
        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [anchor]})
        coord = make_full_coordinator(hass, client)
        _mock_store(coord)
        await coord._async_update_data()
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)

        just_older = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="just older",
            received_at=watermark - timedelta(seconds=1),
        )
        just_newer = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="just newer",
            received_at=watermark + timedelta(seconds=1),
        )
        client.categorise_alarms = AsyncMock(
            return_value={CATEGORY_NETWORK_WAN: [anchor, just_older, just_newer]}
        )
        await coord._async_update_data()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 1
        assert state.last_alert is just_newer

    def test_push_alert_with_future_received_at_is_accepted(self):
        """A webhook alert stamped one hour ahead still alerts, counts and is tracked as newest."""
        coord = make_coordinator()
        future = datetime.now(UTC) + timedelta(hours=1)
        alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN, message="future push", key="K1", received_at=future
        )

        coord.push_alert(CATEGORY_NETWORK_WAN, alert)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is True
        assert state.alert_count == 1
        assert state.open_count == 1
        assert state.last_alert is alert
        assert state.last_alarm_received_at == future

    def test_older_push_after_future_push_does_not_regress_newest_seen(self):
        """A past-dated push arriving after a future-dated one is accepted but the
        newest-seen time (the Clear watermark source) stays on the future value."""
        coord = make_coordinator()
        now = datetime.now(UTC)
        future = now + timedelta(hours=1)
        coord.push_alert(
            CATEGORY_NETWORK_WAN,
            UniFiAlert(category=CATEGORY_NETWORK_WAN, message="f", key="KF", received_at=future),
        )
        coord.push_alert(
            CATEGORY_NETWORK_WAN,
            UniFiAlert(
                category=CATEGORY_NETWORK_WAN,
                message="p",
                key="KP",
                received_at=now - timedelta(hours=1),
            ),
        )

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.alert_count == 2
        assert state.last_alarm_received_at == future

    @pytest.mark.asyncio
    async def test_push_after_clear_with_future_watermark_still_alerts(self):
        """A fast controller clock must not swallow later alerts: after Clear anchors to a
        future time, a push stamped at the (earlier) HA time still turns the category on."""
        coord = make_coordinator()
        future = datetime.now(UTC) + timedelta(hours=1)
        coord.push_alert(
            CATEGORY_NETWORK_WAN,
            UniFiAlert(category=CATEGORY_NETWORK_WAN, message="f", key="KF", received_at=future),
        )
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is False
        assert state.last_cleared_at == future

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN, "later", key="KL"))

        assert state.is_alerting is True
        assert state.alert_count == 2
        assert state.last_alert.message == "later"


class TestTimezoneOffsets:
    """Polled ISO timestamps carrying different UTC offsets are compared by instant (#387)."""

    @pytest.mark.asyncio
    async def test_watermark_comparison_is_by_instant_across_offsets(self):
        """The same instant written as +10:00, -05:00 and +00:00 is equal for the watermark.

        All three are 10:00 UTC. After Clear none re-count; an alarm one second later,
        written in yet another offset, does.
        """

        def alarm(ts: str) -> UniFiAlert:
            return UniFiAlert.from_api_alarm(CATEGORY_NETWORK_WAN, {"msg": ts, "datetime": ts})

        same_instant = [
            alarm("2026-06-01T20:00:00+10:00"),
            alarm("2026-06-01T05:00:00-05:00"),
            alarm("2026-06-01T10:00:00+00:00"),
        ]
        assert {a.received_at for a in same_instant} == {datetime(2026, 6, 1, 10, 0, tzinfo=UTC)}
        assert len({a.received_at.utcoffset() for a in same_instant}) == 3

        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: same_instant})
        coord = make_full_coordinator(hass, client)
        _mock_store(coord)
        await coord._async_update_data()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 3

        await coord.async_clear_category(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        await coord._async_update_data()
        assert state.open_count == 0

        one_second_later = alarm("2026-06-01T01:00:01-09:00")  # 10:00:01 UTC
        client.categorise_alarms = AsyncMock(
            return_value={CATEGORY_NETWORK_WAN: [*same_instant, one_second_later]}
        )
        await coord._async_update_data()
        assert state.open_count == 1
        assert state.last_alert is one_second_later

    def test_naive_iso_timestamp_from_controller_is_treated_as_utc_for_tracking(self):
        """A tz-less ISO string parses naive; watermark tracking normalises it to UTC."""
        naive = UniFiAlert.from_api_alarm(
            CATEGORY_NETWORK_WAN, {"msg": "naive", "datetime": "2026-06-01T10:00:00"}
        )
        assert naive.received_at.tzinfo is None

        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        state.apply_alert(naive)

        assert state.last_alarm_received_at == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        raises=TypeError,
        reason=(
            "Known gap (#387): UniFiAlert.from_api_alarm() keeps a tz-less ISO string naive, "
            "and _async_update_data() compares received_at to the aware last_cleared_at "
            "without ensure_aware(), so every poll after a Clear raises TypeError."
        ),
    )
    async def test_naive_polled_timestamp_after_clear_does_not_break_polling(self):
        """A tz-less ISO alarm timestamp should be treated as UTC when polled after a Clear."""
        naive = UniFiAlert.from_api_alarm(
            CATEGORY_NETWORK_WAN, {"msg": "naive", "datetime": "2026-06-01T10:00:00"}
        )
        hass, client = make_hass_and_client()
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [naive]})
        coord = make_full_coordinator(hass, client)
        _mock_store(coord)
        await coord._async_update_data()
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)

        await coord._async_update_data()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 0
