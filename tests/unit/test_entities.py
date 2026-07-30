"""Tests for all entity platform classes: binary_sensor, sensor, event, button."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

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
    coord.async_clear_category = AsyncMock()
    coord.async_clear_all = AsyncMock()
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

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            pytest.param(make_state(is_alerting=True), True, id="alerting"),
            pytest.param(make_state(is_alerting=False), False, id="not-alerting"),
            pytest.param(None, False, id="state-missing"),
        ],
    )
    def test_is_on(self, state, expected):
        entity = self._make(state)
        assert entity.is_on is expected

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            pytest.param(make_state(enabled=True), True, id="enabled"),
            pytest.param(make_state(enabled=False), False, id="disabled"),
        ],
    )
    def test_available(self, state, expected):
        entity = self._make(state)
        assert entity.available is expected

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
        assert attrs["last_severity"] == "critical"
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

    def test_extra_attrs_webhook_health_never_received(self):
        state = make_state()
        entity = self._make(state)
        attrs = entity.extra_state_attributes
        assert attrs["webhook_health"] == "never_received"
        assert attrs["last_webhook_at"] is None

    def test_extra_attrs_webhook_health_healthy(self):
        state = make_state()
        state.last_webhook_at = datetime.now(UTC)
        entity = self._make(state)
        attrs = entity.extra_state_attributes
        assert attrs["webhook_health"] == "healthy"
        assert attrs["last_webhook_at"] == state.last_webhook_at.isoformat()

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

    @pytest.mark.parametrize(
        ("is_alerting", "expected"),
        [
            pytest.param(True, True, id="alerting"),
            pytest.param(False, False, id="not-alerting"),
        ],
    )
    def test_is_on(self, is_alerting, expected):
        states = {CATEGORY_NETWORK_WAN: make_state(is_alerting=is_alerting)}
        entity = self._make(states)
        assert entity.is_on is expected

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
        assert attrs["last_severity"] == "critical"

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

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            pytest.param(
                make_state(last_alert=make_alert(message="WAN went down")),
                "WAN went down",
                id="alert-present",
            ),
            pytest.param(make_state(), None, id="no-alert"),
            pytest.param(None, None, id="state-missing"),
        ],
    )
    def test_native_value(self, state, expected):
        entity = self._make(state)
        assert entity.native_value == expected

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            pytest.param(make_state(enabled=True), True, id="enabled"),
            pytest.param(make_state(enabled=False), False, id="disabled"),
        ],
    )
    def test_available(self, state, expected):
        entity = self._make(state)
        assert entity.available is expected

    @pytest.mark.parametrize(
        ("is_alerting", "expected_icon"),
        [
            pytest.param(True, CATEGORY_ICONS[CATEGORY_NETWORK_WAN], id="alerting"),
            pytest.param(False, CATEGORY_ICONS_OK[CATEGORY_NETWORK_WAN], id="not-alerting"),
        ],
    )
    def test_icon(self, is_alerting, expected_icon):
        state = make_state(is_alerting=is_alerting)
        entity = self._make(state)
        assert entity.icon == expected_icon

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

    def test_state_class_is_measurement(self):
        from homeassistant.components.sensor import SensorStateClass

        entity = self._make(make_state())
        assert entity.state_class == SensorStateClass.MEASUREMENT

    def test_device_class_is_none(self):
        entity = self._make(make_state())
        assert entity.device_class is None


class TestUniFiWebhookHealthSensor:
    def _make(self, state: CategoryState | None):
        from custom_components.unifi_alerts.sensor import UniFiWebhookHealthSensor

        coord = make_coordinator({CATEGORY_NETWORK_WAN: state} if state else {})
        entry = make_entry()
        return UniFiWebhookHealthSensor(coord, entry, CATEGORY_NETWORK_WAN)

    def test_native_value_never_received(self):
        entity = self._make(make_state())
        assert entity.native_value == "never_received"

    def test_native_value_healthy(self):
        state = make_state()
        state.last_webhook_at = datetime.now(UTC)
        entity = self._make(state)
        assert entity.native_value == "healthy"

    def test_native_value_stale(self):
        state = make_state()
        state.last_webhook_at = datetime(2020, 1, 1, tzinfo=UTC)
        entity = self._make(state)
        assert entity.native_value == "stale"

    def test_native_value_none_when_state_missing(self):
        entity = self._make(None)
        assert entity.native_value is None

    def test_available_reflects_enabled_state(self):
        entity_on = self._make(make_state(enabled=True))
        entity_off = self._make(make_state(enabled=False))
        assert entity_on.available is True
        assert entity_off.available is False

    def test_extra_attrs_last_webhook_at_none(self):
        entity = self._make(make_state())
        assert entity.extra_state_attributes["last_webhook_at"] is None

    def test_extra_attrs_last_webhook_at_set(self):
        state = make_state()
        state.last_webhook_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        entity = self._make(state)
        assert entity.extra_state_attributes["last_webhook_at"] == state.last_webhook_at.isoformat()

    def test_extra_attrs_empty_when_no_state(self):
        entity = self._make(None)
        assert entity.extra_state_attributes == {}

    def test_device_class_is_enum(self):
        from homeassistant.components.sensor import SensorDeviceClass

        entity = self._make(make_state())
        assert entity.device_class == SensorDeviceClass.ENUM

    def test_options_cover_all_health_states(self):
        entity = self._make(make_state())
        assert entity.options == ["never_received", "healthy", "stale"]

    def test_unique_id_format(self):
        entity = self._make(make_state())
        assert entity.unique_id.endswith(f"_{CATEGORY_NETWORK_WAN}_webhook_health")


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

    def test_state_class_is_measurement(self):
        from homeassistant.components.sensor import SensorStateClass

        entity = self._make({})
        assert entity.state_class == SensorStateClass.MEASUREMENT

    def test_device_class_is_none(self):
        entity = self._make({})
        assert entity.device_class is None


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

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            pytest.param(make_state(enabled=True), True, id="enabled"),
            pytest.param(make_state(enabled=False), False, id="disabled"),
            pytest.param(None, False, id="state-missing"),
        ],
    )
    def test_available(self, state, expected):
        entity = self._make(state)
        assert entity.available is expected

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

    @pytest.mark.asyncio
    async def test_reload_does_not_replay_restored_alert(self):
        """Regression for #116: options save triggers a full reload; the
        restored CategoryState carries a non-zero alert_count, and the first
        coordinator update post-reload must NOT re-fire alert_received.
        """
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=3, last_alert=alert)
        entity = self._make(state)
        # Simulate the reload boundary: __init__ has just set _last_seen_count
        # to 0; async_added_to_hass must seed from the restored alert_count.
        assert entity._last_seen_count == 0
        await entity.async_added_to_hass()
        assert entity._last_seen_count == 3
        # First coordinator update after restore — same count, no new alert.
        entity._handle_coordinator_update()
        entity._trigger_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_alert_after_reload_still_fires_once(self):
        """The seeding fix for #116 must not suppress genuinely new alerts."""
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=3, last_alert=alert)
        entity = self._make(state)
        await entity.async_added_to_hass()
        # A fresh push arrives — coordinator bumps alert_count to 4.
        state.alert_count = 4
        entity._handle_coordinator_update()
        entity._trigger_event.assert_called_once()
        # And a second identical update (no new push) must not re-fire.
        entity._handle_coordinator_update()
        entity._trigger_event.assert_called_once()

    def test_multiple_rapid_alerts_each_fire_exactly_once(self):
        """Several webhook pushes in quick succession must each fire their
        own alert_received event - no event may be skipped or double-fired."""
        alert = make_alert()
        state = make_state(is_alerting=True, alert_count=0, last_alert=alert)
        entity = self._make(state)
        entity._last_seen_count = 0

        for expected_count in (1, 2, 3):
            state.alert_count = expected_count
            entity._handle_coordinator_update()

        assert entity._trigger_event.call_count == 3
        assert entity._last_seen_count == 3

    @pytest.mark.asyncio
    async def test_added_to_hass_no_state_leaves_seed_zero(self):
        """Fresh install / unknown category: no restored state → seed stays 0."""
        entity = self._make(None)
        await entity.async_added_to_hass()
        assert entity._last_seen_count == 0


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
    async def test_press_delegates_to_coordinator(self):
        state = make_state(is_alerting=True)
        entity = self._make(state)
        await entity.async_press()
        entity.coordinator.async_clear_category.assert_awaited_once_with(CATEGORY_NETWORK_WAN)

    def test_unique_id_format(self):
        state = make_state()
        entity = self._make(state)
        assert entity.unique_id == f"entry-abc_{CATEGORY_NETWORK_WAN}_clear"

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            pytest.param(make_state(enabled=True), True, id="enabled"),
            pytest.param(make_state(enabled=False), False, id="disabled"),
            pytest.param(None, False, id="state-missing"),
        ],
    )
    def test_available(self, state, expected):
        entity = self._make(state)
        assert entity.available is expected

    def test_handle_coordinator_update_writes_ha_state(self):
        """Coordinator update must re-evaluate available without a reload."""
        state = make_state(enabled=True)
        entity = self._make(state)
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_called_once()

    def test_availability_updates_after_coordinator_change(self):
        """available reflects coordinator state after _handle_coordinator_update."""
        state = make_state(enabled=True)
        entity = self._make(state)
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        assert entity.available is True
        state.enabled = False
        entity._handle_coordinator_update()
        assert entity.available is False


