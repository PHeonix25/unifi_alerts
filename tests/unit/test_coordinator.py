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
    async def test_invalid_auth_on_retry_raises_update_failed(self):
        """If re-auth also fails, UpdateFailed must be raised."""
        from homeassistant.helpers.update_coordinator import UpdateFailed

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
        with pytest.raises(UpdateFailed):
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
