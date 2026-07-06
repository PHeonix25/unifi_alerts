"""Tests for UniFiAlertsCoordinator: shutdown, cancel_clear, and auto-clear.

Split out of test_coordinator.py (#283) by behaviour area. See
test_coordinator_push_dedup.py, test_coordinator_polling.py, and
test_coordinator_persistence.py for the other pieces.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_alert, make_coordinator, make_coordinator_with_cancellable_task

from custom_components.unifi_alerts.const import CATEGORY_NETWORK_WAN


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_tasks(self):
        coord, task_mock = make_coordinator_with_cancellable_task()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        await coord.async_shutdown()
        task_mock.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_clears_tasks_dict(self):
        coord, _ = make_coordinator_with_cancellable_task()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert len(coord._clear_tasks) == 1
        await coord.async_shutdown()
        assert len(coord._clear_tasks) == 0


class TestCancelClear:
    def test_cancel_clear_cancels_pending_task(self):
        coord, task_mock = make_coordinator_with_cancellable_task()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        coord.cancel_clear(CATEGORY_NETWORK_WAN)
        task_mock.cancel.assert_called_once()

    def test_cancel_clear_removes_task_from_dict(self):
        coord, _ = make_coordinator_with_cancellable_task()
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN))
        assert CATEGORY_NETWORK_WAN in coord._clear_tasks
        coord.cancel_clear(CATEGORY_NETWORK_WAN)
        assert CATEGORY_NETWORK_WAN not in coord._clear_tasks

    def test_cancel_clear_noop_when_no_task(self):
        coord = make_coordinator()
        # Should not raise even if no task exists
        coord.cancel_clear(CATEGORY_NETWORK_WAN)


class TestAutoClear:
    """Tests for the _auto_clear coroutine."""

    @pytest.mark.asyncio
    async def test_auto_clear_clears_state_after_delay(self):
        """_auto_clear must call state.clear() and notify listeners exactly once after sleeping.

        Strengthened from a prior version that only checked `is_alerting is
        False` plus `async_set_updated_data.assert_called()` (not `_once`) and
        never checked `last_cleared_at` — a half-broken clear (e.g. one that
        forgot to stamp `last_cleared_at`, or that notified twice) would have
        passed. `open_count` is deliberately NOT asserted here: it is owned
        exclusively by the polling path (see `CategoryState.open_count`'s
        docstring), and `clear()` never touches it — this test pushes an
        alert via webhook only (no poll involved), so open_count stays at its
        initial 0 throughout regardless of whether auto-clear ran correctly.
        """
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
        assert state.last_cleared_at is None  # precondition: never cleared yet

        # Call _auto_clear directly with a very short delay
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await coord._auto_clear(CATEGORY_NETWORK_WAN, 0)

        assert state.is_alerting is False
        assert state.last_cleared_at is not None
        coord.async_set_updated_data.assert_called_once()

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

    def test_schedule_clear_converts_minutes_to_seconds(self):
        """_schedule_clear must convert clear_timeout_minutes to seconds.

        Regression guard for `delay = self._clear_timeout_minutes * 60`
        (coordinator.py). Every other auto-clear test calls `_auto_clear`
        directly with an explicit delay, or no-ops `asyncio.sleep` entirely,
        so a minutes/seconds swap at that multiplication would pass the rest
        of the suite (auto-clearing alerts 60x too fast, or never within any
        test's patience) while CI stays green.
        """
        coord = make_coordinator()
        coord._clear_timeout_minutes = 5
        dummy_coro = MagicMock()
        with patch.object(coord, "_auto_clear", return_value=dummy_coro) as mock_auto_clear:
            coord._schedule_clear(CATEGORY_NETWORK_WAN)

        mock_auto_clear.assert_called_once_with(CATEGORY_NETWORK_WAN, 300)
