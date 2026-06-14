"""Tests for the UniFiAlertsCoordinator."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    CONF_CLEAR_TIMEOUT,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
)
from custom_components.unifi_alerts.coordinator import (
    _PERSIST_DELAY_SECONDS,
    UniFiAlertsCoordinator,
)
from custom_components.unifi_alerts.models import UniFiAlert


def make_coordinator(hass=None, enabled=None):
    if hass is None:
        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()  # discard the coroutine cleanly — no "never awaited" warning
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task

    client = MagicMock()
    client.categorise_alarms = AsyncMock(return_value={})

    config = {
        CONF_ENABLED_CATEGORIES: enabled or ALL_CATEGORIES,
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 30,
    }
    coord = UniFiAlertsCoordinator(hass, client, config)
    # Persistence is exercised in dedicated tests; default to a mock Store so
    # push_alert's debounced async_delay_save is a harmless no-op here (the
    # real Store needs a live event loop the MagicMock hass does not provide).
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    coord._store.async_delay_save = MagicMock()
    return coord


def make_alert(category: str, message: str = "test alert", key: str = "") -> UniFiAlert:
    payload = {"message": message}
    if key:
        payload["key"] = key
    return UniFiAlert.from_webhook_payload(category, payload)


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


class TestShutdown:
    def _make_coordinator_with_real_tasks(self):
        """Return a coordinator whose _clear_tasks holds cancellable MagicMocks."""
        hass = MagicMock()
        task_mock = MagicMock()
        task_mock.done.return_value = False

        def _create_task(coro, **kwargs):
            coro.close()
            return task_mock

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        coord = make_coordinator(hass=hass)
        coord.async_set_updated_data = MagicMock()
        return coord, task_mock

    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_tasks(self):
        coord, task_mock = self._make_coordinator_with_real_tasks()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        await coord.async_shutdown()
        task_mock.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_clears_tasks_dict(self):
        coord, _ = self._make_coordinator_with_real_tasks()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert len(coord._clear_tasks) == 1
        await coord.async_shutdown()
        assert len(coord._clear_tasks) == 0


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

    def test_empty_key_still_dedups(self):
        """Alerts with no `key` field still dedup on the empty-string token —
        prevents a misconfigured controller (which omits `key`) from flooding."""
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        a1 = make_alert(CATEGORY_NETWORK_WAN, "first")  # key=""
        a2 = make_alert(CATEGORY_NETWORK_WAN, "second")  # key=""
        coord.push_alert(CATEGORY_NETWORK_WAN, a1)
        coord.push_alert(CATEGORY_NETWORK_WAN, a2)
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 1

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


class TestCancelClear:
    def _make_coordinator_with_task(self):
        hass = MagicMock()
        task_mock = MagicMock()
        task_mock.done.return_value = False

        def _create_task(coro, **kwargs):
            coro.close()
            return task_mock

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        coord = make_coordinator(hass=hass)
        coord.async_set_updated_data = MagicMock()
        return coord, task_mock

    def test_cancel_clear_cancels_pending_task(self):
        coord, task_mock = self._make_coordinator_with_task()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        coord.cancel_clear(CATEGORY_NETWORK_WAN)
        task_mock.cancel.assert_called_once()

    def test_cancel_clear_removes_task_from_dict(self):
        coord, _ = self._make_coordinator_with_task()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert CATEGORY_NETWORK_WAN in coord._clear_tasks
        coord.cancel_clear(CATEGORY_NETWORK_WAN)
        assert CATEGORY_NETWORK_WAN not in coord._clear_tasks

    def test_cancel_clear_noop_when_no_task(self):
        coord = make_coordinator()
        # Should not raise even if no task exists
        coord.cancel_clear(CATEGORY_NETWORK_WAN)


class TestPollingPath:
    @pytest.mark.asyncio
    async def test_polling_does_not_increment_alert_count(self):
        """Polling open alarms must not increment alert_count — only webhooks should."""
        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        from custom_components.unifi_alerts.models import UniFiAlert

        polled_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="persistent open alarm",
            received_at=datetime(2024, 1, 1, 10, 0),
        )
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [polled_alert]})

        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

        # Simulate first poll — finds an open alarm
        await coord._async_update_data()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.is_alerting is True
        assert state.alert_count == 0  # polling must NOT increment alert_count

    @pytest.mark.asyncio
    async def test_polling_does_not_fire_again_when_already_alerting(self):
        """If category is already alerting, polling must leave it unchanged."""
        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        from custom_components.unifi_alerts.models import UniFiAlert

        polled_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="open alarm",
            received_at=datetime(2024, 1, 1, 10, 0),
        )
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [polled_alert]})

        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

        # Mark as already alerting via webhook push (increments count to 1)
        webhook_alert = make_alert(CATEGORY_NETWORK_WAN, "webhook alert")
        coord.push_alert(CATEGORY_NETWORK_WAN, webhook_alert)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.alert_count == 1

        # Poll again — should not increment count further
        await coord._async_update_data()
        assert state.alert_count == 1


class TestPollingErrorPaths:
    """Tests for _async_update_data error handling."""

    @pytest.mark.asyncio
    async def test_invalid_auth_triggers_re_auth_and_retries(self):
        """On InvalidAuthError the coordinator re-authenticates once and retries."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()

        # First call raises InvalidAuthError; after re-auth the second call succeeds
        client.categorise_alarms = AsyncMock(side_effect=[InvalidAuthError("expired"), {}])
        client.authenticate = AsyncMock()

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        # Should not raise
        await coord._async_update_data()
        client.authenticate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reauth_raises_invalid_auth_raises_config_entry_auth_failed(self):
        """If re-auth itself raises InvalidAuthError, ConfigEntryAuthFailed must be raised."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        client.categorise_alarms = AsyncMock(side_effect=InvalidAuthError("expired"))
        client.authenticate = AsyncMock(side_effect=InvalidAuthError("still bad"))

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_reauth_raises_cannot_connect_raises_config_entry_auth_failed(self):
        """If re-auth raises CannotConnectError, ConfigEntryAuthFailed must be raised."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.unifi_alerts.unifi_client import CannotConnectError, InvalidAuthError

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        client.categorise_alarms = AsyncMock(side_effect=InvalidAuthError("expired"))
        client.authenticate = AsyncMock(side_effect=CannotConnectError("unreachable during reauth"))

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_reauth_succeeds_but_retry_fails_raises_update_failed_with_distinctive_message(
        self,
    ):
        """Re-auth succeeds but retried categorise_alarms fails → UpdateFailed with 'after re-authentication'."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.unifi_alerts.unifi_client import CannotConnectError, InvalidAuthError

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        # First categorise_alarms call fails with auth error; re-auth succeeds; second call fails
        client.categorise_alarms = AsyncMock(
            side_effect=[InvalidAuthError("expired"), CannotConnectError("controller 500")]
        )
        client.authenticate = AsyncMock()  # re-auth succeeds

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        with pytest.raises(UpdateFailed) as exc_info:
            await coord._async_update_data()

        assert "after re-authentication" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reauth_succeeds_but_retry_still_401_raises_config_entry_auth_failed(self):
        """Re-auth succeeds but retried fetch still raises InvalidAuthError → ConfigEntryAuthFailed."""
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        # First call: auth expired; re-auth succeeds; retry: still unauthorized
        client.categorise_alarms = AsyncMock(
            side_effect=[InvalidAuthError("expired"), InvalidAuthError("still 401")]
        )
        client.authenticate = AsyncMock()  # re-auth itself succeeds

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_cannot_connect_raises_update_failed(self):
        """CannotConnectError must be wrapped in UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        client.categorise_alarms = AsyncMock(side_effect=CannotConnectError("timeout"))

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()

    @pytest.mark.asyncio
    async def test_polling_zeroes_open_count_for_cleared_categories(self):
        """Categories that have no polled alarms get open_count reset to 0."""
        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        client = MagicMock()
        # First poll: WAN has 1 alarm; second poll: WAN has 0 alarms
        polled_alert = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="open",
            received_at=datetime(2024, 1, 1, 10, 0),
        )
        client.categorise_alarms = AsyncMock(
            side_effect=[
                {CATEGORY_NETWORK_WAN: [polled_alert]},
                {},  # second poll: nothing open
            ]
        )

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

        await coord._async_update_data()
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 1

        await coord._async_update_data()
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 0