class TestUniFiClearAllButton:
    def _make(self, states: dict[str, CategoryState]):
        from custom_components.unifi_alerts.button import UniFiClearAllButton

        coord = make_coordinator(states)
        entry = make_entry()
        return UniFiClearAllButton(coord, entry)

    @pytest.mark.asyncio
    async def test_press_delegates_to_coordinator(self):
        wan_state = make_state(category=CATEGORY_NETWORK_WAN, is_alerting=True)
        states = {CATEGORY_NETWORK_WAN: wan_state}
        entity = self._make(states)
        await entity.async_press()
        entity.coordinator.async_clear_all.assert_awaited_once()

    @pytest.mark.parametrize(
        ("states", "expected"),
        [
            pytest.param(
                {
                    CATEGORY_NETWORK_WAN: make_state(enabled=True),
                    CATEGORY_SECURITY_THREAT: make_state(enabled=False),
                },
                True,
                id="any-category-enabled",
            ),
            pytest.param(
                {
                    CATEGORY_NETWORK_WAN: make_state(enabled=False),
                    CATEGORY_SECURITY_THREAT: make_state(enabled=False),
                },
                False,
                id="all-categories-disabled",
            ),
            pytest.param({}, False, id="no-categories"),
        ],
    )
    def test_available(self, states, expected):
        entity = self._make(states)
        assert entity.available is expected

    def test_handle_coordinator_update_writes_ha_state(self):
        """Coordinator update must re-evaluate available without a reload."""
        states = {CATEGORY_NETWORK_WAN: make_state(enabled=True)}
        entity = self._make(states)
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_called_once()

    def test_availability_updates_after_coordinator_change(self):
        """available reflects coordinator state after _handle_coordinator_update."""
        wan_state = make_state(category=CATEGORY_NETWORK_WAN, enabled=True)
        states = {CATEGORY_NETWORK_WAN: wan_state}
        entity = self._make(states)
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        assert entity.available is True
        wan_state.enabled = False
        entity._handle_coordinator_update()
        assert entity.available is False


