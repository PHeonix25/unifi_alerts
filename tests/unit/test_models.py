"""Tests for data models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_CLIENT,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CATEGORY_POWER,
    CATEGORY_SECURITY_FIREWALL,
    CATEGORY_SECURITY_THREAT,
)
from custom_components.unifi_alerts.models import (
    CategoryState,
    UniFiAlert,
    _render_message_raw,
)


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

    def test_raw_not_retained_after_webhook_construction(self):
        """Raw payload must not be retained in memory after building from a webhook."""
        payload = {"message": "test", "client_mac": "aa:bb:cc:dd:ee:ff", "src_ip": "10.0.0.1"}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert alert.raw == {}

    def test_raw_not_retained_after_api_alarm_construction(self):
        """Raw alarm dict must not be retained in memory after building from a poll."""
        alarm = {
            "msg": "threat",
            "key": "EVT_IPS_ThreatDetected",
            "client_mac": "aa:bb:cc:dd:ee:ff",
        }
        alert = UniFiAlert.from_api_alarm(CATEGORY_NETWORK_WAN, alarm)
        assert alert.raw == {}

    def test_key_truncated_at_64(self):
        payload = {"message": "test", "key": "K" * 100}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert len(alert.key) == 64

    def test_device_name_truncated_at_255(self):
        payload = {"message": "test", "device_name": "D" * 300}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert len(alert.device_name) == 255

    def test_severity_truncated_at_32(self):
        payload = {"message": "test", "severity": "S" * 100}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert len(alert.severity) == 32

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


class TestNonStringPayloadFields:
    """device_name and site must coerce to str for any payload value, matching the
    existing str(...) handling already applied to message/key/severity. Regression
    tests for GitHub issue #266."""

    _NON_STRING_VALUES = [123, {"nested": "dict"}, ["a", "list"], None]

    @pytest.mark.parametrize("value", _NON_STRING_VALUES)
    def test_webhook_device_name_non_string_coerced(self, value):
        payload = {"message": "test", "device_name": value}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert isinstance(alert.device_name, str)

    @pytest.mark.parametrize("value", _NON_STRING_VALUES)
    def test_webhook_site_non_string_coerced(self, value):
        payload = {"message": "test", "site_name": value}
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, payload)
        assert isinstance(alert.site, str)

    @pytest.mark.parametrize("value", _NON_STRING_VALUES)
    def test_api_alarm_device_name_non_string_coerced(self, value):
        alarm = {"msg": "test", "device_name": value}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert isinstance(alert.device_name, str)

    @pytest.mark.parametrize("value", _NON_STRING_VALUES)
    def test_api_alarm_site_non_string_coerced(self, value):
        alarm = {"msg": "test", "site_name": value}
        alert = UniFiAlert.from_api_alarm(CATEGORY_SECURITY_THREAT, alarm)
        assert isinstance(alert.site, str)

    @pytest.mark.parametrize("value", _NON_STRING_VALUES)
    def test_system_log_event_device_name_non_string_coerced(self, value):
        event = {
            "key": "FIREWALL_BLOCK",
            "category": "SECURITY",
            "timestamp": 1700000000000,
            "status": "NEW",
            "device_name": value,
        }
        alert = UniFiAlert.from_system_log_event(event, set())
        assert isinstance(alert.device_name, str)

    @pytest.mark.parametrize("value", _NON_STRING_VALUES)
    def test_system_log_event_site_non_string_coerced(self, value):
        event = {
            "key": "FIREWALL_BLOCK",
            "category": "SECURITY",
            "timestamp": 1700000000000,
            "status": "NEW",
            "site_name": value,
        }
        alert = UniFiAlert.from_system_log_event(event, set())
        assert isinstance(alert.site, str)


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

    def test_last_webhook_at_defaults_to_none(self):
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        assert state.last_webhook_at is None


