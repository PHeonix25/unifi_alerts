"""Integration tests: entry setup creates all expected entities.

Verifies that after async_setup_entry completes:
- Every enabled category has a binary_sensor, sensor (message + count), event,
  and button entity registered and in a sane initial state.
- The rollup binary_sensor and rollup count sensor also exist.
- Disabling a category in options and reloading makes that category's binary
  sensor report as unavailable.

Run only these tests:
    pytest tests/integration/test_lifecycle.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CONF_ENABLED_CATEGORIES,
    CONF_MIN_SEVERITY,
)
from custom_components.unifi_alerts.models import UniFiAlert
from custom_components.unifi_alerts.severity import SEVERITY_HIGH, SEVERITY_LOW

from .conftest import BASE_CONFIG, ENTRY_ID, entity_id_for, get_coordinator


@pytest.mark.integration
async def test_binary_sensors_created_for_all_categories(hass, entry):
    """Every enabled category must have a binary_sensor entity after setup."""
    for cat in ALL_CATEGORIES:
        uid = f"{ENTRY_ID}_{cat}_binary"
        eid = entity_id_for(hass, "binary_sensor", uid)
        assert eid is not None, f"binary_sensor missing for category {cat!r}"
        state = hass.states.get(eid)
        assert state is not None
        assert state.state == "off"


@pytest.mark.integration
async def test_rollup_binary_sensor_created(hass, entry):
    """A rollup binary_sensor must exist and start off."""
    uid = f"{ENTRY_ID}_rollup_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert eid is not None
    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_count_sensors_created_for_all_categories(hass, entry):
    """Every enabled category must have a count sensor starting at 0."""
    for cat in ALL_CATEGORIES:
        uid = f"{ENTRY_ID}_{cat}_count"
        eid = entity_id_for(hass, "sensor", uid)
        assert eid is not None, f"count sensor missing for category {cat!r}"
        state = hass.states.get(eid)
        assert state is not None
        assert state.state == "0"


@pytest.mark.integration
async def test_rollup_count_sensor_created(hass, entry):
    """A rollup count sensor must exist and start at 0."""
    uid = f"{ENTRY_ID}_rollup_count"
    eid = entity_id_for(hass, "sensor", uid)
    assert eid is not None
    assert hass.states.get(eid).state == "0"


@pytest.mark.integration
async def test_clear_buttons_created(hass, entry):
    """Each category and a clear-all button must be registered."""
    for cat in ALL_CATEGORIES:
        uid = f"{ENTRY_ID}_{cat}_clear"
        eid = entity_id_for(hass, "button", uid)
        assert eid is not None, f"clear button missing for category {cat!r}"

    uid = f"{ENTRY_ID}_clear_all"
    eid = entity_id_for(hass, "button", uid)
    assert eid is not None


@pytest.mark.integration
async def test_options_disable_category_makes_sensor_unavailable(hass, entry, mock_unifi_client):
    """Disabling a category via options + reload → that binary sensor is removed."""
    uid = f"{ENTRY_ID}_{CATEGORY_NETWORK_WAN}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"  # starts available

    remaining = [c for c in ALL_CATEGORIES if c != CATEGORY_NETWORK_WAN]
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_CATEGORIES: remaining})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(eid) is None  # entity is pruned, not just unavailable


def _below_threshold_alert(category: str) -> UniFiAlert:
    return UniFiAlert(
        category=category,
        message="below threshold",
        received_at=datetime.now(UTC),
        key="EVT_AP_Disconnected",
        severity=SEVERITY_LOW,
    )


def _at_threshold_alert(category: str) -> UniFiAlert:
    return UniFiAlert(
        category=category,
        message="at threshold",
        received_at=datetime.now(UTC),
        key="EVT_AP_Disconnected",
        severity=SEVERITY_HIGH,
    )


async def _assert_min_severity_gate_behavior(hass, coordinator, category, eid):
    """A below-threshold push is a no-op; an at/above-threshold push is accepted."""
    coordinator.push_alert(category, _below_threshold_alert(category))
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"
    assert coordinator.get_category_state(category).alert_count == 0

    coordinator.push_alert(category, _at_threshold_alert(category))
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "on"
    assert coordinator.get_category_state(category).alert_count == 1


@pytest.mark.integration
async def test_min_severity_survives_reload_and_still_gates_alerts(hass, mock_unifi_client):
    """A non-default per-category min_severity must survive a config-entry
    reload and keep gating alerts identically before and after.

    Full config-entry setup with min_severity=HIGH on network_device. Before
    reload: a below-threshold push is a no-op, an at/above-threshold push is
    accepted. After reload: entry.data still carries the stored setting, and
    both pushes behave identically again on the freshly-created coordinator —
    confirming the setting is read from the reloaded entry, not left over from
    the previous coordinator instance.
    """
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_alerts.const import CONF_WEBHOOK_ID_SUFFIX, DOMAIN

    category = CATEGORY_NETWORK_DEVICE
    min_sev_entry_id = "test-entry-min-severity-lifecycle"
    min_sev_config = {
        **BASE_CONFIG,
        CONF_WEBHOOK_ID_SUFFIX: "minsevlifecycle",
        CONF_MIN_SEVERITY: {category: SEVERITY_HIGH},
    }

    await hass.config.async_update(internal_url="http://homeassistant.test:8123")
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=min_sev_config,
        entry_id=min_sev_entry_id,
        version=3,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    uid = f"{min_sev_entry_id}_{category}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    # Before reload: below-threshold push is a no-op; at/above-threshold push is accepted.
    coordinator = get_coordinator(hass, config_entry)
    await _assert_min_severity_gate_behavior(hass, coordinator, category, eid)

    # Reload the entry — this rebuilds the coordinator from entry.data, exercising
    # the persistence path a config-entry reload takes (options change, secret
    # rotation, HA restart-equivalent), without touching the stored min_severity.
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    # The stored setting itself must still be present on the reloaded entry.
    assert config_entry.data[CONF_MIN_SEVERITY] == {category: SEVERITY_HIGH}

    # After reload: the setting must still gate alerts identically on the
    # freshly-created coordinator.
    reloaded_coordinator = get_coordinator(hass, config_entry)
    reloaded_eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(reloaded_eid).state == "off"
    await _assert_min_severity_gate_behavior(hass, reloaded_coordinator, category, reloaded_eid)

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