# ═══════════════════════════════════════════════════════════════════════════════
# Device info — configuration_url + proactive registration cross-checks
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceInfo:
    """_device_info() helpers in all four platforms must include configuration_url."""

    @pytest.mark.parametrize(
        "platform",
        ["binary_sensor", "sensor", "event", "button"],
    )
    def test_device_info_has_configuration_url(self, platform):
        import importlib

        _device_info = importlib.import_module(
            f"custom_components.unifi_alerts.{platform}"
        )._device_info

        entry = make_entry()
        info = _device_info(entry)
        assert info["configuration_url"] == entry.data["controller_url"]

    def test_all_platforms_share_identical_identifiers(self):
        from custom_components.unifi_alerts.binary_sensor import _device_info as bs_info
        from custom_components.unifi_alerts.button import _device_info as btn_info
        from custom_components.unifi_alerts.event import _device_info as ev_info
        from custom_components.unifi_alerts.sensor import _device_info as s_info

        entry = make_entry()
        assert bs_info(entry)["identifiers"] == s_info(entry)["identifiers"]
        assert bs_info(entry)["identifiers"] == ev_info(entry)["identifiers"]
        assert bs_info(entry)["identifiers"] == btn_info(entry)["identifiers"]


# ═══════════════════════════════════════════════════════════════════════════════
# Entity categories + message sensor default
# ═══════════════════════════════════════════════════════════════════════════════


