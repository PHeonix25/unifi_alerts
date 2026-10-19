"""Unit tests for WatermarkStore (persistence.py), independent of the coordinator.

The coordinator-level behaviour (clear paths persisting, push scheduling a
write) is covered in tests/unit/coordinator/test_persistence.py; these tests
exercise the storage bookkeeping in isolation (#386).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    DOMAIN,
    ISSUE_ID_PERSIST_FAILED,
    STORAGE_VERSION_WATERMARKS,
)
from custom_components.unifi_alerts.models import CategoryState, UniFiAlert
from custom_components.unifi_alerts.persistence import (
    _PERSIST_DELAY_SECONDS,
    WatermarkStore,
    async_remove_watermarks,
)

_PERSISTENCE = "custom_components.unifi_alerts.persistence"
_TS = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _make_states() -> dict[str, CategoryState]:
    return {cat: CategoryState(category=cat, enabled=True) for cat in ALL_CATEGORIES}


def _make_alert(category: str = CATEGORY_NETWORK_WAN, message: str = "wan down") -> UniFiAlert:
    return UniFiAlert(
        category=category,
        message=message,
        received_at=_TS,
        raw={"secret": "must-not-persist"},
        key="EVT_GW_WANTransition",
        device_name="gw",
        site="default",
        severity="HIGH",
    )


def _make_store(
    states: dict[str, CategoryState] | None = None, entry_id: str = "entry-1"
) -> tuple[WatermarkStore, dict[str, CategoryState], MagicMock]:
    """WatermarkStore with its HA Store swapped for a mock."""
    states = states if states is not None else _make_states()
    store = WatermarkStore(MagicMock(), entry_id, states)
    mock_store = MagicMock()
    mock_store.async_load = AsyncMock(return_value=None)
    mock_store.async_save = AsyncMock()
    mock_store.async_delay_save = MagicMock()
    store._store = mock_store
    return store, states, mock_store


class TestConstruction:
    def test_store_uses_per_entry_key_and_version(self):
        hass = MagicMock()
        with patch(f"{_PERSISTENCE}.Store") as mock_cls:
            WatermarkStore(hass, "entry-xyz", _make_states())

        mock_cls.assert_called_once_with(
            hass, STORAGE_VERSION_WATERMARKS, f"{DOMAIN}_watermarks_entry-xyz"
        )

    @pytest.mark.asyncio
    async def test_async_remove_watermarks_removes_same_store(self):
        hass = MagicMock()
        mock_store = MagicMock()
        mock_store.async_remove = AsyncMock()
        with patch(f"{_PERSISTENCE}.Store", return_value=mock_store) as mock_cls:
            await async_remove_watermarks(hass, "entry-xyz")

        mock_cls.assert_called_once_with(
            hass, STORAGE_VERSION_WATERMARKS, f"{DOMAIN}_watermarks_entry-xyz"
        )
        mock_store.async_remove.assert_awaited_once()


class TestLoad:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("stored", [None, {}])
    async def test_load_empty_leaves_state_untouched(self, stored):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = stored

        await store.load()

        for state in states.values():
            assert state.last_cleared_at is None
            assert state.alert_count == 0
            assert state.last_alert is None
            assert state.last_webhook_at is None

    @pytest.mark.asyncio
    async def test_load_current_format_restores_all_fields(self):
        store, states, mock_store = _make_store()
        alert = _make_alert()
        mock_store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {
                "last_cleared_at": _TS.isoformat(),
                "alert_count": 7,
                "last_alert": alert.to_dict(),
                "last_webhook_at": _TS.isoformat(),
            }
        }

        await store.load()

        state = states[CATEGORY_NETWORK_WAN]
        assert state.last_cleared_at == _TS
        assert state.alert_count == 7
        assert state.last_webhook_at == _TS
        assert state.last_alert is not None
        assert state.last_alert.message == "wan down"
        assert state.last_alert.severity == "HIGH"
        # Other categories are untouched.
        assert states[CATEGORY_SECURITY_THREAT].last_cleared_at is None

    @pytest.mark.asyncio
    async def test_load_legacy_bare_string_restores_watermark_only(self):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {CATEGORY_NETWORK_WAN: _TS.isoformat()}

        await store.load()

        state = states[CATEGORY_NETWORK_WAN]
        assert state.last_cleared_at == _TS
        assert state.alert_count == 0
        assert state.last_alert is None

    @pytest.mark.asyncio
    async def test_load_naive_timestamps_are_restored_as_utc(self):
        """Tz-less stored timestamps restore as UTC-aware so later comparisons
        against aware alarm times cannot raise TypeError (#441)."""
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {
                "last_cleared_at": "2026-06-01T10:00:00",
                "last_webhook_at": "2026-06-01T11:00:00",
            },
            CATEGORY_SECURITY_THREAT: "2026-06-01T12:00:00",
        }

        await store.load()

        wan = states[CATEGORY_NETWORK_WAN]
        assert wan.last_cleared_at == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        assert wan.last_webhook_at == datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
        assert states[CATEGORY_SECURITY_THREAT].last_cleared_at == datetime(
            2026, 6, 1, 12, 0, tzinfo=UTC
        )

    @pytest.mark.asyncio
    async def test_load_legacy_invalid_string_is_ignored_with_warning(self, caplog):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {CATEGORY_NETWORK_WAN: "not-a-date"}

        with caplog.at_level(logging.WARNING, logger=_PERSISTENCE):
            await store.load()  # must not raise

        assert states[CATEGORY_NETWORK_WAN].last_cleared_at is None
        assert "Ignoring invalid stored watermark" in caplog.text

    @pytest.mark.asyncio
    async def test_load_unknown_category_is_skipped(self):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {"retired_category": _TS.isoformat()}

        await store.load()

        assert set(states) == set(ALL_CATEGORIES)
        assert all(s.last_cleared_at is None for s in states.values())

    @pytest.mark.asyncio
    async def test_load_unexpected_entry_type_is_skipped(self):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {CATEGORY_NETWORK_WAN: 12345}

        await store.load()  # must not raise

        assert states[CATEGORY_NETWORK_WAN].last_cleared_at is None
        assert states[CATEGORY_NETWORK_WAN].alert_count == 0

    @pytest.mark.asyncio
    async def test_load_invalid_dict_timestamp_keeps_other_fields(self, caplog):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {"last_cleared_at": "bad", "alert_count": 2}
        }

        with caplog.at_level(logging.WARNING, logger=_PERSISTENCE):
            await store.load()

        state = states[CATEGORY_NETWORK_WAN]
        assert state.last_cleared_at is None
        assert state.alert_count == 2
        assert "Ignoring invalid stored watermark" in caplog.text

    @pytest.mark.asyncio
    async def test_load_invalid_last_webhook_at_is_ignored(self, caplog):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {"alert_count": 1, "last_webhook_at": "bad"}
        }

        with caplog.at_level(logging.WARNING, logger=_PERSISTENCE):
            await store.load()

        assert states[CATEGORY_NETWORK_WAN].last_webhook_at is None
        assert states[CATEGORY_NETWORK_WAN].alert_count == 1
        assert "Ignoring invalid stored last_webhook_at" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc", [KeyError("category"), TypeError("bad"), ValueError("bad")])
    async def test_load_unparseable_last_alert_is_dropped(self, exc, caplog):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {"alert_count": 3, "last_alert": {"message": "corrupt"}}
        }

        with (
            patch(f"{_PERSISTENCE}.UniFiAlert.from_dict", side_effect=exc),
            caplog.at_level(logging.WARNING, logger=_PERSISTENCE),
        ):
            await store.load()  # must not raise

        state = states[CATEGORY_NETWORK_WAN]
        assert state.last_alert is None
        assert state.alert_count == 3
        assert "Ignoring invalid stored last_alert" in caplog.text

    @pytest.mark.asyncio
    async def test_load_null_last_alert_stays_none(self):
        store, states, mock_store = _make_store()
        mock_store.async_load.return_value = {
            CATEGORY_NETWORK_WAN: {"alert_count": 0, "last_alert": None}
        }

        await store.load()

        assert states[CATEGORY_NETWORK_WAN].last_alert is None