class TestRollupOpenCount:
    def test_rollup_open_count_sums_enabled_categories(self):
        coord = make_coordinator()
        coord.get_category_state(CATEGORY_NETWORK_WAN).open_count = 3
        coord.get_category_state(CATEGORY_SECURITY_THREAT).open_count = 2
        assert coord.rollup_open_count == 5

    def test_rollup_open_count_excludes_disabled_categories(self):
        coord = make_coordinator(enabled=[CATEGORY_NETWORK_WAN])
        coord.get_category_state(CATEGORY_NETWORK_WAN).open_count = 3
        coord.get_category_state(CATEGORY_SECURITY_THREAT).open_count = 99
        assert coord.rollup_open_count == 3

    def test_rollup_open_count_zero_when_no_alarms(self):
        coord = make_coordinator()
        assert coord.rollup_open_count == 0


class TestAutoClear:
    """Tests for the _auto_clear coroutine."""

    @pytest.mark.asyncio
    async def test_auto_clear_clears_state_after_delay(self):
        """_auto_clear must call state.clear() and notify listeners after sleeping."""
        import asyncio

        hass = MagicMock()

        real_tasks = []

        def _create_task(coro, **kwargs):
            task = asyncio.ensure_future(coro)
            real_tasks.append(task)
            return task

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        coord = make_coordinator(hass=hass)
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()
        coord.async_set_updated_data = MagicMock()

        alert = make_alert(CATEGORY_NETWORK_WAN)
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.apply_alert(alert)

        # Call _auto_clear directly with a very short delay
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coord._auto_clear(CATEGORY_NETWORK_WAN, 0)

        assert state.is_alerting is False
        coord.async_set_updated_data.assert_called()

    @pytest.mark.asyncio
    async def test_auto_clear_noop_when_not_alerting(self):
        """_auto_clear must not notify if the category is not alerting."""

        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: MagicMock()
        coord = make_coordinator(hass=hass)
        coord.async_set_updated_data = MagicMock()

        # Do NOT set alerting — state starts as not alerting
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coord._auto_clear(CATEGORY_NETWORK_WAN, 0)

        coord.async_set_updated_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_clear_persists_watermark(self):
        """Auto-clear must persist the advanced watermark to storage.

        Regression: previously _auto_clear() called state.clear() (which
        advances last_cleared_at in memory) but never awaited
        _async_persist_watermarks(). An HA restart immediately after a
        timer-triggered clear would lose the watermark and open_count
        would jump back to the lifetime total on the next poll.
        """
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(return_value=None)
        coord._store.async_save = AsyncMock()
        coord.async_set_updated_data = MagicMock()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.apply_alert(make_alert(CATEGORY_NETWORK_WAN))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coord._auto_clear(CATEGORY_NETWORK_WAN, 0)

        coord._store.async_save.assert_awaited_once()
        # The persisted payload should include the freshly advanced watermark
        # for this category.
        saved = coord._store.async_save.await_args.args[0]
        assert CATEGORY_NETWORK_WAN in saved