class TestEntityCategories:
    """Verify entity_category assignments for the polish items bundled into v1.3."""

    @pytest.mark.parametrize(
        ("entity_cls_path", "expected_category"),
        [
            pytest.param("sensor.UniFiCategoryMessageSensor", "DIAGNOSTIC", id="message-sensor"),
            pytest.param(
                "sensor.UniFiWebhookHealthSensor", "DIAGNOSTIC", id="webhook-health-sensor"
            ),
            pytest.param("button.UniFiClearCategoryButton", "CONFIG", id="clear-category-button"),
            pytest.param("button.UniFiClearAllButton", "CONFIG", id="clear-all-button"),
        ],
    )
    def test_entity_category_assignment(self, entity_cls_path, expected_category):
        import importlib

        from homeassistant.const import EntityCategory

        module_name, cls_name = entity_cls_path.rsplit(".", 1)
        entity_cls = getattr(
            importlib.import_module(f"custom_components.unifi_alerts.{module_name}"), cls_name
        )

        # CachedProperties metaclass stores _attr_* backing values as __attr_* in __dict__
        assert entity_cls.__dict__.get("__attr_entity_category") == getattr(
            EntityCategory, expected_category
        )

    def test_event_entity_has_no_device_class(self):
        from custom_components.unifi_alerts.event import UniFiAlertEventEntity

        # __attr_device_class is the CachedProperties backing key; absent means no override
        assert "__attr_device_class" not in UniFiAlertEventEntity.__dict__

    def test_message_sensor_returns_no_alerts_yet_when_empty(self):
        from custom_components.unifi_alerts.sensor import UniFiCategoryMessageSensor

        coord = make_coordinator({CATEGORY_NETWORK_WAN: make_state()})
        entry = make_entry()
        entity = UniFiCategoryMessageSensor(coord, entry, CATEGORY_NETWORK_WAN)
        assert entity.native_value is None

    def test_message_sensor_returns_message_when_alert_present(self):
        from custom_components.unifi_alerts.sensor import UniFiCategoryMessageSensor

        alert = make_alert(message="WAN went down")
        coord = make_coordinator({CATEGORY_NETWORK_WAN: make_state(last_alert=alert)})
        entry = make_entry()
        entity = UniFiCategoryMessageSensor(coord, entry, CATEGORY_NETWORK_WAN)
        assert entity.native_value == "WAN went down"


# ═══════════════════════════════════════════════════════════════════════════════
# Translation keys (ARCH-2): every entity routes its display name through
# `strings.json` via a per-category `_attr_translation_key` (e.g. `last_message_network_wan`).
# This locks the contract for localisation; the rendered English string lives in
# `strings.json` / `translations/en.json` and is verified for byte-parity by
# `scripts/check_translations.py`.
# ═══════════════════════════════════════════════════════════════════════════════