class TestBuildData:
    def test_snapshot_covers_every_category(self):
        store, _, _ = _make_store()

        data = store.build_data()

        assert set(data) == set(ALL_CATEGORIES)
        assert data[CATEGORY_NETWORK_WAN] == {"alert_count": 0, "last_alert": None}

    def test_snapshot_omits_unset_timestamps_and_includes_set_ones(self):
        store, states, _ = _make_store()
        state = states[CATEGORY_NETWORK_WAN]
        state.last_cleared_at = _TS
        state.last_webhook_at = _TS
        state.alert_count = 4
        state.last_alert = _make_alert()

        entry = store.build_data()[CATEGORY_NETWORK_WAN]

        assert entry["last_cleared_at"] == _TS.isoformat()
        assert entry["last_webhook_at"] == _TS.isoformat()
        assert entry["alert_count"] == 4
        assert entry["last_alert"] == state.last_alert.to_dict()
        assert "last_cleared_at" not in store.build_data()[CATEGORY_SECURITY_THREAT]

    def test_snapshot_is_json_serialisable_and_excludes_raw_payload(self):
        store, states, _ = _make_store()
        states[CATEGORY_NETWORK_WAN].last_alert = _make_alert()
        states[CATEGORY_NETWORK_WAN].last_cleared_at = _TS

        encoded = json.dumps(store.build_data())

        assert "must-not-persist" not in encoded

    def test_snapshot_reads_live_state(self):
        """build_data must reflect later mutations of the shared mapping."""
        store, states, _ = _make_store()
        before = store.build_data()
        states[CATEGORY_NETWORK_WAN].alert_count = 9

        assert before[CATEGORY_NETWORK_WAN]["alert_count"] == 0
        assert store.build_data()[CATEGORY_NETWORK_WAN]["alert_count"] == 9


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_save_then_load_restores_state(self):
        store, states, mock_store = _make_store()
        wan = states[CATEGORY_NETWORK_WAN]
        wan.last_cleared_at = _TS
        wan.last_webhook_at = _TS
        wan.alert_count = 5
        wan.last_alert = _make_alert()

        with patch(f"{_PERSISTENCE}.ir"):
            await store.save()
        saved = mock_store.async_save.await_args.args[0]

        store2, states2, mock_store2 = _make_store()
        mock_store2.async_load.return_value = json.loads(json.dumps(saved))
        await store2.load()

        restored = states2[CATEGORY_NETWORK_WAN]
        assert restored.last_cleared_at == _TS
        assert restored.last_webhook_at == _TS
        assert restored.alert_count == 5
        assert restored.last_alert is not None
        assert restored.last_alert.message == "wan down"
        assert restored.last_alert.received_at == _TS