class TestWatermarks:
    """Tests for the acknowledgement watermark feature (Option C)."""

    def _make_coord_with_mock_store(self):
        """Coordinator with a Store mock so async_load/async_save are controllable."""
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(return_value=None)
        coord._store.async_save = AsyncMock()
        return coord

    @pytest.mark.asyncio
    async def test_restore_watermarks_sets_last_cleared_at(self):
        coord = self._make_coord_with_mock_store()
        ts = "2024-06-01T10:00:00+00:00"
        coord._store.async_load.return_value = {CATEGORY_NETWORK_WAN: ts}

        await coord.async_restore_watermarks()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at is not None
        assert state.last_cleared_at.isoformat() == ts

    @pytest.mark.asyncio
    async def test_restore_watermarks_skips_invalid_timestamps(self):
        coord = self._make_coord_with_mock_store()
        coord._store.async_load.return_value = {CATEGORY_NETWORK_WAN: "not-a-date"}

        await coord.async_restore_watermarks()  # must not raise

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at is None

    @pytest.mark.asyncio
    async def test_restore_watermarks_handles_empty_store(self):
        coord = self._make_coord_with_mock_store()
        coord._store.async_load.return_value = None

        await coord.async_restore_watermarks()  # must not raise

        for cat in ALL_CATEGORIES:
            assert coord.get_category_state(cat).last_cleared_at is None

    @pytest.mark.asyncio
    async def test_async_clear_category_sets_watermark_and_notifies(self):
        coord = self._make_coord_with_mock_store()
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.is_alerting = True

        await coord.async_clear_category(CATEGORY_NETWORK_WAN)

        assert state.is_alerting is False
        assert state.last_cleared_at is not None
        coord._store.async_save.assert_awaited_once()
        coord.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_clear_category_cancels_auto_clear_task(self):
        hass = MagicMock()
        task_mock = MagicMock()
        task_mock.done.return_value = False

        def _create_task(coro, **kw):
            coro.close()
            return task_mock

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task
        coord = make_coordinator(hass=hass)
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(return_value=None)
        coord._store.async_save = AsyncMock()
        coord.async_set_updated_data = MagicMock()

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        await coord.async_clear_category(CATEGORY_NETWORK_WAN)

        task_mock.cancel.assert_called()

    @pytest.mark.asyncio
    async def test_async_clear_all_sets_watermark_on_all_enabled(self):
        coord = self._make_coord_with_mock_store()
        coord.async_set_updated_data = MagicMock()

        await coord.async_clear_all()

        for cat in ALL_CATEGORIES:
            state = coord.get_category_state(cat)
            assert state.last_cleared_at is not None
        coord._store.async_save.assert_awaited_once()
        coord.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_count_filtered_by_watermark(self):
        """Alarms older than watermark must not contribute to open_count."""
        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()
        hass.async_create_background_task = hass.async_create_task
        client = MagicMock()

        watermark = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        old_alarm = MagicMock()
        old_alarm.received_at = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)  # before watermark
        new_alarm = MagicMock()
        new_alarm.received_at = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)  # after watermark

        client.categorise_alarms = AsyncMock(
            return_value={CATEGORY_NETWORK_WAN: [old_alarm, new_alarm]}
        )
        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()
        coord.get_category_state(CATEGORY_NETWORK_WAN).last_cleared_at = watermark

        await coord._async_update_data()

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 1

    @pytest.mark.asyncio
    async def test_open_count_unfiltered_when_no_watermark(self):
        """Without a watermark, all unarchived alarms are counted."""
        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()
        hass.async_create_background_task = hass.async_create_task
        client = MagicMock()

        alarms = [MagicMock() for _ in range(5)]
        for i, a in enumerate(alarms):
            a.received_at = datetime(2024, 6, 1, i, 0, 0, tzinfo=UTC)

        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: alarms})
        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()
        # No watermark set — last_cleared_at is None

        await coord._async_update_data()

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 5