class TestTranslationKeys:
    """Verify each entity exposes the expected translation key + placeholders."""

    @pytest.mark.parametrize(
        ("entity_cls_path", "expected_key"),
        [
            pytest.param(
                "binary_sensor.UniFiCategoryBinarySensor",
                CATEGORY_NETWORK_WAN,
                id="category-binary-sensor",
            ),
            pytest.param(
                "sensor.UniFiCategoryMessageSensor",
                f"last_message_{CATEGORY_NETWORK_WAN}",
                id="message-sensor",
            ),
            pytest.param(
                "sensor.UniFiCategoryCountSensor",
                f"open_count_{CATEGORY_NETWORK_WAN}",
                id="count-sensor",
            ),
            pytest.param(
                "sensor.UniFiWebhookHealthSensor",
                f"webhook_health_{CATEGORY_NETWORK_WAN}",
                id="webhook-health-sensor",
            ),
            pytest.param(
                "event.UniFiAlertEventEntity", f"event_{CATEGORY_NETWORK_WAN}", id="event-entity"
            ),
            pytest.param(
                "button.UniFiClearCategoryButton",
                f"clear_{CATEGORY_NETWORK_WAN}",
                id="clear-category-button",
            ),
        ],
    )
    def test_per_category_entity_translation(self, entity_cls_path, expected_key):
        """Per-category entities (constructed with a category arg) route through strings.json."""
        import importlib

        module_name, cls_name = entity_cls_path.rsplit(".", 1)
        entity_cls = getattr(
            importlib.import_module(f"custom_components.unifi_alerts.{module_name}"), cls_name
        )

        coord = make_coordinator({CATEGORY_NETWORK_WAN: make_state()})
        entry = make_entry()
        entity = entity_cls(coord, entry, CATEGORY_NETWORK_WAN)
        assert entity.translation_key == expected_key
        assert entity.translation_placeholders == {}

    @pytest.mark.parametrize(
        ("entity_cls_path", "expected_key"),
        [
            pytest.param(
                "binary_sensor.UniFiRollupBinarySensor", "any_alert", id="rollup-binary-sensor"
            ),
            pytest.param("sensor.UniFiRollupCountSensor", "total_open", id="rollup-count-sensor"),
            pytest.param("button.UniFiClearAllButton", "clear_all", id="clear-all-button"),
        ],
    )
    def test_rollup_entity_translation(self, entity_cls_path, expected_key):
        """Rollup entities (constructed with no category arg) route through strings.json."""
        import importlib

        module_name, cls_name = entity_cls_path.rsplit(".", 1)
        entity_cls = getattr(
            importlib.import_module(f"custom_components.unifi_alerts.{module_name}"), cls_name
        )

        coord = make_coordinator({})
        entry = make_entry()
        entity = entity_cls(coord, entry)
        assert entity.translation_key == expected_key

    def test_unique_ids_unchanged_by_translation_migration(self):
        """unique_id is the contract for automations - it must NOT change."""
        from custom_components.unifi_alerts.binary_sensor import (
            UniFiCategoryBinarySensor,
            UniFiRollupBinarySensor,
        )
        from custom_components.unifi_alerts.button import (
            UniFiClearAllButton,
            UniFiClearCategoryButton,
        )
        from custom_components.unifi_alerts.event import UniFiAlertEventEntity
        from custom_components.unifi_alerts.sensor import (
            UniFiCategoryCountSensor,
            UniFiCategoryMessageSensor,
            UniFiRollupCountSensor,
            UniFiWebhookHealthSensor,
        )

        coord = make_coordinator({CATEGORY_NETWORK_WAN: make_state()})
        entry = make_entry()
        eid = entry.entry_id

        assert (
            UniFiCategoryBinarySensor(coord, entry, CATEGORY_NETWORK_WAN).unique_id
            == f"{eid}_{CATEGORY_NETWORK_WAN}_binary"
        )
        assert UniFiRollupBinarySensor(coord, entry).unique_id == f"{eid}_rollup_binary"
        assert (
            UniFiCategoryMessageSensor(coord, entry, CATEGORY_NETWORK_WAN).unique_id
            == f"{eid}_{CATEGORY_NETWORK_WAN}_message"
        )
        assert (
            UniFiCategoryCountSensor(coord, entry, CATEGORY_NETWORK_WAN).unique_id
            == f"{eid}_{CATEGORY_NETWORK_WAN}_count"
        )
        assert UniFiRollupCountSensor(coord, entry).unique_id == f"{eid}_rollup_count"
        assert (
            UniFiWebhookHealthSensor(coord, entry, CATEGORY_NETWORK_WAN).unique_id
            == f"{eid}_{CATEGORY_NETWORK_WAN}_webhook_health"
        )
        assert (
            UniFiAlertEventEntity(coord, entry, CATEGORY_NETWORK_WAN).unique_id
            == f"{eid}_{CATEGORY_NETWORK_WAN}_event"
        )
        assert (
            UniFiClearCategoryButton(coord, entry, CATEGORY_NETWORK_WAN).unique_id
            == f"{eid}_{CATEGORY_NETWORK_WAN}_clear"
        )
        assert UniFiClearAllButton(coord, entry).unique_id == f"{eid}_clear_all"