class TestWebhookHealth:
    """Tests for CategoryState.webhook_health()."""

    def test_never_received_when_no_webhook(self):
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        assert state.webhook_health() == "never_received"

    def test_healthy_when_recent(self):
        now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
        state = CategoryState(
            category=CATEGORY_NETWORK_WAN,
            last_webhook_at=datetime(2026, 6, 11, 10, 0, 0, tzinfo=UTC),
        )
        assert state.webhook_health(now=now) == "healthy"

    def test_healthy_at_exact_window_boundary(self):
        """A webhook exactly WEBHOOK_STALE_AFTER_SECONDS old is still healthy."""
        from custom_components.unifi_alerts.const import WEBHOOK_STALE_AFTER_SECONDS

        now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
        state = CategoryState(
            category=CATEGORY_NETWORK_WAN,
            last_webhook_at=now - timedelta(seconds=WEBHOOK_STALE_AFTER_SECONDS),
        )
        assert state.webhook_health(now=now) == "healthy"

    def test_stale_when_past_window(self):
        from custom_components.unifi_alerts.const import WEBHOOK_STALE_AFTER_SECONDS

        now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
        state = CategoryState(
            category=CATEGORY_NETWORK_WAN,
            last_webhook_at=now - timedelta(seconds=WEBHOOK_STALE_AFTER_SECONDS + 1),
        )
        assert state.webhook_health(now=now) == "stale"

    def test_defaults_now_to_current_time(self):
        """Omitting now must not raise and should read healthy for a just-now webhook."""
        state = CategoryState(
            category=CATEGORY_NETWORK_WAN,
            last_webhook_at=datetime.now(UTC),
        )
        assert state.webhook_health() == "healthy"


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

    def test_parameter_value_containing_token_is_not_re_substituted(self):
        """A param value that looks like {TOKEN} must not trigger a second pass."""
        raw = "Source: {SRC}."
        params = {"SRC": {"name": "{DST}"}, "DST": {"name": "secret"}}
        result = _render_message_raw(raw, params)
        # Single-pass: {SRC} -> "{DST}" and then the substitution stops.
        # If double-pass were allowed, the result would be "Source: secret."
        assert result == "Source: {DST}."

    def test_overlapping_prefix_keys_resolve_independently(self):
        """{IP} and {IP_DST} must each be replaced with their own value."""
        raw = "From {IP} to {IP_DST}."
        params = {
            "IP": {"name": "1.2.3.4"},
            "IP_DST": {"name": "5.6.7.8"},
        }
        result = _render_message_raw(raw, params)
        assert result == "From 1.2.3.4 to 5.6.7.8."

    def test_non_string_parameter_values_converted(self):
        """Non-string param values (int, bool, None) must be stringified."""
        raw = "Count={COUNT} active={ACTIVE} extra={EXTRA}."
        params = {"COUNT": 7, "ACTIVE": True, "EXTRA": None}
        result = _render_message_raw(raw, params)
        assert result == "Count=7 active=True extra=None."


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

    def test_raw_not_retained_after_construction(self):
        """Raw payload must be empty after construction; no in-memory privacy exposure."""
        event = dict(self._BASE_EVENT)
        alert = UniFiAlert.from_system_log_event(event)
        assert alert.raw == {}

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


class TestUnknownSystemLogKeyObservability:
    """Tests for warn-once-per-unknown-key behaviour in from_system_log_event.

    Deduplication is now caller-scoped: pass a shared set[str] as seen_keys to
    get warn-once behaviour; pass None to warn on every call.
    """

    _BASE_EVENT = {
        "id": "x",
        "category": "SECURITY",
        "key": "UNMAPPED_BUT_HAS_ENUM_FALLBACK",
        "timestamp": 1700000000000,
        "status": "NEW",
    }

    def test_unknown_key_with_enum_fallback_warns_once_per_key(self, caplog):
        """Unmapped key whose enum has a coarse fallback warns once per seen_keys set."""
        import logging

        seen: set[str] = set()
        caplog.set_level(logging.WARNING, logger="custom_components.unifi_alerts.models")
        UniFiAlert.from_system_log_event(dict(self._BASE_EVENT), seen)
        UniFiAlert.from_system_log_event(dict(self._BASE_EVENT), seen)
        UniFiAlert.from_system_log_event(dict(self._BASE_EVENT), seen)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "UNMAPPED_BUT_HAS_ENUM_FALLBACK" in warnings[0].getMessage()
        assert "coarse fallback" in warnings[0].getMessage()

    def test_unknown_key_with_no_fallback_warns_once_per_key(self, caplog):
        """Unmapped key whose enum is also unknown warns once with the 'event skipped' phrasing."""
        import logging

        seen: set[str] = set()
        caplog.set_level(logging.WARNING, logger="custom_components.unifi_alerts.models")
        event = dict(self._BASE_EVENT, key="FULLY_UNMAPPED", category="UNRECOGNISED_ENUM")
        UniFiAlert.from_system_log_event(event, seen)
        UniFiAlert.from_system_log_event(event, seen)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "FULLY_UNMAPPED" in warnings[0].getMessage()
        assert "event skipped" in warnings[0].getMessage()
        alert = UniFiAlert.from_system_log_event(event, seen)
        assert alert.category == ""

    def test_known_key_does_not_warn(self, caplog):
        """A mapped key produces no observability warning."""
        import logging

        seen: set[str] = set()
        caplog.set_level(logging.WARNING, logger="custom_components.unifi_alerts.models")
        # FIREWALL_BLOCK is in SYSTEM_LOG_KEY_TO_CATEGORY per existing tests above.
        event = dict(self._BASE_EVENT, key="FIREWALL_BLOCK")
        UniFiAlert.from_system_log_event(event, seen)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings == []

    def test_distinct_unknown_keys_each_warn_once(self, caplog):
        """Each new unknown key produces its own warning; the dedupe is per-key, not global."""
        import logging

        seen: set[str] = set()
        caplog.set_level(logging.WARNING, logger="custom_components.unifi_alerts.models")
        UniFiAlert.from_system_log_event(dict(self._BASE_EVENT, key="UNMAPPED_A"), seen)
        UniFiAlert.from_system_log_event(dict(self._BASE_EVENT, key="UNMAPPED_B"), seen)
        UniFiAlert.from_system_log_event(dict(self._BASE_EVENT, key="UNMAPPED_A"), seen)  # repeat
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2
        messages = [r.getMessage() for r in warnings]
        assert any("UNMAPPED_A" in m for m in messages)
        assert any("UNMAPPED_B" in m for m in messages)

    def test_no_seen_keys_warns_every_call(self, caplog):
        """When seen_keys=None, each call warns independently (no dedup)."""
        import logging

        caplog.set_level(logging.WARNING, logger="custom_components.unifi_alerts.models")
        event = dict(self._BASE_EVENT, key="FULLY_UNMAPPED", category="UNRECOGNISED_ENUM")
        UniFiAlert.from_system_log_event(event, None)
        UniFiAlert.from_system_log_event(event, None)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2