class TestSiteConfig:
    """Tests for CONF_SITE threading through the coordinator."""

    @pytest.mark.asyncio
    async def test_coordinator_passes_site_to_categorise_alarms(self):
        """Coordinator must forward the configured site name to categorise_alarms."""
        from custom_components.unifi_alerts.const import CONF_SITE

        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()

        client = MagicMock()
        client.categorise_alarms = AsyncMock(return_value={})

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
            CONF_SITE: "secondary",
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

        await coord._async_update_data()

        client.categorise_alarms.assert_awaited_once_with("secondary")

    @pytest.mark.asyncio
    async def test_coordinator_defaults_site_to_default(self):
        """When CONF_SITE is absent, coordinator must use 'default'."""
        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()

        client = MagicMock()
        client.categorise_alarms = AsyncMock(return_value={})

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
            # CONF_SITE intentionally absent
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

        await coord._async_update_data()

        client.categorise_alarms.assert_awaited_once_with("default")


class TestPollingWatermarkSuppressesIsAlerting:
    """Polling must apply the watermark filter when re-asserting is_alerting.

    Field-confirmed regression: after async_clear_category (or auto-clear)
    advanced last_cleared_at, the next poll re-discovered a pre-watermark
    alarm and re-asserted is_alerting=True with a stale message. The UI
    showed status=Problem + Open Count=0 simultaneously because open_count
    used the watermark filter but the is_alerting branch did not.
    """

    @pytest.mark.asyncio
    async def test_polling_does_not_reassert_for_pre_watermark_alarm(self):
        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()
        hass.async_create_background_task = hass.async_create_task

        watermark = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        stale_alarm = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="stale pre-watermark alarm",
            received_at=datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC),
        )

        client = MagicMock()
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [stale_alarm]})

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.last_cleared_at = watermark

        await coord._async_update_data()

        assert state.is_alerting is False
        assert state.last_alert is None
        assert state.open_count == 0

    @pytest.mark.asyncio
    async def test_polling_picks_post_watermark_alarm_for_most_recent(self):
        """Mixed pre+post-watermark batch must use the post-watermark alarm."""
        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()
        hass.async_create_background_task = hass.async_create_task

        watermark = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        stale = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="stale",
            received_at=datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC),
        )
        fresh = UniFiAlert(
            category=CATEGORY_NETWORK_WAN,
            message="fresh",
            received_at=datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC),
        )

        client = MagicMock()
        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: [stale, fresh]})

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.last_cleared_at = watermark

        await coord._async_update_data()

        assert state.is_alerting is True
        assert state.last_alert is fresh
        assert state.open_count == 1


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
        import asyncio

        gate = asyncio.Event()  # held open until the test releases it

        async def blocking_categorise_alarms(site):  # noqa: ARG001
            # Block the poll mid-await until the test fires the webhook
            await gate.wait()
            # Return empty list — the regression scenario: poll sees no alarms
            return {}

        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()  # discard auto-clear coroutines — not under test
            return MagicMock()

        hass.async_create_task = _create_task
        hass.async_create_background_task = _create_task

        client = MagicMock()
        client.categorise_alarms = blocking_categorise_alarms

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

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


