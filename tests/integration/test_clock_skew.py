"""Integration tests: controller/HA clock skew, end to end (#387).

``tests/unit/coordinator/test_clock_skew.py`` covers the watermark logic in
isolation. These tests run the same scenarios through a real HomeAssistant
instance and assert on what a user sees: entity states and attributes.

Scenarios covered:
- A webhook payload carrying a far-future ``timestamp`` is accepted, and the
  alert is stamped with HA's clock (there is no controller timestamp in the
  Alarm Manager payload, see docs/UNIFI.md "Clock assumption").
- An alert dated one hour in the future (a fast controller clock) turns the
  sensors on and is displayed as a UTC-aware ISO timestamp.
- Past, present and future alerts are all accepted; the newest time is tracked.
- After Clear, the watermark is anchored to the future-dated alert: polled
  alarms at or before it are not re-counted, a later one is.

Run only these tests:
    pytest tests/integration/test_clock_skew.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.unifi_alerts.const import CATEGORY_NETWORK_WAN, webhook_id_for_category
from custom_components.unifi_alerts.models import UniFiAlert

from .conftest import ENTRY_ID, WEBHOOK_ID_SUFFIX, WEBHOOK_SECRET, entity_id_for, get_coordinator

TEST_CATEGORY = CATEGORY_NETWORK_WAN
TEST_WEBHOOK_ID = webhook_id_for_category(TEST_CATEGORY, WEBHOOK_ID_SUFFIX)


def _alert(received_at: datetime, key: str = "EVT_GW_WANTransition") -> UniFiAlert:
    """Build a WAN alert with an explicit receipt time."""
    return UniFiAlert(
        category=TEST_CATEGORY,
        key=key,
        message=f"WAN event at {received_at.isoformat()}",
        device_name="UDM-Pro",
        site="default",
        received_at=received_at,
    )


def _eid(hass, platform: str, suffix: str) -> str:
    """Resolve the entity_id for a WAN-category (or rollup) entity."""
    eid = entity_id_for(hass, platform, f"{ENTRY_ID}_{suffix}")
    assert eid is not None, f"{platform} {suffix} not registered"
    return eid


@pytest.mark.integration
async def test_webhook_payload_timestamp_is_ignored_and_alert_stamped_by_ha(
    hass, entry, hass_client
):
    """A webhook with a timestamp one hour ahead is accepted and stamped with HA's own clock."""
    future_ms = int((datetime.now(UTC) + timedelta(hours=1)).timestamp() * 1000)
    binary = _eid(hass, "binary_sensor", f"{TEST_CATEGORY}_binary")
    message = _eid(hass, "sensor", f"{TEST_CATEGORY}_message")

    before = datetime.now(UTC)
    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json={"key": "EVT_GW_WANTransition", "message": "future-dated", "timestamp": future_ms},
    )
    assert resp.status == 200
    await resp.read()
    await hass.async_block_till_done()
    after = datetime.now(UTC)

    assert hass.states.get(binary).state == "on"
    received_at = datetime.fromisoformat(hass.states.get(message).attributes["received_at"])
    assert received_at.tzinfo is not None
    assert before <= received_at <= after


@pytest.mark.integration
async def test_future_dated_alert_is_accepted_and_displayed_as_utc_iso(hass, entry):
    """An alert received_at one hour ahead turns every related entity on with that exact time."""
    future = datetime.now(UTC) + timedelta(hours=1)
    coordinator = get_coordinator(hass, entry)

    coordinator.push_alert(TEST_CATEGORY, _alert(future))
    await hass.async_block_till_done()

    binary = hass.states.get(_eid(hass, "binary_sensor", f"{TEST_CATEGORY}_binary"))
    rollup = hass.states.get(_eid(hass, "binary_sensor", "rollup_binary"))
    message = hass.states.get(_eid(hass, "sensor", f"{TEST_CATEGORY}_message"))
    count = hass.states.get(_eid(hass, "sensor", f"{TEST_CATEGORY}_count"))
    assert binary.state == "on"
    assert rollup.state == "on"
    assert count.state == "1"
    # Displayed in UTC with an explicit offset, regardless of the HA display timezone.
    assert message.attributes["received_at"] == future.isoformat()
    assert message.attributes["received_at"].endswith("+00:00")
    assert binary.attributes["last_alert_at"] == future.isoformat()
    assert rollup.attributes["last_alert_at"] == future.isoformat()


@pytest.mark.integration
async def test_past_present_and_future_alerts_are_all_accepted(hass, entry):
    """Alerts dated in the past, now and the future each count; the newest time is tracked."""
    now = datetime.now(UTC)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)
    coordinator = get_coordinator(hass, entry)

    # Distinct keys so webhook dedup does not collapse them.
    coordinator.push_alert(TEST_CATEGORY, _alert(future, key="EVT_FUTURE"))
    coordinator.push_alert(TEST_CATEGORY, _alert(now, key="EVT_PRESENT"))
    coordinator.push_alert(TEST_CATEGORY, _alert(past, key="EVT_PAST"))
    await hass.async_block_till_done()

    rollup_count = hass.states.get(_eid(hass, "sensor", "rollup_count"))
    assert rollup_count.attributes["total_webhook_count"] == 3
    assert hass.states.get(_eid(hass, "sensor", f"{TEST_CATEGORY}_count")).state == "3"
    # Arrival order was future, present, past: the late, older alert must not pull the
    # newest-seen time (the Clear watermark source) backwards.
    state = coordinator.get_category_state(TEST_CATEGORY)
    assert state.last_alarm_received_at == future


@pytest.mark.integration
async def test_clear_after_future_alert_anchors_watermark_for_later_polls(
    hass, entry, mock_unifi_client
):
    """Pressing Clear after a future-dated alert makes polling ignore alarms up to that time."""
    future = datetime.now(UTC) + timedelta(hours=1)
    coordinator = get_coordinator(hass, entry)
    coordinator.push_alert(TEST_CATEGORY, _alert(future))
    await hass.async_block_till_done()

    clear_button = _eid(hass, "button", f"{TEST_CATEGORY}_clear")
    await hass.services.async_call("button", "press", {"entity_id": clear_button}, blocking=True)
    await hass.async_block_till_done()

    binary = _eid(hass, "binary_sensor", f"{TEST_CATEGORY}_binary")
    count = _eid(hass, "sensor", f"{TEST_CATEGORY}_count")
    assert hass.states.get(binary).state == "off"
    assert coordinator.get_category_state(TEST_CATEGORY).last_cleared_at == future

    # The controller re-reports older alarms plus the already-acknowledged one: none count.
    older = [
        _alert(future - timedelta(hours=2), key="EVT_OLD"),
        _alert(future, key="EVT_ACKED"),
    ]
    mock_unifi_client.categorise_alarms.return_value = {TEST_CATEGORY: older}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(count).state == "0"
    assert hass.states.get(binary).state == "off"

    # An alarm strictly newer than the watermark is counted and re-asserts the sensor.
    newer = _alert(future + timedelta(minutes=1), key="EVT_NEW")
    mock_unifi_client.categorise_alarms.return_value = {TEST_CATEGORY: [*older, newer]}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(count).state == "1"
    assert hass.states.get(binary).state == "on"