class TestAlertSerialization:
    def test_to_dict_serializes_received_at_isoformat(self):
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": "serialized"})
        serialized = alert.to_dict()
        assert serialized["received_at"] == alert.received_at.isoformat()

    def test_from_dict_invalid_received_at_type_falls_back_to_now(self):
        restored = UniFiAlert.from_dict(
            {
                "category": CATEGORY_NETWORK_WAN,
                "message": "bad-ts",
                "received_at": {},
            }
        )
        assert isinstance(restored.received_at, datetime)
        assert restored.received_at.tzinfo == UTC

    def test_to_dict_omits_raw_payload(self):
        """to_dict() must drop `raw` — it carries client MACs / IPs / hostnames that should not hit disk."""
        alert = UniFiAlert.from_webhook_payload(
            CATEGORY_NETWORK_WAN,
            {
                "message": "client connected",
                "client_mac": "aa:bb:cc:dd:ee:ff",
                "client_ip": "192.0.2.10",
                "hostname": "my-laptop",
            },
        )
        serialized = alert.to_dict()
        assert "raw" not in serialized
        # Scalar fields the restore path consumes must still be present.
        for field_name in (
            "category",
            "message",
            "received_at",
            "key",
            "device_name",
            "site",
            "severity",
        ):
            assert field_name in serialized

    def test_to_dict_survives_non_json_value_in_raw(self):
        """A non-JSON-safe value in raw must not be able to break Store.async_save."""
        import json

        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": "test"})
        # Inject a value stdlib json cannot serialise; if `raw` is still in to_dict() this raises.
        alert.raw = {"weird": object()}
        json.dumps(alert.to_dict())

    def test_round_trip_resets_raw_to_empty_dict(self):
        """from_dict(to_dict(alert)) preserves scalar fields and resets raw to {}."""
        original = UniFiAlert(
            category=CATEGORY_SECURITY_THREAT,
            message="intrusion blocked",
            received_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            raw={"client_mac": "aa:bb:cc:dd:ee:ff", "src_ip": "203.0.113.5"},
            key="THREAT_BLOCKED",
            device_name="UDM-Pro",
            site="default",
            severity="HIGH",
        )
        restored = UniFiAlert.from_dict(original.to_dict())
        assert restored.category == original.category
        assert restored.message == original.message
        assert restored.received_at == original.received_at
        assert restored.key == original.key
        assert restored.device_name == original.device_name
        assert restored.site == original.site
        assert restored.severity == original.severity
        assert restored.raw == {}


