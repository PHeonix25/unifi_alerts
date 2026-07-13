"""Tests for UniFiAlertsCoordinator: init, rollups, push, dedup, and push/poll races.

Split by behaviour area (#283) alongside test_polling.py,
test_persistence.py, and test_autoclear.py in this package.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    CONF_MIN_SEVERITY,
)
from custom_components.unifi_alerts.models import UniFiAlert
from custom_components.unifi_alerts.severity import (
    MIN_SEVERITY_NO_FILTER,
    MIN_SEVERITY_ORDER,
    SEVERITY_ORDER,
)

from .conftest import make_alert, make_coordinator, make_full_coordinator, make_hass_and_client

# Minimum_Severity_Setting values that have at least one Severity_Level
# strictly below them. LOW is excluded — it is the lowest Severity_Level, so
# no alert can ever be "strictly below" a minimum of LOW.
_BELOW_THRESHOLD_MINIMUMS: list[str] = SEVERITY_ORDER[1:]


class TestCoordinatorInit:
    def test_all_categories_initialised(self):
        coord = make_coordinator()
        for cat in ALL_CATEGORIES:
            state = coord.get_category_state(cat)
            assert state is not None
            assert state.category == cat

    def test_only_enabled_categories_are_enabled(self):
        coord = make_coordinator(enabled=[CATEGORY_NETWORK_WAN])
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).enabled is True
        assert coord.get_category_state(CATEGORY_SECURITY_THREAT).enabled is False


class TestPushAlert:
    def test_push_sets_alerting(self):
        coord = make_coordinator()
        alert = make_alert(CATEGORY_NETWORK_WAN)
        coord.async_set_updated_data = MagicMock()
        coord.push_alert(CATEGORY_NETWORK_WAN, alert)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is True
        assert state.last_alert is alert

    def test_push_increments_count(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        # Distinct keys so the per-(category, alert_key) dedup window does not
        # collapse them — three different events should produce three counts.
        for i in range(3):
            coord.push_alert(
                CATEGORY_NETWORK_WAN,
                make_alert(CATEGORY_NETWORK_WAN, f"alert {i}", key=f"EVT_TEST_{i}"),
            )
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 3

    def test_push_records_last_webhook_at(self):
        """push_alert must stamp last_webhook_at from the alert's receipt time."""
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        alert = make_alert(CATEGORY_NETWORK_WAN)
        coord.push_alert(CATEGORY_NETWORK_WAN, alert)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_webhook_at == alert.received_at

    def test_polling_does_not_set_last_webhook_at(self):
        """The polling path must never stamp last_webhook_at (webhook-only signal)."""
        coord = make_coordinator()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        # Simulate the poll path mutating alert state directly.
        state.is_alerting = True
        state.last_alert = make_alert(CATEGORY_NETWORK_WAN)
        assert state.last_webhook_at is None

    def test_push_to_disabled_category_ignored(self):
        coord = make_coordinator(enabled=[CATEGORY_NETWORK_WAN])
        coord.async_set_updated_data = MagicMock()
        alert = make_alert(CATEGORY_SECURITY_THREAT)
        coord.push_alert(CATEGORY_SECURITY_THREAT, alert)
        state = coord.get_category_state(CATEGORY_SECURITY_THREAT)
        assert state.is_alerting is False

    def test_push_notifies_listeners(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        coord.async_set_updated_data.assert_called_once()

    def test_push_to_unknown_category_logs_warning(self):
        from unittest.mock import patch as _patch

        coord = make_coordinator()
        alert = make_alert("nonexistent_category")
        with _patch("custom_components.unifi_alerts.coordinator._LOGGER") as mock_logger:
            coord.push_alert("nonexistent_category", alert)
        mock_logger.warning.assert_called_once()
        assert "unknown category" in mock_logger.warning.call_args[0][0]


class TestRollupProperties:
    def test_any_alerting_false_when_no_alerts(self):
        coord = make_coordinator()
        assert coord.any_alerting is False

    def test_any_alerting_true_after_push(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert coord.any_alerting is True

    def test_rollup_count_sums_all_categories(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        coord.push_alert(CATEGORY_SECURITY_THREAT, make_alert(CATEGORY_SECURITY_THREAT))
        assert coord.rollup_alert_count == 2

    def test_rollup_last_alert_returns_most_recent(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        t1 = datetime(2024, 1, 1, 10, 0, 0)
        t2 = datetime(2024, 1, 1, 10, 0, 1)
        first = UniFiAlert(category=CATEGORY_NETWORK_WAN, message="first", received_at=t1)
        second = UniFiAlert(category=CATEGORY_SECURITY_THREAT, message="second", received_at=t2)
        coord.push_alert(CATEGORY_NETWORK_WAN, first)
        coord.push_alert(CATEGORY_SECURITY_THREAT, second)
        last = coord.rollup_last_alert
        assert last is not None
        assert last.message == "second"

    def test_rollup_last_alert_none_when_no_alerts(self):
        coord = make_coordinator()
        assert coord.rollup_last_alert is None


class TestPushDedup:
    """Per-(category, alert_key) cooldown suppresses webhook flood.

    Without this, a misconfigured Alarm Manager or noisy category can flood
    the webhook endpoint, generating an alert_count increment + event entity
    fire for every POST. The dedup window collapses repeats while still
    allowing distinct events through.
    """

    def test_duplicate_within_window_is_suppressed(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "first", key="EVT_GW_WANTransition")
        a2 = make_alert(CATEGORY_NETWORK_WAN, "second-but-same-key", key="EVT_GW_WANTransition")
        coord.push_alert(CATEGORY_NETWORK_WAN, a1)
        coord.push_alert(CATEGORY_NETWORK_WAN, a2)
        # Only the first push counted; the second was suppressed
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.alert_count == 1
        # async_set_updated_data was only called once (no spurious notify)
        assert coord.async_set_updated_data.call_count == 1

    def test_distinct_keys_are_not_suppressed(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "first", key="EVT_GW_WANTransition")
        a2 = make_alert(CATEGORY_NETWORK_WAN, "different", key="EVT_GW_Failover")
        coord.push_alert(CATEGORY_NETWORK_WAN, a1)
        coord.push_alert(CATEGORY_NETWORK_WAN, a2)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.alert_count == 2

    def test_same_key_in_different_category_is_not_suppressed(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "wan", key="EVT_X")
        a2 = make_alert(CATEGORY_SECURITY_THREAT, "threat", key="EVT_X")
        coord.push_alert(CATEGORY_NETWORK_WAN, a1)
        coord.push_alert(CATEGORY_SECURITY_THREAT, a2)
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 1
        assert coord.get_category_state(CATEGORY_SECURITY_THREAT).alert_count == 1

    def test_dup_after_window_elapsed_is_accepted(self):
        """When the cooldown has passed, the same (category, key) is allowed."""
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "first", key="EVT_GW_WANTransition")
        a2 = make_alert(CATEGORY_NETWORK_WAN, "second", key="EVT_GW_WANTransition")

        # Patch time.monotonic to advance past the dedup window between pushes
        from custom_components.unifi_alerts.const import WEBHOOK_DEDUP_WINDOW_SECONDS

        clock = [0.0]
        with patch(
            "custom_components.unifi_alerts.coordinator.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            coord.push_alert(CATEGORY_NETWORK_WAN, a1)
            clock[0] = WEBHOOK_DEDUP_WINDOW_SECONDS + 0.01
            coord.push_alert(CATEGORY_NETWORK_WAN, a2)

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 2

    def test_distinct_keyless_alerts_are_not_suppressed(self):
        """Alerts with no `key` field (e.g. the empty-body webhook ping) have no
        identity to dedup on — two distinct keyless alerts in the same window
        must both count, unlike two keyed alerts sharing the same key (issue #263)."""
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "first")  # key=""
        a2 = make_alert(CATEGORY_NETWORK_WAN, "second")  # key=""
        coord.push_alert(CATEGORY_NETWORK_WAN, a1)
        coord.push_alert(CATEGORY_NETWORK_WAN, a2)
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 2
        assert coord.async_set_updated_data.call_count == 2
        # Keyless pushes must not pollute _last_push_at — only real keys are tracked.
        assert coord._last_push_at == {}

    def test_last_push_at_dict_bounded_by_dedup_window(self):
        """Regression: ``_last_push_at`` must not grow without bound.

        A misconfigured controller emitting high-cardinality alert keys could
        otherwise accumulate one entry per unique key forever. The dict is
        opportunistically pruned to entries whose last-push timestamp is
        within ``WEBHOOK_DEDUP_WINDOW_SECONDS`` of the most recent push, so
        its size stays bounded regardless of the controller's lifetime
        event-key cardinality.
        """
        from custom_components.unifi_alerts.const import WEBHOOK_DEDUP_WINDOW_SECONDS

        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()

        clock = [0.0]
        with patch(
            "custom_components.unifi_alerts.coordinator.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            # Burst of 50 distinct keys at t=0
            for i in range(50):
                coord.push_alert(
                    CATEGORY_NETWORK_WAN,
                    make_alert(CATEGORY_NETWORK_WAN, f"alert {i}", key=f"EVT_BURST_{i}"),
                )
            # All 50 are still within the window — dict holds them all
            assert len(coord._last_push_at) == 50

            # Jump past the window — the next push must prune the burst
            clock[0] = WEBHOOK_DEDUP_WINDOW_SECONDS + 1.0
            coord.push_alert(
                CATEGORY_NETWORK_WAN,
                make_alert(CATEGORY_NETWORK_WAN, "fresh", key="EVT_FRESH"),
            )
            # Only the fresh entry remains; the 50 stale ones were pruned.
            assert len(coord._last_push_at) == 1
            assert (CATEGORY_NETWORK_WAN, "EVT_FRESH") in coord._last_push_at


class TestRollupOpenCount:
    @pytest.mark.parametrize(
        ("enabled", "open_counts", "expected_rollup"),
        [
            pytest.param(
                None,
                {CATEGORY_NETWORK_WAN: 3, CATEGORY_SECURITY_THREAT: 2},
                5,
                id="sums-enabled-categories",
            ),
            pytest.param(
                [CATEGORY_NETWORK_WAN],
                {CATEGORY_NETWORK_WAN: 3, CATEGORY_SECURITY_THREAT: 99},
                3,
                id="excludes-disabled-categories",
            ),
            pytest.param(None, {}, 0, id="zero-when-no-alarms"),
        ],
    )
    def test_rollup_open_count(self, enabled, open_counts, expected_rollup):
        coord = make_coordinator(enabled=enabled)
        for category, count in open_counts.items():
            coord.get_category_state(category).open_count = count
        assert coord.rollup_open_count == expected_rollup


class TestWebhookMidPollRace:
    """A webhook arriving while _async_update_data() is mid-await must not regress is_alerting.

    The coordinator's polling path only sets is_alerting=True when it finds open
    alarms and is_alerting is currently False. It never clears is_alerting on its
    own. So if a webhook fires during a poll and asserts is_alerting=True, the
    poll completing with an empty result cannot clobber that state — the poll
    simply zeroes open_count and leaves is_alerting untouched.
    """

    @pytest.mark.asyncio
    async def test_webhook_during_poll_does_not_regress_is_alerting(self):

        gate = asyncio.Event()  # held open until the test releases it

        async def blocking_categorise_alarms(site):
            # Block the poll mid-await until the test fires the webhook
            await gate.wait()
            # Return empty list — the regression scenario: poll sees no alarms
            return {}

        hass, client = make_hass_and_client()
        client.categorise_alarms = blocking_categorise_alarms
        coord = make_full_coordinator(hass, client)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is False

        # Start the poll as a concurrent task; it will block on gate.wait()
        poll_task = asyncio.ensure_future(coord._async_update_data())

        # Yield to the event loop so poll_task enters blocking_categorise_alarms
        # and parks on gate.wait() before we interact with coordinator state.
        await asyncio.sleep(0)

        # Webhook arrives while the poll is suspended — asserts is_alerting
        webhook_alert = make_alert(CATEGORY_NETWORK_WAN, "webhook during poll", key="EVT_RACE")
        coord.push_alert(CATEGORY_NETWORK_WAN, webhook_alert)
        assert state.is_alerting is True

        # Release the gate: poll resumes, calls categorise_alarms, gets {}, and
        # zeroes open_count for categories with no alarms. It must NOT flip
        # is_alerting back to False.
        gate.set()
        await poll_task

        assert state.is_alerting is True

    @pytest.mark.asyncio
    async def test_clear_during_poll_is_not_undone_by_stale_poll_data(self):
        """A manual clear while a poll is mid-flight must not be re-opened by that poll.

        `_async_update_data` reads `state.last_cleared_at` only *after*
        `await self._fetch_categorised()` resolves (coordinator.py, watermark
        line inside the per-category loop), so a concurrent clear's fresh
        watermark is visible by the time the poll filters its (now-stale)
        alarm list. This test pins that ordering: the alarm the poll fetched
        predates the clear, so it must be filtered out and must not
        resurrect `is_alerting`. If the watermark were captured before the
        await instead (the regression this guards), the stale alarm would
        pass the filter and silently undo the user's clear.
        """

        gate = asyncio.Event()
        stale_alert = make_alert(CATEGORY_NETWORK_WAN, "stale pre-clear alarm")
        # UniFiAlert is frozen-ish only by convention; received_at is a plain
        # field, so backdating it here is the simplest way to simulate an
        # alarm that was already open when the poll started.
        stale_alert.received_at = datetime(2020, 1, 1, tzinfo=UTC)

        async def blocking_categorise_alarms(site):
            await gate.wait()
            return {CATEGORY_NETWORK_WAN: [stale_alert]}

        hass, client = make_hass_and_client()
        client.categorise_alarms = blocking_categorise_alarms
        coord = make_full_coordinator(hass, client)
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.apply_alert(stale_alert)  # the alarm was already open before the poll started
        assert state.is_alerting is True

        # Start the poll; it blocks on gate.wait() inside categorise_alarms,
        # already holding the pre-clear alarm list it will apply once resumed.
        poll_task = asyncio.ensure_future(coord._async_update_data())
        await asyncio.sleep(0)

        # Manually clear the category while the poll is still suspended.
        # async_clear_category awaits _async_persist_watermarks(), a genuine
        # yield point, so this interleaves with poll_task on the same loop.
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is False
        assert state.last_cleared_at is not None

        # Resume the poll: it applies the stale alarm list fetched before
        # the clear. Correct behaviour is to filter it out via the
        # now-current watermark and leave is_alerting False.
        gate.set()
        await poll_task

        assert state.is_alerting is False


class TestConcurrentPushDedup:
    """Two same-category webhook pushes becoming runnable at the same instant
    must not corrupt the dedup map or double-count, even though they arrive
    via genuinely concurrent tasks (the real shape of two overlapping HTTP
    POSTs). push_alert() itself is fully synchronous with no internal await,
    so once either task resumes past its own await point, it runs push_alert
    to completion before the other task gets a turn — this test pins that
    guarantee so a future change that makes push_alert (or its dedup-map
    mutation) awaiting-and-interruptible can't silently reintroduce a race.
    """

    @pytest.mark.asyncio
    async def test_concurrent_same_key_pushes_dedup_to_exactly_one(self):

        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        gate = asyncio.Event()

        async def push_after_gate(alert):
            await gate.wait()
            coord.push_alert(CATEGORY_NETWORK_WAN, alert)

        alert_a = make_alert(CATEGORY_NETWORK_WAN, "first", key="EVT_RACE")
        alert_b = make_alert(CATEGORY_NETWORK_WAN, "second-same-key", key="EVT_RACE")

        task_a = asyncio.ensure_future(push_after_gate(alert_a))
        task_b = asyncio.ensure_future(push_after_gate(alert_b))
        # Let both tasks reach gate.wait() and park there before releasing —
        # so they become runnable at the same instant, not one after the other.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        gate.set()
        await asyncio.gather(task_a, task_b)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        # Exactly one push must be recorded — the second is a dedup-window
        # duplicate of the first regardless of which task the loop ran first.
        assert state.alert_count == 1
        assert len(coord._last_push_at) == 1

    @pytest.mark.asyncio
    async def test_concurrent_different_key_pushes_both_recorded(self):
        """Distinct keys pushed concurrently must both be recorded independently."""

        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        gate = asyncio.Event()

        async def push_after_gate(alert):
            await gate.wait()
            coord.push_alert(CATEGORY_NETWORK_WAN, alert)

        alert_a = make_alert(CATEGORY_NETWORK_WAN, "first", key="EVT_RACE_A")
        alert_b = make_alert(CATEGORY_NETWORK_WAN, "second", key="EVT_RACE_B")

        task_a = asyncio.ensure_future(push_after_gate(alert_a))
        task_b = asyncio.ensure_future(push_after_gate(alert_b))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        gate.set()
        await asyncio.gather(task_a, task_b)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        # Both distinct keys must be counted — neither dedup entry must have
        # clobbered the other in the dict rebuild inside push_alert.
        assert state.alert_count == 2
        assert len(coord._last_push_at) == 2


class TestPushAlertOptimisticOpenCount:
    """push_alert must increment open_count optimistically.

    Field-confirmed: webhook fires update is_alerting and alert_count, but
    open_count only refreshed on the next REST poll (default 60 s). For up
    to one poll interval the binary sensor showed Problem while Open Count
    showed 0. push_alert now bumps open_count immediately and polling
    reconciles to the authoritative value on the next refresh.
    """

    @pytest.mark.parametrize(
        ("watermark", "expected_open_count"),
        [
            pytest.param(None, 1, id="no-watermark"),
            pytest.param(datetime(2020, 1, 1, tzinfo=UTC), 1, id="alert-after-watermark"),
            pytest.param(datetime(2030, 1, 1, tzinfo=UTC), 0, id="alert-before-watermark"),
        ],
    )
    def test_push_increments_open_count_based_on_watermark(self, watermark, expected_open_count):
        """push_alert bumps open_count only when the alert is after the watermark (or none is set).

        Webhook payloads use datetime.now(UTC), so a future watermark always
        puts the incoming alert "before" it (suppressed) while a past or
        absent watermark always puts it "after" (counted).
        """
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 0
        state.last_cleared_at = watermark

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))

        # apply_alert always runs (alert_count bumps); open_count only bumps
        # when the alert is not suppressed by the watermark.
        assert state.alert_count == 1
        assert state.open_count == expected_open_count

    def test_dedup_window_also_suppresses_open_count_increment(self):
        """Duplicate (category, key) within the dedup window must not double-count."""
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "first", key="EVT_GW_WANTransition")
        a2 = make_alert(CATEGORY_NETWORK_WAN, "second-same-key", key="EVT_GW_WANTransition")

        coord.push_alert(CATEGORY_NETWORK_WAN, a1)
        coord.push_alert(CATEGORY_NETWORK_WAN, a2)

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 1

    @pytest.mark.asyncio
    async def test_polling_clamps_optimistic_open_count_back_down(self):
        """If polling comes back lower than the optimistic count, polling wins.

        Covers the documented v1.5.0 reconciliation behaviour: push_alert is
        optimistic; the next poll is authoritative for low-volume controllers
        whose alarms are still in the /list/alarm response.
        """
        hass, client = make_hass_and_client()
        # Polling returns nothing for the WAN category — alarm has cleared
        # on the controller side already.
        client.categorise_alarms = AsyncMock(return_value={})
        coord = make_full_coordinator(hass, client)

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 1

        await coord._async_update_data()

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 0


class TestPushAlertSeverityGate:
    """Minimum_Severity_Setting gate on the webhook push path (push_alert)."""

    # Feature: minimum-severity-filter, Property 8: Below-threshold push on an enabled category is a true no-op
    @given(
        minimum=st.sampled_from(_BELOW_THRESHOLD_MINIMUMS),
        prior_is_alerting=st.booleans(),
        prior_alert_count=st.integers(min_value=0, max_value=1000),
        prior_open_count=st.integers(min_value=0, max_value=1000),
        has_prior_alert=st.booleans(),
        data=st.data(),
    )
    @settings(max_examples=25)
    def test_below_threshold_push_is_noop(
        self,
        minimum: str,
        prior_is_alerting: bool,
        prior_alert_count: int,
        prior_open_count: int,
        has_prior_alert: bool,
        data: st.DataObject,
    ) -> None:
        """A below-threshold push on an Enabled Category must leave is_alerting,
        alert_count, open_count, and last_alert unchanged from their values
        immediately before the call."""
        category = CATEGORY_NETWORK_WAN
        below_severities = SEVERITY_ORDER[: SEVERITY_ORDER.index(minimum)]
        severity = data.draw(st.sampled_from(below_severities))

        coord = make_coordinator(enabled=[category])
        coord.async_set_updated_data = MagicMock()
        coord._config[CONF_MIN_SEVERITY] = {category: minimum}

        state = coord.get_category_state(category)
        prior_last_alert = make_alert(category, "prior alert") if has_prior_alert else None
        state.is_alerting = prior_is_alerting
        state.alert_count = prior_alert_count
        state.open_count = prior_open_count
        state.last_alert = prior_last_alert

        alert = make_alert(category, "below-threshold alert")
        alert.severity = severity

        coord.push_alert(category, alert)

        assert state.is_alerting == prior_is_alerting
        assert state.alert_count == prior_alert_count
        assert state.open_count == prior_open_count
        assert state.last_alert is prior_last_alert

    # Feature: minimum-severity-filter, Property 11: last_webhook_at still advances on a gated push
    @given(
        minimum=st.sampled_from(_BELOW_THRESHOLD_MINIMUMS),
        prior_is_alerting=st.booleans(),
        prior_alert_count=st.integers(min_value=0, max_value=1000),
        prior_open_count=st.integers(min_value=0, max_value=1000),
        has_prior_alert=st.booleans(),
        data=st.data(),
    )
    @settings(max_examples=25)
    def test_below_threshold_push_still_advances_last_webhook_at(
        self,
        minimum: str,
        prior_is_alerting: bool,
        prior_alert_count: int,
        prior_open_count: int,
        has_prior_alert: bool,
        data: st.DataObject,
    ) -> None:
        """A below-threshold push on an Enabled Category must still update
        last_webhook_at to the alert's received_at, even though is_alerting,
        alert_count, open_count, and last_alert remain unchanged."""
        category = CATEGORY_NETWORK_WAN
        below_severities = SEVERITY_ORDER[: SEVERITY_ORDER.index(minimum)]
        severity = data.draw(st.sampled_from(below_severities))

        coord = make_coordinator(enabled=[category])
        coord.async_set_updated_data = MagicMock()
        coord._config[CONF_MIN_SEVERITY] = {category: minimum}

        state = coord.get_category_state(category)
        prior_last_alert = make_alert(category, "prior alert") if has_prior_alert else None
        state.is_alerting = prior_is_alerting
        state.alert_count = prior_alert_count
        state.open_count = prior_open_count
        state.last_alert = prior_last_alert
        state.last_webhook_at = None

        alert = make_alert(category, "below-threshold alert")
        alert.severity = severity

        coord.push_alert(category, alert)

        assert state.last_webhook_at == alert.received_at
        assert state.is_alerting == prior_is_alerting
        assert state.alert_count == prior_alert_count
        assert state.open_count == prior_open_count
        assert state.last_alert is prior_last_alert

    # Feature: minimum-severity-filter, Property 10: At-or-above-threshold or No_Filter push is accepted exactly as before this feature
    @given(
        gate_mode=st.sampled_from(["at_or_above", "no_filter"]),
        prior_is_alerting=st.booleans(),
        has_prior_alert=st.booleans(),
        watermark_case=st.sampled_from(["none", "past", "future"]),
        data=st.data(),
    )
    @settings(max_examples=25)
    def test_at_or_above_threshold_or_no_filter_push_is_accepted(
        self,
        gate_mode: str,
        prior_is_alerting: bool,
        has_prior_alert: bool,
        watermark_case: str,
        data: st.DataObject,
    ) -> None:
        """An at/above-threshold push, or any push when the category's
        Minimum_Severity_Setting is No_Filter, must be accepted exactly as it
        was before this feature: is_alerting set True, alert_count
        incremented by 1, last_alert updated to the pushed alert, and
        open_count incremented by 1 only when the alert is newer than the
        watermark."""
        category = CATEGORY_NETWORK_WAN
        prior_alert_count = data.draw(st.integers(min_value=0, max_value=1000))
        prior_open_count = data.draw(st.integers(min_value=0, max_value=1000))

        if gate_mode == "no_filter":
            minimum = MIN_SEVERITY_NO_FILTER
            severity = data.draw(st.sampled_from(SEVERITY_ORDER))
        else:
            minimum = data.draw(st.sampled_from(SEVERITY_ORDER))
            at_or_above_severities = SEVERITY_ORDER[SEVERITY_ORDER.index(minimum) :]
            severity = data.draw(st.sampled_from(at_or_above_severities))

        coord = make_coordinator(enabled=[category])
        coord.async_set_updated_data = MagicMock()
        coord._config[CONF_MIN_SEVERITY] = {category: minimum}

        state = coord.get_category_state(category)
        prior_last_alert = make_alert(category, "prior alert") if has_prior_alert else None
        state.is_alerting = prior_is_alerting
        state.alert_count = prior_alert_count
        state.open_count = prior_open_count
        state.last_alert = prior_last_alert

        alert = make_alert(category, "accepted alert")
        alert.severity = severity

        if watermark_case == "none":
            state.last_cleared_at = None
            expect_open_count_incremented = True
        elif watermark_case == "past":
            state.last_cleared_at = alert.received_at - timedelta(seconds=1)
            expect_open_count_incremented = True
        else:  # "future"
            state.last_cleared_at = alert.received_at + timedelta(seconds=1)
            expect_open_count_incremented = False

        coord.push_alert(category, alert)

        assert state.is_alerting is True
        assert state.alert_count == prior_alert_count + 1
        assert state.last_alert is alert
        expected_open_count = (
            prior_open_count + 1 if expect_open_count_incremented else prior_open_count
        )
        assert state.open_count == expected_open_count

    # Feature: minimum-severity-filter, Property 9: Disabled category never evaluates the gate
    @given(
        category=st.sampled_from(ALL_CATEGORIES),
        minimum=st.sampled_from(MIN_SEVERITY_ORDER),
        severity=st.sampled_from(SEVERITY_ORDER),
        prior_is_alerting=st.booleans(),
        has_prior_alert=st.booleans(),
        data=st.data(),
    )
    @settings(max_examples=25)
    def test_disabled_category_never_evaluates_gate(
        self,
        category: str,
        minimum: str,
        severity: str,
        prior_is_alerting: bool,
        has_prior_alert: bool,
        data: st.DataObject,
    ) -> None:
        """A push to a disabled category must never reach the severity gate at
        all — the category's entire state (including last_webhook_at, which
        the gate itself would otherwise update on a below-threshold push)
        must remain unchanged, regardless of the configured minimum or the
        alert's severity."""
        prior_alert_count = data.draw(st.integers(min_value=0, max_value=1000))
        prior_open_count = data.draw(st.integers(min_value=0, max_value=1000))
        prior_last_webhook_offset = data.draw(
            st.one_of(st.none(), st.integers(min_value=-100_000, max_value=100_000))
        )
        base_time = datetime(2024, 1, 1, tzinfo=UTC)
        prior_last_webhook_at = (
            base_time + timedelta(seconds=prior_last_webhook_offset)
            if prior_last_webhook_offset is not None
            else None
        )

        coord = make_coordinator(enabled=[])  # category starts disabled
        coord.async_set_updated_data = MagicMock()
        coord._config[CONF_MIN_SEVERITY] = {category: minimum}

        state = coord.get_category_state(category)
        assert state.enabled is False
        prior_last_alert = make_alert(category, "prior alert") if has_prior_alert else None
        state.is_alerting = prior_is_alerting
        state.alert_count = prior_alert_count
        state.open_count = prior_open_count
        state.last_alert = prior_last_alert
        state.last_webhook_at = prior_last_webhook_at

        alert = make_alert(category, "arbitrary-severity alert")
        alert.severity = severity

        coord.push_alert(category, alert)

        assert state.enabled is False
        assert state.is_alerting == prior_is_alerting
        assert state.alert_count == prior_alert_count
        assert state.open_count == prior_open_count
        assert state.last_alert is prior_last_alert
        assert state.last_webhook_at == prior_last_webhook_at
        # No notification either — a disabled-category push is a full no-op.
        coord.async_set_updated_data.assert_not_called()