class TestPushAlertOptimisticOpenCount:
    """push_alert must increment open_count optimistically.

    Field-confirmed: webhook fires update is_alerting and alert_count, but
    open_count only refreshed on the next REST poll (default 60 s). For up
    to one poll interval the binary sensor showed Problem while Open Count
    showed 0. push_alert now bumps open_count immediately and polling
    reconciles to the authoritative value on the next refresh.
    """

    def test_push_increments_open_count_when_no_watermark(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.open_count == 0

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))

        assert state.open_count == 1

    def test_push_increments_open_count_when_alert_after_watermark(self):
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        # Watermark set in the past — webhook arriving "now" is after it
        state.last_cleared_at = datetime(2020, 1, 1, tzinfo=UTC)

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))

        assert state.open_count == 1

    def test_push_does_not_increment_open_count_for_pre_watermark_alert(self):
        """A push for an alert older than the watermark must not bump open_count."""
        coord = make_coordinator()
        coord.async_set_updated_data = MagicMock()
        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        state.last_cleared_at = datetime(2030, 1, 1, tzinfo=UTC)  # future

        # Webhook payloads use datetime.now(UTC), which is before 2030
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))

        # apply_alert still ran (alert_count bumped), but open_count was
        # suppressed because the alert is older than the watermark.
        assert state.alert_count == 1
        assert state.open_count == 0

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
        hass = MagicMock()
        hass.async_create_task = lambda coro, **kw: coro.close() or MagicMock()
        hass.async_create_background_task = hass.async_create_task

        client = MagicMock()
        # Polling returns nothing for the WAN category — alarm has cleared
        # on the controller side already.
        client.categorise_alarms = AsyncMock(return_value={})

        config = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 30,
        }
        coord = UniFiAlertsCoordinator(hass, client, config)
        coord.async_set_updated_data = MagicMock()

        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 1

        await coord._async_update_data()

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == 0


class TestCounterPersistence:
    """Tests for alert_count and last_alert persistence across reloads."""

    def _make_coord_with_mock_store(self):
        """Coordinator with a Store mock so async_load/async_save are controllable."""
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(return_value=None)
        coord._store.async_save = AsyncMock()
        return coord

    @pytest.mark.asyncio
    async def test_alert_count_persists_across_reload(self):
        """alert_count written by push_alert is restored by a freshly created coordinator."""
        coord = self._make_coord_with_mock_store()
        coord.async_set_updated_data = MagicMock()

        # Push 3 distinct alerts so alert_count reaches 3.
        for i in range(3):
            coord.push_alert(
                CATEGORY_NETWORK_WAN,
                make_alert(CATEGORY_NETWORK_WAN, f"alert {i}", key=f"EVT_TEST_{i}"),
            )
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 3

        # Capture what was saved by the last _schedule_persist call.
        # _schedule_persist is fire-and-forget via hass background tasks which
        # are mocked to no-ops in make_coordinator; call the save directly.
        await coord._async_persist_watermarks()
        saved = coord._store.async_save.await_args.args[0]

        # Simulate a reload: new coordinator, same store data.
        coord2 = self._make_coord_with_mock_store()
        coord2._store.async_load.return_value = saved
        await coord2.async_restore_watermarks()

        assert coord2.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 3

    @pytest.mark.asyncio
    async def test_last_alert_persists_across_reload(self):
        """last_alert round-trips through the Store correctly."""
        coord = self._make_coord_with_mock_store()
        coord.async_set_updated_data = MagicMock()

        alert = make_alert(CATEGORY_NETWORK_WAN, "persistent alert", key="EVT_PERSIST")
        coord.push_alert(CATEGORY_NETWORK_WAN, alert)

        await coord._async_persist_watermarks()
        saved = coord._store.async_save.await_args.args[0]

        coord2 = self._make_coord_with_mock_store()
        coord2._store.async_load.return_value = saved
        await coord2.async_restore_watermarks()

        restored = coord2.get_category_state(CATEGORY_NETWORK_WAN).last_alert
        assert restored is not None
        assert restored.message == "persistent alert"
        assert restored.category == CATEGORY_NETWORK_WAN
        assert restored.received_at == alert.received_at

    @pytest.mark.asyncio
    async def test_last_webhook_at_persists_across_reload(self):
        """last_webhook_at round-trips through the Store so health survives a reload."""
        coord = self._make_coord_with_mock_store()
        coord.async_set_updated_data = MagicMock()

        alert = make_alert(CATEGORY_NETWORK_WAN, "health probe", key="EVT_HEALTH")
        coord.push_alert(CATEGORY_NETWORK_WAN, alert)

        await coord._async_persist_watermarks()
        saved = coord._store.async_save.await_args.args[0]
        assert saved[CATEGORY_NETWORK_WAN]["last_webhook_at"] == alert.received_at.isoformat()

        coord2 = self._make_coord_with_mock_store()
        coord2._store.async_load.return_value = saved
        await coord2.async_restore_watermarks()

        assert coord2.get_category_state(CATEGORY_NETWORK_WAN).last_webhook_at == alert.received_at

    @pytest.mark.asyncio
    async def test_restore_skips_invalid_last_webhook_at(self):
        """A corrupt last_webhook_at must be ignored, not raise."""
        coord = self._make_coord_with_mock_store()
        coord._store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {"last_webhook_at": "not-a-timestamp", "alert_count": 1}
        }

        await coord.async_restore_watermarks()  # must not raise

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).last_webhook_at is None

    @pytest.mark.asyncio
    async def test_restore_handles_legacy_payload_without_counters(self):
        """A store payload with only last_cleared_at (pre-v1.6.0) restores cleanly.

        alert_count must default to 0 and last_alert to None.
        """
        coord = self._make_coord_with_mock_store()
        # Old-format payload: bare ISO string per category.
        legacy_payload = {CATEGORY_NETWORK_WAN: "2024-06-01T10:00:00+00:00"}
        coord._store.async_load.return_value = legacy_payload

        await coord.async_restore_watermarks()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at is not None
        assert state.alert_count == 0
        assert state.last_alert is None

    @pytest.mark.asyncio
    async def test_apply_alert_triggers_save(self):
        """push_alert must schedule a persist (via _schedule_persist) after apply_alert.

        We verify by patching _schedule_persist and asserting it is called.
        """
        from unittest.mock import patch as _patch

        coord = self._make_coord_with_mock_store()
        coord.async_set_updated_data = MagicMock()

        with _patch.object(coord, "_schedule_persist") as mock_persist:
            coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))

        mock_persist.assert_called_once()