class TestUnicodeRoundTrip:
    """Non-ASCII text must survive parse -> to_dict -> from_dict without mangling
    and must be truncated at 255 chars by the same byte-count boundary as ASCII."""

    def test_emoji_in_message_survives_round_trip(self):
        """Emoji characters (multi-byte UTF-8) survive serialisation and restore."""
        msg = "WAN down 🔥🚨 check your ISP 💀"
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": msg})
        assert alert.message == msg
        restored = UniFiAlert.from_dict(alert.to_dict())
        assert restored.message == msg

    def test_cjk_characters_survive_round_trip(self):
        """Chinese/Japanese/Korean characters survive serialisation and restore."""
        msg = "网络断开 — 請检查 ISP 连接"
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": msg})
        assert alert.message == msg
        restored = UniFiAlert.from_dict(alert.to_dict())
        assert restored.message == msg

    def test_rtl_text_survives_round_trip(self):
        """Right-to-left Arabic text survives serialisation and restore."""
        msg = "انقطاع الشبكة — تحقق من مزود الإنترنت"
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": msg})
        assert alert.message == msg
        restored = UniFiAlert.from_dict(alert.to_dict())
        assert restored.message == msg

    def test_unicode_message_truncated_at_255_chars(self):
        """A 300-character message is clamped to 255 characters (not bytes)."""
        msg = "あ" * 300
        alert = UniFiAlert.from_webhook_payload(CATEGORY_NETWORK_WAN, {"message": msg})
        assert len(alert.message) == 255
        assert alert.message == "あ" * 255

    def test_mixed_unicode_ascii_round_trip(self):
        """Mixed Unicode and ASCII in all scalar fields survives round-trip."""
        original = UniFiAlert(
            category=CATEGORY_SECURITY_THREAT,
            message="🔥 Threat blocked: 203.0.113.5 → internal host (CVE-2025-99999)",
            received_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            raw={},
            key="THREAT_BLOCKED",
            device_name="UDM-Pro 日本語 テスト",
            site="default",
            severity="HIGH",
        )
        restored = UniFiAlert.from_dict(original.to_dict())
        assert restored.message == original.message
        assert restored.device_name == original.device_name
        assert restored.key == original.key


class TestLargeBatchDeterminism:
    """A large number of alerts must keep counts and watermark filtering exact."""

    def test_500_alerts_applied_to_category_state_count_is_exact(self):
        """Applying 500 alerts to CategoryState must produce alert_count == 500."""
        state = CategoryState(category=CATEGORY_NETWORK_WAN)
        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(500):
            alert = UniFiAlert(
                category=CATEGORY_NETWORK_WAN,
                message=f"alert {i}",
                received_at=base_time + timedelta(seconds=i),
                raw={},
                key="EVT_GW_WANTransition",
                device_name="UDM-Pro",
                site="default",
                severity="critical",
            )
            state.apply_alert(alert)
        assert state.alert_count == 500
        assert state.is_alerting is True
        assert state.last_alert is not None
        assert state.last_alert.message == "alert 499"

    def test_watermark_filter_on_500_alerts_is_deterministic(self):
        """Watermark filtering on 500 alerts must pass exactly the alerts after the mark."""
        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        watermark = base_time + timedelta(seconds=249)
        alerts = [
            UniFiAlert(
                category=CATEGORY_NETWORK_WAN,
                message=f"alert {i}",
                received_at=base_time + timedelta(seconds=i),
                raw={},
                key="EVT_GW_WANTransition",
                device_name="UDM-Pro",
                site="default",
                severity="critical",
            )
            for i in range(500)
        ]
        # Mirrors the coordinator's watermark filter:
        # state.open_count = len([a for a in alerts if a.received_at > watermark])
        counted = [a for a in alerts if a.received_at > watermark]
        # Alerts at seconds 250..499 pass (250 total); 0..249 are at or before the mark.
        assert len(counted) == 250
        assert counted[0].message == "alert 250"
        assert counted[-1].message == "alert 499"

    def test_500_alerts_round_trip_preserves_all_messages(self):
        """500 alerts serialised and restored via to_dict/from_dict keep their messages."""
        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        alerts = [
            UniFiAlert(
                category=CATEGORY_NETWORK_WAN,
                message=f"msg-{i:04d}",
                received_at=base_time + timedelta(seconds=i),
                raw={},
                key="EVT",
                device_name="",
                site="default",
                severity="info",
            )
            for i in range(500)
        ]
        restored = [UniFiAlert.from_dict(a.to_dict()) for a in alerts]
        assert len(restored) == 500
        for i, alert in enumerate(restored):
            assert alert.message == f"msg-{i:04d}"
            assert alert.received_at == base_time + timedelta(seconds=i)
