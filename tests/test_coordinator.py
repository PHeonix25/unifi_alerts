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
        hass.async_create_task = MagicMock(return_value=MagicMock())

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
        coord.push_alert(CATEGORY_NETWORK_WAN, make_alert(CATEGORY_NETWORK_WAN, "first"))
        coord.push_alert(CATEGORY_SECURITY_THREAT, make_alert(CATEGORY_SECURITY_THREAT, "second"))
        last = coord.rollup_last_alert
        assert last is not None
        assert last.message == "second"

    def test_rollup_last_alert_none_when_no_alerts(self):
        coord = make_coordinator()
        assert coord.rollup_last_alert is None
