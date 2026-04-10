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

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CONF_ENABLED_CATEGORIES,
)

from .conftest import ENTRY_ID, entity_id_for


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
    """Disabling a category via options + reload → that binary sensor is unavailable."""
    uid = f"{ENTRY_ID}_{CATEGORY_NETWORK_WAN}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"  # starts available

    remaining = [c for c in ALL_CATEGORIES if c != CATEGORY_NETWORK_WAN]
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_CATEGORIES: remaining})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "unavailable"
