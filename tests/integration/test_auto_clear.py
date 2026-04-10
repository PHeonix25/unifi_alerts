"""Integration tests: auto-clear timeout resets binary sensor to OFF.

The coordinator schedules an asyncio.sleep task after each alert.  We patch
asyncio.sleep to a no-op so the task completes on the first
``async_block_till_done`` call and the sensor state is verifiably reset.

Run only these tests:
    pytest tests/integration/test_auto_clear.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.unifi_alerts.const import CATEGORY_NETWORK_WAN
from custom_components.unifi_alerts.models import UniFiAlert

from .conftest import ENTRY_ID, entity_id_for, get_coordinator

TEST_CATEGORY = CATEGORY_NETWORK_WAN


def _make_alert(category: str = TEST_CATEGORY) -> UniFiAlert:
    return UniFiAlert(
        category=category,
        key="EVT_GW_WANTransition",
        message="WAN went offline",
        device_name="UDM-Pro",
        site="default",
        received_at=datetime.now(UTC),
    )


@pytest.mark.integration
async def test_push_alert_sets_sensor_on(hass, entry):
    """Pushing an alert via the coordinator sets the binary sensor to ON."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    coordinator = get_coordinator(hass, entry)

    coordinator.push_alert(TEST_CATEGORY, _make_alert())
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "on"


@pytest.mark.integration
async def test_auto_clear_resets_sensor_to_off(hass, entry):
    """After the auto-clear delay elapses the binary sensor must return to OFF.

    asyncio.sleep is patched to a coroutine that returns immediately so the
    auto-clear task completes during async_block_till_done.
    """
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    coordinator = get_coordinator(hass, entry)

    with patch(
        "custom_components.unifi_alerts.coordinator.asyncio.sleep",
        new=AsyncMock(),
    ):
        coordinator.push_alert(TEST_CATEGORY, _make_alert())
        # block_till_done runs the auto-clear task to completion while the
        # sleep mock is still active
        await hass.async_block_till_done()

    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_auto_clear_also_resets_rollup_sensor(hass, entry):
    """After auto-clear the rollup binary sensor should also return to OFF."""
    rollup_eid = entity_id_for(hass, "binary_sensor", f"{ENTRY_ID}_rollup_binary")
    coordinator = get_coordinator(hass, entry)

    with patch(
        "custom_components.unifi_alerts.coordinator.asyncio.sleep",
        new=AsyncMock(),
    ):
        coordinator.push_alert(TEST_CATEGORY, _make_alert())
        await hass.async_block_till_done()

    assert hass.states.get(rollup_eid).state == "off"


@pytest.mark.integration
async def test_push_without_auto_clear_keeps_sensor_on(hass, entry):
    """Without the auto-clear firing, the sensor remains ON between block_till_done calls."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    coordinator = get_coordinator(hass, entry)

    # Push alert without mocking sleep — the real sleep won't expire in test time
    coordinator.push_alert(TEST_CATEGORY, _make_alert())
    await hass.async_block_till_done()

    # Sensor should still be ON because the auto-clear timer hasn't fired
    assert hass.states.get(eid).state == "on"

    # Clean up the pending clear task so the test environment stays tidy
    coordinator.cancel_clear(TEST_CATEGORY)