# ═══════════════════════════════════════════════════════════════════════════════
# Platform setup honours enabled flag
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlatformSetupHonoursEnabled:
    """Test that entity platforms only create entities for enabled categories."""

    @pytest.mark.asyncio
    async def test_binary_sensor_setup_skips_disabled(self):
        """Disabled categories should not create binary sensor entities."""
        from custom_components.unifi_alerts import binary_sensor

        states = {
            CATEGORY_NETWORK_WAN: make_state(category=CATEGORY_NETWORK_WAN, enabled=True),
            CATEGORY_SECURITY_THREAT: make_state(category=CATEGORY_SECURITY_THREAT, enabled=False),
        }
        coord = make_coordinator(states)
        entry = make_entry()
        entry.runtime_data = MagicMock(coordinator=coord)

        added: list = []
        await binary_sensor.async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        uids = [e.unique_id for e in added]
        # enabled category present, disabled absent, aggregate present
        assert any(CATEGORY_NETWORK_WAN in u for u in uids)
        assert not any(CATEGORY_SECURITY_THREAT in u for u in uids)
        assert any(u.endswith("_rollup_binary") for u in uids)

    @pytest.mark.asyncio
    async def test_sensor_setup_skips_disabled(self):
        """Disabled categories should not create sensor entities."""
        from custom_components.unifi_alerts import sensor

        states = {
            CATEGORY_NETWORK_WAN: make_state(category=CATEGORY_NETWORK_WAN, enabled=True),
            CATEGORY_SECURITY_THREAT: make_state(category=CATEGORY_SECURITY_THREAT, enabled=False),
        }
        coord = make_coordinator(states)
        entry = make_entry()
        entry.runtime_data = MagicMock(coordinator=coord)

        added: list = []
        await sensor.async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        uids = [e.unique_id for e in added]
        # enabled category present (3 entities), disabled absent, aggregate present
        assert any(CATEGORY_NETWORK_WAN in u for u in uids)
        assert not any(CATEGORY_SECURITY_THREAT in u for u in uids)
        assert any(u.endswith("_rollup_count") for u in uids)

    @pytest.mark.asyncio
    async def test_event_setup_skips_disabled(self):
        """Disabled categories should not create event entities."""
        from custom_components.unifi_alerts import event

        states = {
            CATEGORY_NETWORK_WAN: make_state(category=CATEGORY_NETWORK_WAN, enabled=True),
            CATEGORY_SECURITY_THREAT: make_state(category=CATEGORY_SECURITY_THREAT, enabled=False),
        }
        coord = make_coordinator(states)
        entry = make_entry()
        entry.runtime_data = MagicMock(coordinator=coord)

        added: list = []
        await event.async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        uids = [e.unique_id for e in added]
        # enabled category present, disabled absent
        assert any(CATEGORY_NETWORK_WAN in u for u in uids)
        assert not any(CATEGORY_SECURITY_THREAT in u for u in uids)

    @pytest.mark.asyncio
    async def test_button_setup_skips_disabled(self):
        """Disabled categories should not create button entities."""
        from custom_components.unifi_alerts import button

        states = {
            CATEGORY_NETWORK_WAN: make_state(category=CATEGORY_NETWORK_WAN, enabled=True),
            CATEGORY_SECURITY_THREAT: make_state(category=CATEGORY_SECURITY_THREAT, enabled=False),
        }
        coord = make_coordinator(states)
        entry = make_entry()
        entry.runtime_data = MagicMock(coordinator=coord)

        added: list = []
        await button.async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))

        uids = [e.unique_id for e in added]
        # enabled category present, disabled absent, aggregate present
        assert any(CATEGORY_NETWORK_WAN in u for u in uids)
        assert not any(CATEGORY_SECURITY_THREAT in u for u in uids)
        assert any(u.endswith("_clear_all") for u in uids)

    def test_prune_removes_disabled_and_keeps_enabled_and_aggregate(self):
        """The prune function should remove only disabled-category registry entries."""
        from unittest.mock import patch

        from custom_components.unifi_alerts import _prune_disabled_category_entities

        coord = make_coordinator(
            {
                CATEGORY_NETWORK_WAN: make_state(category=CATEGORY_NETWORK_WAN, enabled=True),
                CATEGORY_SECURITY_THREAT: make_state(
                    category=CATEGORY_SECURITY_THREAT, enabled=False
                ),
            }
        )
        entry = make_entry()

        def reg_entry(uid: str):
            m = MagicMock()
            m.unique_id = uid
            m.entity_id = uid
            return m

        entries = [
            reg_entry(f"{entry.entry_id}_{CATEGORY_NETWORK_WAN}_binary"),  # keep
            reg_entry(f"{entry.entry_id}_{CATEGORY_SECURITY_THREAT}_binary"),  # remove
            reg_entry(f"{entry.entry_id}_{CATEGORY_SECURITY_THREAT}_count"),  # remove
            reg_entry(f"{entry.entry_id}_rollup_binary"),  # keep (aggregate)
        ]
        registry = MagicMock()
        registry.async_remove = MagicMock()

        import custom_components.unifi_alerts as init_mod

        with (
            patch.object(init_mod.er, "async_get", return_value=registry),
            patch.object(init_mod.er, "async_entries_for_config_entry", return_value=entries),
        ):
            _prune_disabled_category_entities(MagicMock(), entry, coord)

        removed = {c.args[0] for c in registry.async_remove.call_args_list}
        assert removed == {
            f"{entry.entry_id}_{CATEGORY_SECURITY_THREAT}_binary",
            f"{entry.entry_id}_{CATEGORY_SECURITY_THREAT}_count",
        }
