"""Tests for the UniFiAlertsCoordinator."""
from __future__ import annotations

from datetime import datetime
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
from custom_components.unifi_alerts.coordinator import UniFiAlertsCoordinator
from custom_components.unifi_alerts.models import CategoryState, UniFiAlert


def make_coordinator(hass=None, enabled=None):
    if hass is None:
        hass = MagicMock()

        def _create_task(coro, **kwargs):
            coro.close()  # discard the coroutine cleanly — no "never awaited" warning
            return MagicMock()

        hass.async_create_task = _create_task

    client = MagicMock()
    client.categorise_alarms = AsyncMock(return_value={})

    config = {
        CONF_ENABLED_CATEGORIES: enabled or ALL_CATEGORIES,
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 30,
    }
    return UniFiAlertsCoordinator(hass, client, config)


def make_alert(category: str, message: str = "test alert") -> UniFiAlert:
    return UniFiAlert.from_webhook_payload(category, {"message": message})


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
        for i in range(3):
            coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN, f"alert {i}"))
        assert coord.get_category_state(CATEGORY_NETWORK_WAN).alert_count == 3

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

    def test_push_to_unknown_category_logs_warning(self, caplog):
        coord = make_coordinator()
        alert = make_alert("nonexistent_category")
        coord.push_alert("nonexistent_category", alert)
        assert "unknown category" in caplog.text


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


class TestCancelClear:
    def _make_coordinator_with_task(self):
        hass = MagicMock()
        task_mock = MagicMock()
        task_mock.done.return_value = False

        def _create_task(coro, **kwargs):
            coro.close()
            return task_mock

        hass.async_create_task = _create_task
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