def _make_hass_and_client():
    """Return a hass mock + client mock for coordinator tests."""
    hass = MagicMock()

    def _create_task(coro, **kwargs):
        coro.close()
        return MagicMock()

    hass.async_create_task = _create_task
    hass.async_create_background_task = _create_task

    client = MagicMock()
    client.probe_system_log_endpoint = AsyncMock(return_value=False)
    client.fetch_system_log_alarms = AsyncMock(return_value=[])
    client.categorise_alarms = AsyncMock(return_value={})
    return hass, client


def _make_full_coordinator(hass, client):
    config = {
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 30,
    }
    coord = UniFiAlertsCoordinator(hass, client, config)
    coord.async_set_updated_data = MagicMock()
    return coord


class TestCoordinatorV2Dispatch:
    """Tests for the v2 system-log dispatch path in _async_update_data."""

    @pytest.mark.asyncio
    async def test_coordinator_uses_system_log_when_available(self):
        """When probe returns True, coordinator must call fetch_system_log_alarms."""
        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = _make_full_coordinator(hass, client)

        await coord._async_update_data()

        client.fetch_system_log_alarms.assert_awaited_once()
        client.categorise_alarms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_coordinator_falls_back_to_legacy_on_probe_false(self):
        """When probe returns False, coordinator must use categorise_alarms."""
        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=False)
        coord = _make_full_coordinator(hass, client)

        await coord._async_update_data()

        client.categorise_alarms.assert_awaited_once()
        client.fetch_system_log_alarms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_coordinator_falls_back_to_legacy_on_probe_exception(self):
        """If probe raises an exception, coordinator must fall back to legacy path."""
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(
            side_effect=CannotConnectError("network error")
        )
        coord = _make_full_coordinator(hass, client)

        await coord._async_update_data()

        client.categorise_alarms.assert_awaited_once()
        client.fetch_system_log_alarms.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_coordinator_falls_back_to_legacy_on_404(self):
        """probe=False (from a 404) triggers legacy fallback."""
        hass, client = _make_hass_and_client()
        # Simulates the probe returning False due to 404 (already handled in UniFiClient)
        client.probe_system_log_endpoint = AsyncMock(return_value=False)
        coord = _make_full_coordinator(hass, client)

        await coord._async_update_data()

        client.categorise_alarms.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v2_events_parsed_and_categorised(self):
        """v2 events returned from fetch_system_log_alarms must be parsed and grouped by category."""
        from custom_components.unifi_alerts.const import CATEGORY_SECURITY_THREAT

        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            return_value=[
                {
                    "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
                    "category": "SECURITY",
                    "status": "NEW",
                    "timestamp": 1778025612345,
                    "message_raw": "Threat from {SRC_IP}.",
                    "parameters": {"SRC_IP": {"name": "1.2.3.4"}},
                    "severity": "HIGH",
                },
                {
                    "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
                    "category": "SECURITY",
                    "status": "NEW",
                    "timestamp": 1778025612000,
                    "message_raw": "Threat from {SRC_IP}.",
                    "parameters": {"SRC_IP": {"name": "5.6.7.8"}},
                    "severity": "HIGH",
                },
            ]
        )
        coord = _make_full_coordinator(hass, client)

        await coord._async_update_data()

        state = coord.get_category_state(CATEGORY_SECURITY_THREAT)
        assert state.open_count == 2

    @pytest.mark.asyncio
    async def test_v2_unknown_key_with_unknown_category_is_skipped(self):
        """Events with no matching key or category enum must be silently skipped."""
        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(
            return_value=[
                {
                    "key": "TOTALLY_UNKNOWN_KEY",
                    "category": "AUDIT",  # not in SYSTEM_LOG_CATEGORY_FALLBACK
                    "status": "NEW",
                    "timestamp": 1778025612345,
                    "message_raw": "Some audit event.",
                    "parameters": {},
                    "severity": "LOW",
                }
            ]
        )
        coord = _make_full_coordinator(hass, client)

        await coord._async_update_data()

        # No category should have an open_count > 0
        for state in coord.category_states.values():
            assert state.open_count == 0

    @pytest.mark.asyncio
    async def test_v2_watermark_passed_as_since_to_fetch(self):
        """The oldest watermark across enabled categories must be passed as since=."""
        from datetime import UTC, datetime

        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = _make_full_coordinator(hass, client)

        # Set distinct watermarks; the oldest should be passed as since
        older_wm = datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)
        newer_wm = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        coord.get_category_state(CATEGORY_NETWORK_WAN).last_cleared_at = older_wm
        coord.get_category_state(CATEGORY_SECURITY_THREAT).last_cleared_at = newer_wm

        await coord._async_update_data()

        client.fetch_system_log_alarms.assert_awaited_once()
        _, kwargs = client.fetch_system_log_alarms.call_args
        assert kwargs.get("since") == older_wm

    @pytest.mark.asyncio
    async def test_v2_no_watermark_passes_none_as_since(self):
        """When no category has been cleared, since=None must be passed (client picks lookback)."""
        hass, client = _make_hass_and_client()
        client.probe_system_log_endpoint = AsyncMock(return_value=True)
        client.fetch_system_log_alarms = AsyncMock(return_value=[])
        coord = _make_full_coordinator(hass, client)

        # No watermarks set; all last_cleared_at are None
        await coord._async_update_data()

        client.fetch_system_log_alarms.assert_awaited_once()
        _, kwargs = client.fetch_system_log_alarms.call_args
        assert kwargs.get("since") is None


