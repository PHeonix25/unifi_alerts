"""Tests for UniFiAlertsCoordinator: watermark/counter persistence and misc coverage.

Split out of test_coordinator.py (#283) by behaviour area. See
test_coordinator_push_dedup.py, test_coordinator_polling.py, and
test_coordinator_autoclear.py for the other pieces.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import (
    make_alert,
    make_coordinator,
    make_coordinator_with_cancellable_task,
    make_full_coordinator,
    make_hass_and_client,
)

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
)
from custom_components.unifi_alerts.coordinator import _PERSIST_DELAY_SECONDS


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
        coord, task_mock = make_coordinator_with_cancellable_task()
        coord._store = MagicMock()
        coord._store.async_load = AsyncMock(return_value=None)
        coord._store.async_save = AsyncMock()

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
    @pytest.mark.parametrize(
        ("watermark", "alarm_times", "expected_open_count"),
        [
            pytest.param(
                datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                [
                    datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC),  # before watermark
                    datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC),  # after watermark
                ],
                1,
                id="filtered-by-watermark",
            ),
            pytest.param(
                None,
                [datetime(2024, 6, 1, i, 0, 0, tzinfo=UTC) for i in range(5)],
                5,
                id="unfiltered-without-watermark",
            ),
        ],
    )
    async def test_open_count_watermark_filtering(
        self, watermark, alarm_times, expected_open_count
    ):
        """open_count only counts alarms after the watermark; with no watermark, all count."""
        hass, client = make_hass_and_client()

        alarms = []
        for received_at in alarm_times:
            alarm = MagicMock()
            alarm.received_at = received_at
            alarms.append(alarm)

        client.categorise_alarms = AsyncMock(return_value={CATEGORY_NETWORK_WAN: alarms})
        coord = make_full_coordinator(hass, client)
        coord.get_category_state(CATEGORY_NETWORK_WAN).last_cleared_at = watermark

        await coord._async_update_data()

        assert coord.get_category_state(CATEGORY_NETWORK_WAN).open_count == expected_open_count


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
            pytest.raises(OSError, match="disk full"),
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
            with pytest.raises(OSError, match="disk full"):
                await coord._async_persist_watermarks()
            assert mock_ir.async_create_issue.call_count == 1

            # Next save succeeds - repair issue deleted (self-heal).
            coord._store.async_save = AsyncMock()
            await coord._async_persist_watermarks()
            assert mock_ir.async_delete_issue.call_count == 1


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
