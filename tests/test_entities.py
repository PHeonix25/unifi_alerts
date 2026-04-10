"""Tests for all entity platform classes: binary_sensor, sensor, event, button."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from conftest import make_entry

from custom_components.unifi_alerts.const import (
    CATEGORY_ICONS,
    CATEGORY_ICONS_OK,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
)
from custom_components.unifi_alerts.models import CategoryState, UniFiAlert

# ── shared helpers ────────────────────────────────────────────────────────────


def make_alert(category: str = CATEGORY_NETWORK_WAN, message: str = "WAN offline") -> UniFiAlert:
    return UniFiAlert(
        category=category,
        message=message,
        received_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        key="EVT_GW_WANTransition",
        device_name="UDM-Pro",
        severity="critical",
        site="default",
    )


def make_state(
    category: str = CATEGORY_NETWORK_WAN,
    is_alerting: bool = False,
    enabled: bool = True,
    alert_count: int = 0,
    open_count: int = 0,
    last_alert: UniFiAlert | None = None,
) -> CategoryState:
    state = CategoryState(
        category=category,
        enabled=enabled,
        is_alerting=is_alerting,
        alert_count=alert_count,
        open_count=open_count,
        last_alert=last_alert,
    )
    return state


def make_coordinator(states: dict[str, CategoryState] | None = None):
    """Build a minimal mock coordinator with controllable state.

    NOTE: rollup attributes (any_alerting, rollup_alert_count, etc.) are
    computed once at call time and stored as fixed values on the mock.
    They will NOT update if a CategoryState is mutated after the coordinator
    is built.  This is intentional — entity tests only need a snapshot, not
    a live coordinator.  If a future test needs dynamic rollup behaviour,
    use a real UniFiAlertsCoordinator instead.
    """
    coord = MagicMock()
    _states = states or {}

    coord.get_category_state = lambda cat: _states.get(cat)
    coord.category_states = _states
    coord.any_alerting = any(s.is_alerting for s in _states.values() if s.enabled)
    coord.rollup_alert_count = sum(s.alert_count for s in _states.values() if s.enabled)
    coord.rollup_open_count = sum(s.open_count for s in _states.values() if s.enabled)
    coord.async_set_updated_data = MagicMock()

    alerts = [s.last_alert for s in _states.values() if s.enabled and s.last_alert]
    coord.rollup_last_alert = max(alerts, key=lambda a: a.received_at) if alerts else None

    coord.cancel_clear = MagicMock()
    return coord


# ═══════════════════════════════════════════════════════════════════════════════
# binary_sensor
# ═══════════════════════════════════════════════════════════════════════════════


class TestUniFiCategoryBinarySensor:
    from custom_components.unifi_alerts.binary_sensor import UniFiCategoryBinarySensor

    def _make(self, state: CategoryState | None):
        from custom_components.unifi_alerts.binary_sensor import UniFiCategoryBinarySensor

        coord = make_coordinator({CATEGORY_NETWORK_WAN: state} if state else {})
        entry = make_entry()
        entity = UniFiCategoryBinarySensor(coord, entry, CATEGORY_NETWORK_WAN)
        return entity

    def test_is_on_true_when_alerting(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        assert entity.is_on is True

    def test_is_on_false_when_not_alerting(self):
        state = make_state(is_alerting=False)
        entity = self._make(state)
        assert entity.is_on is False

    def test_is_on_false_when_state_missing(self):
        entity = self._make(None)
        assert entity.is_on is False

    def test_available_true_when_enabled(self):
        state = make_state(enabled=True)
        entity = self._make(state)
        assert entity.available is True

    def test_available_false_when_disabled(self):
        state = make_state(enabled=False)
        entity = self._make(state)
        assert entity.available is False

    def test_icon_alert_when_on(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        assert entity.icon == CATEGORY_ICONS[CATEGORY_NETWORK_WAN]

    def test_icon_ok_when_off(self):
        state = make_state(is_alerting=False)
        entity = self._make(state)
        assert entity.icon == CATEGORY_ICONS_OK[CATEGORY_NETWORK_WAN]

    def test_extra_attrs_with_alert(self):
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=2, open_count=1, last_alert=alert)
        entity = self._make(state)
        attrs = entity.extra_state_attributes
        assert attrs["category"] == CATEGORY_NETWORK_WAN
        assert attrs["alert_count"] == 2
        assert attrs["open_count"] == 1
        assert attrs["last_message"] == "WAN offline"
        assert attrs["last_device"] == "UDM-Pro"
        assert attrs["last_key"] == "EVT_GW_WANTransition"
        assert "last_alert_at" in attrs

    def test_extra_attrs_without_alert(self):
        state = make_state()
        entity = self._make(state)
        attrs = entity.extra_state_attributes
        assert "last_message" not in attrs
        assert attrs["alert_count"] == 0

    def test_extra_attrs_empty_when_no_state(self):
        entity = self._make(None)
        assert entity.extra_state_attributes == {}

    def test_extra_attrs_includes_last_cleared_at(self):
        alert = make_alert()
        state = make_state(last_alert=alert)
        state.last_cleared_at = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)
        entity = self._make(state)
        attrs = entity.extra_state_attributes
        assert "last_cleared_at" in attrs

    def test_unique_id_format(self):
        state = make_state()
        entity = self._make(state)
        assert entity.unique_id == f"entry-abc_{CATEGORY_NETWORK_WAN}_binary"


class TestUniFiRollupBinarySensor:
    def _make(self, states: dict[str, CategoryState]):
        from custom_components.unifi_alerts.binary_sensor import UniFiRollupBinarySensor

        coord = make_coordinator(states)
        entry = make_entry()
        return UniFiRollupBinarySensor(coord, entry)

    def test_is_on_when_any_alerting(self):
        states = {CATEGORY_NETWORK_WAN: make_state(is_alerting=True)}
        entity = self._make(states)
        assert entity.is_on is True

    def test_is_on_false_when_nothing_alerting(self):
        states = {CATEGORY_NETWORK_WAN: make_state(is_alerting=False)}
        entity = self._make(states)
        assert entity.is_on is False

    def test_icon_alert_when_on(self):
        states = {CATEGORY_NETWORK_WAN: make_state(is_alerting=True)}
        entity = self._make(states)
        assert entity.icon == "mdi:shield-alert"

    def test_icon_check_when_off(self):
        states = {}
        entity = self._make(states)
        assert entity.icon == "mdi:shield-check"

    def test_extra_attrs_with_last_alert(self):
        alert = make_alert()
        states = {
            CATEGORY_NETWORK_WAN: make_state(
                is_alerting=True, alert_count=1, open_count=2, last_alert=alert
            )
        }
        entity = self._make(states)
        attrs = entity.extra_state_attributes
        assert attrs["total_alert_count"] == 1
        assert attrs["total_open_count"] == 2
        assert attrs["last_message"] == "WAN offline"
        assert attrs["last_category"] == CATEGORY_NETWORK_WAN

    def test_extra_attrs_without_last_alert(self):
        states = {CATEGORY_NETWORK_WAN: make_state()}
        entity = self._make(states)
        attrs = entity.extra_state_attributes
        assert "last_message" not in attrs
        assert attrs["total_alert_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# sensor
# ═══════════════════════════════════════════════════════════════════════════════


class TestUniFiCategoryMessageSensor:
    def _make(self, state: CategoryState | None):
        from custom_components.unifi_alerts.sensor import UniFiCategoryMessageSensor

        coord = make_coordinator({CATEGORY_NETWORK_WAN: state} if state else {})
        entry = make_entry()
        return UniFiCategoryMessageSensor(coord, entry, CATEGORY_NETWORK_WAN)

    def test_native_value_returns_message_when_alert_present(self):
        alert = make_alert(message="WAN went down")
        state = make_state(last_alert=alert)
        entity = self._make(state)
        assert entity.native_value == "WAN went down"

    def test_native_value_none_when_no_alert(self):
        state = make_state()
        entity = self._make(state)
        assert entity.native_value is None

    def test_native_value_none_when_state_missing(self):
        entity = self._make(None)
        assert entity.native_value is None

    def test_available_true_when_enabled(self):
        state = make_state(enabled=True)
        entity = self._make(state)
        assert entity.available is True

    def test_available_false_when_disabled(self):
        state = make_state(enabled=False)
        entity = self._make(state)
        assert entity.available is False

    def test_icon_alert_when_alerting(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        assert entity.icon == CATEGORY_ICONS[CATEGORY_NETWORK_WAN]

    def test_icon_ok_when_not_alerting(self):
        state = make_state(is_alerting=False)
        entity = self._make(state)
        assert entity.icon == CATEGORY_ICONS_OK[CATEGORY_NETWORK_WAN]

    def test_extra_attrs_with_alert(self):
        alert = make_alert()
        state = make_state(last_alert=alert)
        entity = self._make(state)
        attrs = entity.extra_state_attributes
        assert attrs["device_name"] == "UDM-Pro"
        assert attrs["alert_key"] == "EVT_GW_WANTransition"
        assert attrs["severity"] == "critical"
        assert attrs["site"] == "default"
        assert "received_at" in attrs

    def test_extra_attrs_empty_when_no_alert(self):
        state = make_state()
        entity = self._make(state)
        assert entity.extra_state_attributes == {}


class TestUniFiCategoryCountSensor:
    def _make(self, state: CategoryState | None):
        from custom_components.unifi_alerts.sensor import UniFiCategoryCountSensor

        coord = make_coordinator({CATEGORY_NETWORK_WAN: state} if state else {})
        entry = make_entry()
        return UniFiCategoryCountSensor(coord, entry, CATEGORY_NETWORK_WAN)

    def test_native_value_reflects_open_count(self):
        state = make_state(open_count=5)
        entity = self._make(state)
        assert entity.native_value == 5

    def test_native_value_zero_when_state_missing(self):
        entity = self._make(None)
        assert entity.native_value == 0

    def test_available_reflects_enabled_state(self):
        entity_on = self._make(make_state(enabled=True))
        entity_off = self._make(make_state(enabled=False))
        assert entity_on.available is True
        assert entity_off.available is False


class TestUniFiRollupCountSensor:
    def _make(self, states: dict[str, CategoryState]):
        from custom_components.unifi_alerts.sensor import UniFiRollupCountSensor

        coord = make_coordinator(states)
        entry = make_entry()
        return UniFiRollupCountSensor(coord, entry)

    def test_native_value_is_rollup_open_count(self):
        states = {
            CATEGORY_NETWORK_WAN: make_state(open_count=3),
            CATEGORY_SECURITY_THREAT: make_state(open_count=2),
        }
        entity = self._make(states)
        assert entity.native_value == 5

    def test_extra_attrs_with_last_alert(self):
        alert = make_alert()
        states = {
            CATEGORY_NETWORK_WAN: make_state(alert_count=1, open_count=1, last_alert=alert),
        }
        entity = self._make(states)
        attrs = entity.extra_state_attributes
        assert attrs["total_webhook_count"] == 1
        assert attrs["last_message"] == "WAN offline"
        assert attrs["last_category"] == CATEGORY_NETWORK_WAN
        assert "last_alert_at" in attrs

    def test_extra_attrs_without_last_alert(self):
        states = {CATEGORY_NETWORK_WAN: make_state()}
        entity = self._make(states)
        attrs = entity.extra_state_attributes
        assert "last_message" not in attrs
        assert attrs["total_webhook_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# event
# ═══════════════════════════════════════════════════════════════════════════════


class TestUniFiAlertEventEntity:
    def _make(self, state: CategoryState | None):
        from custom_components.unifi_alerts.event import UniFiAlertEventEntity

        coord = make_coordinator({CATEGORY_NETWORK_WAN: state} if state else {})
        entry = make_entry()
        entity = UniFiAlertEventEntity(coord, entry, CATEGORY_NETWORK_WAN)
        entity._trigger_event = MagicMock()  # stub HA event firing
        # Provide a mock hass so that super()._handle_coordinator_update()
        # can call async_write_ha_state() without raising RuntimeError.
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_available_true_when_enabled(self):
        state = make_state(enabled=True)
        entity = self._make(state)
        assert entity.available is True

    def test_available_false_when_disabled(self):
        state = make_state(enabled=False)
        entity = self._make(state)
        assert entity.available is False

    def test_available_false_when_state_missing(self):
        entity = self._make(None)
        assert entity.available is False

    def test_handle_update_fires_event_on_count_increase(self):
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=1, last_alert=alert)
        entity = self._make(state)
        entity._last_seen_count = 0  # hasn't seen this alert yet
        entity._handle_coordinator_update()
        entity._trigger_event.assert_called_once()
        call_type, call_data = entity._trigger_event.call_args[0]
        assert call_type == "alert_received"
        assert call_data["message"] == "WAN offline"
        assert call_data["category"] == CATEGORY_NETWORK_WAN

    def test_handle_update_does_not_fire_when_count_unchanged(self):
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=1, last_alert=alert)
        entity = self._make(state)
        entity._last_seen_count = 1  # already seen this count
        entity._handle_coordinator_update()
        entity._trigger_event.assert_not_called()

    def test_handle_update_increments_last_seen_count(self):
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=3, last_alert=alert)
        entity = self._make(state)
        entity._last_seen_count = 2
        entity._handle_coordinator_update()
        assert entity._last_seen_count == 3

    def test_handle_update_noop_when_no_state(self):
        entity = self._make(None)
        entity._handle_coordinator_update()
        entity._trigger_event.assert_not_called()

    def test_handle_update_noop_when_no_last_alert(self):
        state = make_state(alert_count=0, last_alert=None)
        entity = self._make(state)
        entity._handle_coordinator_update()
        entity._trigger_event.assert_not_called()

    def test_event_payload_contains_all_fields(self):
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=1, last_alert=alert)
        entity = self._make(state)
        entity._last_seen_count = 0
        entity._handle_coordinator_update()
        _, payload = entity._trigger_event.call_args[0]
        for key in (
            "message",
            "category",
            "device_name",
            "alert_key",
            "severity",
            "site",
            "received_at",
        ):
            assert key in payload


# ═══════════════════════════════════════════════════════════════════════════════
# button
# ═══════════════════════════════════════════════════════════════════════════════


class TestUniFiClearCategoryButton:
    def _make(self, state: CategoryState | None):
        from custom_components.unifi_alerts.button import UniFiClearCategoryButton

        coord = make_coordinator({CATEGORY_NETWORK_WAN: state} if state else {})
        entry = make_entry()
        return UniFiClearCategoryButton(coord, entry, CATEGORY_NETWORK_WAN)

    @pytest.mark.asyncio
    async def test_press_cancels_pending_clear_task(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        await entity.async_press()
        entity._coordinator.cancel_clear.assert_called_once_with(CATEGORY_NETWORK_WAN)

    @pytest.mark.asyncio
    async def test_press_clears_state(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        await entity.async_press()
        assert state.is_alerting is False

    @pytest.mark.asyncio
    async def test_press_notifies_coordinator(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        await entity.async_press()
        entity._coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_press_noop_when_no_state(self):
        entity = self._make(None)
        # Should not raise
        await entity.async_press()
        entity._coordinator.cancel_clear.assert_called_once_with(CATEGORY_NETWORK_WAN)

    def test_unique_id_format(self):
        state = make_state()
        entity = self._make(state)
        assert entity.unique_id == f"entry-abc_{CATEGORY_NETWORK_WAN}_clear"


class TestUniFiClearAllButton:
    def _make(self, states: dict[str, CategoryState]):
        from custom_components.unifi_alerts.button import UniFiClearAllButton

        coord = make_coordinator(states)
        entry = make_entry()
        return UniFiClearAllButton(coord, entry)

    @pytest.mark.asyncio
    async def test_press_clears_all_alerting_categories(self):
        wan_state = make_state(category=CATEGORY_NETWORK_WAN, is_alerting=True)
        threat_state = make_state(category=CATEGORY_SECURITY_THREAT, is_alerting=True)
        states = {
            CATEGORY_NETWORK_WAN: wan_state,
            CATEGORY_SECURITY_THREAT: threat_state,
        }
        entity = self._make(states)
        await entity.async_press()
        assert wan_state.is_alerting is False
        assert threat_state.is_alerting is False

    @pytest.mark.asyncio
    async def test_press_skips_non_alerting_categories(self):
        wan_state = make_state(category=CATEGORY_NETWORK_WAN, is_alerting=False)
        states = {CATEGORY_NETWORK_WAN: wan_state}
        entity = self._make(states)
        await entity.async_press()
        # cancel_clear should NOT have been called (nothing was alerting)
        entity._coordinator.cancel_clear.assert_not_called()

    @pytest.mark.asyncio
    async def test_press_cancels_clear_tasks_for_alerting_categories(self):
        wan_state = make_state(category=CATEGORY_NETWORK_WAN, is_alerting=True)
        states = {CATEGORY_NETWORK_WAN: wan_state}
        entity = self._make(states)
        await entity.async_press()
        entity._coordinator.cancel_clear.assert_called_once_with(CATEGORY_NETWORK_WAN)

    @pytest.mark.asyncio
    async def test_press_notifies_coordinator_once(self):
        wan_state = make_state(category=CATEGORY_NETWORK_WAN, is_alerting=True)
        states = {CATEGORY_NETWORK_WAN: wan_state}
        entity = self._make(states)
        await entity.async_press()
        entity._coordinator.async_set_updated_data.assert_called_once()
