"""Tests for data models."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_CLIENT,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_POWER,
    CATEGORY_SECURITY_FIREWALL,
    CATEGORY_SECURITY_THREAT,
)
from custom_components.unifi_alerts.models import CategoryState, UniFiAlert, _render_message_raw


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

    def test_from_api_alarm_epoch_ms(self):
        """Numeric epoch-ms timestamps must be parsed, not silently dropped."""
        epoch_ms = 1705320600000
        expected = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
        alarm = {"msg": "test", "timestamp": epoch_ms}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert alert.received_at == expected
        assert alert.received_at.tzinfo == UTC

    def test_from_api_alarm_epoch_ms_string(self):
        """Numeric-string epoch-ms timestamps are also accepted (fromisoformat rejects them)."""
        epoch_ms = 1705320600000
        expected = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
        alarm = {"msg": "test", "timestamp": str(epoch_ms)}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert alert.received_at == expected

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


class TestRenderMessageRaw:
    """Tests for the _render_message_raw helper."""

    def test_substitutes_name_from_parameter_dict(self):
        raw = "Threat from {SRC_IP} to {DST_CLIENT}."
        params = {
            "SRC_IP": {"id": "198.51.100.1", "name": "198.51.100.1"},
            "DST_CLIENT": {"id": "aa:bb:cc:dd:ee:ff", "name": "my-device"},
        }
        result = _render_message_raw(raw, params)
        assert result == "Threat from 198.51.100.1 to my-device."

    def test_falls_back_to_id_when_name_absent(self):
        raw = "Device {DEVICE} reported issue."
        params = {"DEVICE": {"id": "device-123"}}
        result = _render_message_raw(raw, params)
        assert result == "Device device-123 reported issue."

    def test_falls_back_to_key_when_both_absent(self):
        raw = "Event from {SOURCE}."
        params = {"SOURCE": {}}
        result = _render_message_raw(raw, params)
        assert result == "Event from SOURCE."

    def test_unknown_placeholder_left_intact(self):
        raw = "Alert: {KNOWN} and {UNKNOWN}."
        params = {"KNOWN": {"name": "foo"}}
        result = _render_message_raw(raw, params)
        assert result == "Alert: foo and {UNKNOWN}."

    def test_scalar_parameter_value_converted_to_str(self):
        raw = "Count: {NUM}."
        params = {"NUM": 42}
        result = _render_message_raw(raw, params)
        assert result == "Count: 42."

    def test_empty_message_raw_returns_empty(self):
        result = _render_message_raw("", {})
        assert result == ""


class TestFromSystemLogEvent:
    """Tests for UniFiAlert.from_system_log_event() — v2 system-log parser."""

    # Minimal valid event matching the field-confirmed schema from docs/research/alert-endpoints.md
    _BASE_EVENT = {
        "id": "60a1b2c3d4e5f60718293a4b",
        "category": "SECURITY",
        "event": "THREAT_BLOCKED",
        "key": "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT",
        "message_raw": "Intrusion from {SRC_IP} to {DST_CLIENT} blocked.",
        "parameters": {
            "SRC_IP": {"id": "198.51.100.1", "name": "198.51.100.1", "not_actionable": True},
            "DST_CLIENT": {"id": "bc:24:11:aa:bb:cc", "name": "my-laptop"},
        },
        "severity": "HIGH",
        "status": "NEW",
        "timestamp": 1778025612345,
        "subcategory": "SECURITY_INTRUSION_PREVENTION",
        "type": "THREAT_DETECTION_AND_PREVENTION",
    }

    def test_parses_epoch_ms_timestamp(self):
        """timestamp (epoch ms integer) must become a UTC-aware datetime."""
        event = dict(self._BASE_EVENT)
        alert = UniFiAlert.from_system_log_event(event)
        expected = datetime.fromtimestamp(1778025612345 / 1000, tz=UTC)
        assert alert.received_at == expected
        assert alert.received_at.tzinfo == UTC

    def test_parses_epoch_ms_string_timestamp(self):
        """Numeric-string epoch ms must also be accepted."""
        event = dict(self._BASE_EVENT, timestamp="1778025612345")
        alert = UniFiAlert.from_system_log_event(event)
        expected = datetime.fromtimestamp(1778025612345 / 1000, tz=UTC)
        assert alert.received_at == expected

    def test_missing_timestamp_falls_back_to_now(self):
        """Missing timestamp must not raise; falls back to datetime.now(UTC)."""
        event = {k: v for k, v in self._BASE_EVENT.items() if k != "timestamp"}
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.received_at.tzinfo == UTC

    def test_renders_message_template(self):
        """message_raw + parameters must produce a rendered display message."""
        alert = UniFiAlert.from_system_log_event(dict(self._BASE_EVENT))
        assert "198.51.100.1" in alert.message
        assert "my-laptop" in alert.message
        assert "{SRC_IP}" not in alert.message

    def test_message_truncated_at_255(self):
        event = dict(self._BASE_EVENT, message_raw="x" * 300, parameters={})
        alert = UniFiAlert.from_system_log_event(event)
        assert len(alert.message) == 255

    def test_maps_known_v2_key_to_category(self):
        """Known v2 key must resolve to the correct integration category."""
        alert = UniFiAlert.from_system_log_event(dict(self._BASE_EVENT))
        assert alert.category == CATEGORY_SECURITY_THREAT

    def test_maps_wan_key_to_network_wan(self):
        event = dict(self._BASE_EVENT, key="WAN_TRANSITION", category="INTERNET_AND_WAN")
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.category == CATEGORY_NETWORK_WAN

    def test_maps_device_key_to_network_device(self):
        event = dict(self._BASE_EVENT, key="DEVICE_DISCONNECTED", category="UNIFI_DEVICES")
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.category == CATEGORY_NETWORK_DEVICE

    def test_maps_client_key_to_network_client(self):
        event = dict(self._BASE_EVENT, key="CLIENT_CONNECTED", category="CLIENT_DEVICES")
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.category == CATEGORY_NETWORK_CLIENT

    def test_maps_power_key_to_power(self):
        event = dict(self._BASE_EVENT, key="POE_OVERLOAD", category="POWER")
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.category == CATEGORY_POWER

    def test_unknown_key_falls_back_to_category_enum(self):
        """An unmapped key with a known category enum should fall back to enum mapping."""
        event = dict(self._BASE_EVENT, key="SOME_FUTURE_SECURITY_KEY", category="SECURITY")
        alert = UniFiAlert.from_system_log_event(event)
        # Falls back to SYSTEM_LOG_CATEGORY_FALLBACK["SECURITY"] = CATEGORY_SECURITY_THREAT
        assert alert.category == CATEGORY_SECURITY_THREAT

    def test_unknown_key_and_unknown_category_gives_empty_category(self):
        """Fully unknown key + unknown category results in category='' (caller skips)."""
        event = dict(self._BASE_EVENT, key="TOTALLY_UNKNOWN", category="AUDIT")
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.category == ""

    def test_key_field_preserved(self):
        alert = UniFiAlert.from_system_log_event(dict(self._BASE_EVENT))
        assert alert.key == "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT"

    def test_severity_field_preserved(self):
        alert = UniFiAlert.from_system_log_event(dict(self._BASE_EVENT))
        assert alert.severity == "HIGH"

    def test_raw_dict_preserved(self):
        event = dict(self._BASE_EVENT)
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.raw == event

    def test_firewall_key_maps_to_security_firewall(self):
        event = dict(self._BASE_EVENT, key="FIREWALL_BLOCK", category="SECURITY")
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.category == CATEGORY_SECURITY_FIREWALL

    def test_fallback_to_title_raw_when_no_message_raw(self):
        event = dict(self._BASE_EVENT)
        event.pop("message_raw")
        event["title_raw"] = "Threat Detected and Blocked"
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.message == "Threat Detected and Blocked"

    def test_fallback_to_key_when_no_message_raw_or_title_raw(self):
        event = {k: v for k, v in self._BASE_EVENT.items() if k not in ("message_raw",)}
        event.pop("title_raw", None)
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.message == "THREAT_BLOCKED_KNOWN_DESTINATION_CLIENT"
