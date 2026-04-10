"""Tests for data models."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.unifi_alerts.const import CATEGORY_NETWORK_WAN, CATEGORY_SECURITY_THREAT
from custom_components.unifi_alerts.models import CategoryState, UniFiAlert


class TestUniFiAlert:
    def test_from_webhook_payload_standard(self):
        payload = {
            "message": "WAN went offline",
            "key": "EVT_GW_WANTransition",
            "device_name": "UDM-Pro",
            "severity": "critical",
        }
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert alert.message == "WAN went offline"
        assert alert.key == "EVT_GW_WANTransition"
        assert alert.device_name == "UDM-Pro"
        assert alert.category == CATEGORY_NETWORK_WAN

    def test_from_webhook_payload_fallback_msg_field(self):
        payload = {"msg": "fallback message"}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert alert.message == "fallback message"

    def test_from_webhook_payload_empty_falls_back_to_str(self):
        payload = {"key": "EVT_GW_WANTransition"}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert len(alert.message) > 0

    def test_message_truncated_at_255(self):
        payload = {"message": "x" * 300}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert len(alert.message) == 255

    def test_from_api_alarm(self):
        alarm = {
            "key": "EVT_IPS_ThreatDetected",
            "msg": "Threat from 1.2.3.4",
            "datetime": "2024-01-15T10:30:00",
            "archived": False,
        }
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert alert.message == "Threat from 1.2.3.4"
        assert alert.key == "EVT_IPS_ThreatDetected"
        assert isinstance(alert.received_at, datetime)

    def test_from_api_alarm_bad_datetime_falls_back(self):
        alarm = {"msg": "test", "datetime": "not-a-date"}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert isinstance(alert.received_at, datetime)

    def test_from_webhook_payload_received_at_is_timezone_aware(self):
        """received_at must be UTC-aware so HA time comparisons work."""
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": "test"})
        assert alert.received_at.tzinfo is not None
        assert alert.received_at.tzinfo == UTC

    def test_from_api_alarm_fallback_received_at_is_timezone_aware(self):
        """Fallback datetime (no ts field) must still be UTC-aware."""
        alarm = {"msg": "test"}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert alert.received_at.tzinfo is not None

    def test_from_api_alarm_bad_ts_fallback_is_timezone_aware(self):
        """Fallback datetime (bad ts) must still be UTC-aware."""
        alarm = {"msg": "test", "datetime": "not-a-date"}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert alert.received_at.tzinfo is not None


class TestCategoryState:
    def test_initial_state(self):
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        assert state.is_alerting is False
        assert state.alert_count == 0
        assert state.last_alert is None

    def test_apply_alert_sets_alerting(self):
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": "test"})
        state.apply_alert(alert)
        assert state.is_alerting is True
        assert state.alert_count == 1
        assert state.last_alert is alert

    def test_apply_alert_increments_count(self):
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        for i in range(3):
            alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": f"alert {i}"})
            state.apply_alert(alert)
        assert state.alert_count == 3

    def test_clear_resets_alerting(self):
        state = CategoryState(category=CATEGORY_NETWORK_WAN, is_alerting=True)
        state.clear()
        assert state.is_alerting is False
        assert state.last_cleared_at is not None

    def test_clear_last_cleared_at_is_timezone_aware(self):
        """last_cleared_at must be UTC-aware."""
        state = CategoryState(category=CATEGORY_NETWORK_WAN, is_alerting=True)
        state.clear()
        assert state.last_cleared_at is not None
        assert state.last_cleared_at.tzinfo is not None