class TestCoordinatorUncoveredBranches:
    @pytest.mark.asyncio
    async def test_restore_watermarks_ignores_unknown_category(self):
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(
            return_value={"unknown_category": "2024-01-01T00:00:00+00:00"}
        )
        coord._store.async_save = AsyncMock()

        await coord.async_restore_watermarks()

        for cat in ALL_CATEGORIES:
            assert coord.get_category_state(cat) is not None

    @pytest.mark.asyncio
    async def test_restore_watermarks_invalid_dict_timestamp_is_ignored(self):
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(
            return_value={
                CATEGORY_NETWORK_WAN: {"last_cleared_at": "bad-timestamp", "alert_count": 2}
            }
        )
        coord._store.async_save = AsyncMock()

        await coord.async_restore_watermarks()

        state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        assert state.last_cleared_at is None
        assert state.alert_count == 2

    @pytest.mark.asyncio
    async def test_clear_unknown_category_is_noop(self):
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()

        await coord.async_clear_category("unknown_category")

        coord._store.async_save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clear_all_skips_disabled_categories(self):
        coord = make_coordinator(enabled=[CATEGORY_NETWORK_WAN])
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()
        wan_state = coord.get_category_state(CATEGORY_NETWORK_WAN)
        threat_state = coord.get_category_state(CATEGORY_SECURITY_THREAT)
        wan_state.is_alerting = True
        threat_state.is_alerting = True

        await coord.async_clear_all()

        assert wan_state.is_alerting is False
        assert threat_state.is_alerting is True

    def test_schedule_clear_falls_back_to_async_create_task(self):
        hass = MagicMock()
        hass.async_create_background_task = None
        created = MagicMock()

        def _create_task(coro):
            coro.close()
            return created

        hass.async_create_task = _create_task
        coord = make_coordinator(hass=hass)
        coord._schedule_clear(CATEGORY_NETWORK_WAN)
        assert coord._clear_tasks[CATEGORY_NETWORK_WAN] is created

    def test_schedule_persist_delegates_to_delay_save(self):
        """push persist must coalesce via Store.async_delay_save, not per-push tasks."""
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_delay_save = MagicMock()

        coord._schedule_persist()

        coord._store.async_delay_save.assert_called_once()
        data_func, delay = coord._store.async_delay_save.call_args.args
        assert callable(data_func)
        assert delay == _PERSIST_DELAY_SECONDS
        # The data function returns a live snapshot of every category, so the
        # single coalesced write reflects state captured at write time.
        snapshot = data_func()
        assert set(snapshot) == set(ALL_CATEGORIES)

    def test_schedule_persist_burst_coalesces_to_single_delay_save_per_call(self):
        """A burst of pushes routes every persist through the same debounced sink.

        Store.async_delay_save owns the debounce: repeated calls within the
        delay window collapse to one durable write. We assert we always hand
        off to it (never a fire-and-forget async_save), which is what removes
        the lost-update race.
        """
        coord = make_coordinator()
        coord._store = MagicMock()
        coord._store.async_delay_save = MagicMock()
        coord._store.async_save = AsyncMock()

        for _ in range(5):
            coord._schedule_persist()

        assert coord._store.async_delay_save.call_count == 5
        coord._store.async_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_background_task_exception_is_logged(self, caplog):
        """A background coroutine that raises must be logged, not swallowed."""
        hass = MagicMock()
        hass.async_create_background_task = lambda coro, name=None: asyncio.ensure_future(coro)
        coord = make_coordinator(hass=hass)

        async def _boom() -> None:
            raise RuntimeError("kaboom")

        task = coord._run_background(_boom(), name="unifi_alerts_test")
        with caplog.at_level(logging.ERROR):
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)  # let the done-callback run

        assert "kaboom" in caplog.text

    @pytest.mark.asyncio
    async def test_background_persist_save_failure_is_logged(self, caplog):
        """The save-raises path: a persist exception inside a bg task is logged."""
        hass = MagicMock()
        hass.async_create_background_task = lambda coro, name=None: asyncio.ensure_future(coro)
        coord = make_coordinator(hass=hass)
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock(side_effect=OSError("disk full"))

        task = coord._run_background(coord._async_persist_watermarks(), name="persist")
        with caplog.at_level(logging.ERROR):
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)

        assert "disk full" in caplog.text

    @pytest.mark.asyncio
    async def test_background_task_cancellation_is_not_logged(self, caplog):
        """Cancelling a background task must not log an error."""
        hass = MagicMock()
        hass.async_create_background_task = lambda coro, name=None: asyncio.ensure_future(coro)
        coord = make_coordinator(hass=hass)

        async def _sleep_forever() -> None:
            await asyncio.sleep(3600)

        task = coord._run_background(_sleep_forever(), name="unifi_alerts_test")
        await asyncio.sleep(0)
        task.cancel()
        with caplog.at_level(logging.ERROR):
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)

        assert "failed" not in caplog.text