class TestSave:
    @pytest.mark.asyncio
    async def test_save_writes_snapshot_immediately(self):
        store, states, mock_store = _make_store()
        states[CATEGORY_NETWORK_WAN].alert_count = 2

        with patch(f"{_PERSISTENCE}.ir"):
            await store.save()

        mock_store.async_save.assert_awaited_once()
        assert mock_store.async_save.await_args.args[0][CATEGORY_NETWORK_WAN]["alert_count"] == 2
        mock_store.async_delay_save.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_failure_raises_repair_issue_and_reraises(self):
        store, _, mock_store = _make_store(entry_id="abc123")
        mock_store.async_save.side_effect = OSError("disk full")

        with (
            patch(f"{_PERSISTENCE}.ir") as mock_ir,
            pytest.raises(OSError, match="disk full"),
        ):
            await store.save()

        mock_ir.async_create_issue.assert_called_once()
        args = mock_ir.async_create_issue.call_args.args
        kwargs = mock_ir.async_create_issue.call_args.kwargs
        assert args[1:] == (DOMAIN, f"{ISSUE_ID_PERSIST_FAILED}_abc123")
        assert kwargs["is_fixable"] is False
        assert kwargs["severity"] is mock_ir.IssueSeverity.WARNING
        assert kwargs["translation_key"] == ISSUE_ID_PERSIST_FAILED
        mock_ir.async_delete_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_success_deletes_repair_issue(self):
        store, _, _ = _make_store(entry_id="abc123")

        with patch(f"{_PERSISTENCE}.ir") as mock_ir:
            await store.save()

        mock_ir.async_delete_issue.assert_called_once()
        assert mock_ir.async_delete_issue.call_args.args[1:] == (
            DOMAIN,
            f"{ISSUE_ID_PERSIST_FAILED}_abc123",
        )
        mock_ir.async_create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_repair_issue_is_scoped_to_entry(self):
        store_a, _, mock_a = _make_store(entry_id="a")
        store_b, _, _ = _make_store(entry_id="b")
        mock_a.async_save.side_effect = OSError("disk full")

        with patch(f"{_PERSISTENCE}.ir") as mock_ir:
            with pytest.raises(OSError, match="disk full"):
                await store_a.save()
            await store_b.save()

        assert mock_ir.async_create_issue.call_args.args[2] == f"{ISSUE_ID_PERSIST_FAILED}_a"
        assert mock_ir.async_delete_issue.call_args.args[2] == f"{ISSUE_ID_PERSIST_FAILED}_b"


class TestScheduleSave:
    def test_schedule_save_uses_debounced_delay_save(self):
        store, states, mock_store = _make_store()

        store.schedule_save()

        mock_store.async_delay_save.assert_called_once()
        data_func, delay = mock_store.async_delay_save.call_args.args
        assert delay == _PERSIST_DELAY_SECONDS
        # The data function is evaluated at write time, so it must capture
        # state mutated after scheduling.
        states[CATEGORY_NETWORK_WAN].alert_count = 6
        assert data_func()[CATEGORY_NETWORK_WAN]["alert_count"] == 6

    def test_schedule_save_never_uses_immediate_save(self):
        store, _, mock_store = _make_store()

        for _ in range(5):
            store.schedule_save()

        assert mock_store.async_delay_save.call_count == 5
        mock_store.async_save.assert_not_called()

    def test_schedule_save_does_not_touch_repair_issues(self):
        store, _, _ = _make_store()

        with patch(f"{_PERSISTENCE}.ir") as mock_ir:
            store.schedule_save()

        mock_ir.async_create_issue.assert_not_called()
        mock_ir.async_delete_issue.assert_not_called()