class TestWatermarkPersistFailureRepair:
    """A failed watermark persist must surface as a self-healing repair issue.

    When Store.async_save raises (disk full, I/O error) the in-memory clear has
    already happened, so the user sees the alert cleared but the watermark never
    reaches disk. On the next restart open_count jumps back. The coordinator
    raises an issue_registry repair so the loss is visible, then deletes it on
    the next successful save so it self-heals.
    """

    def _make_coord(self):
        coord = make_coordinator()
        coord._entry_id = "abc123"
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()
        return coord

    @pytest.mark.asyncio
    async def test_persist_failure_creates_repair_issue(self):
        coord = self._make_coord()
        coord._store.async_save = AsyncMock(side_effect=OSError("disk full"))

        with (
            patch("custom_components.unifi_alerts.coordinator.ir") as mock_ir,
            pytest.raises(OSError),
        ):
            await coord._async_persist_watermarks()

        mock_ir.async_create_issue.assert_called_once()
        # Issue id is the constant base suffixed with the entry id.
        _, kwargs = mock_ir.async_create_issue.call_args
        args = mock_ir.async_create_issue.call_args.args
        assert "watermark_persist_failed_abc123" in args
        # is_fixable=False and severity WARNING per the issue spec.
        assert kwargs["is_fixable"] is False
        assert kwargs["severity"] is mock_ir.IssueSeverity.WARNING
        assert kwargs["translation_key"] == "watermark_persist_failed"
        # No deletion happened on the failure path.
        mock_ir.async_delete_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_persist_deletes_repair_issue(self):
        coord = self._make_coord()

        with patch("custom_components.unifi_alerts.coordinator.ir") as mock_ir:
            await coord._async_persist_watermarks()

        mock_ir.async_delete_issue.assert_called_once()
        args = mock_ir.async_delete_issue.call_args.args
        assert "watermark_persist_failed_abc123" in args
        mock_ir.async_create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_repair_issue_self_heals_on_next_success(self):
        """Fail once (issue created), then succeed (issue deleted) - end to end."""
        coord = self._make_coord()

        with patch("custom_components.unifi_alerts.coordinator.ir") as mock_ir:
            # First save raises - repair issue created.
            coord._store.async_save = AsyncMock(side_effect=OSError("disk full"))
            with pytest.raises(OSError):
                await coord._async_persist_watermarks()
            assert mock_ir.async_create_issue.call_count == 1

            # Next save succeeds - repair issue deleted (self-heal).
            coord._store.async_save = AsyncMock()
            await coord._async_persist_watermarks()
            assert mock_ir.async_delete_issue.call_count == 1
