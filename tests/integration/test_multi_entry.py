"""Integration tests: two config entries must not cross-contaminate.

These exercise the cluster A fix for the "webhook ID collision on multi-entry"
bug. Without the per-entry ``CONF_WEBHOOK_ID_SUFFIX``, both entries register
webhooks under the same IDs and the second entry silently overwrites the
first's handlers — every webhook POST then dispatches to whichever entry was
loaded last, regardless of which controller fired it.

Scenarios:
- Two entries, two distinct suffixes → two distinct webhook URLs.
- Posting to entry A's URL must update entry A's coordinator only, never B's.

Run only these tests:
    pytest tests/integration/test_multi_entry.py -v
"""

from __future__ import annotations

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_WAN,
    CONF_WEBHOOK_ID_SUFFIX,
    DOMAIN,
    webhook_id_for_category,
)

from .conftest import BASE_CONFIG, HA_TEST_URL, WEBHOOK_SECRET

ENTRY_A_ID = "test-entry-multi-a"
ENTRY_B_ID = "test-entry-multi-b"
SUFFIX_A = "aaaa1111"
SUFFIX_B = "bbbb2222"
TEST_PAYLOAD = {"key": "EVT_GW_WANTransition", "message": "WAN port went offline"}


@pytest.fixture
async def two_entries(hass, mock_unifi_client):
    """Set up two independent UniFi Alerts entries with distinct suffixes."""
    await hass.config.async_update(internal_url=HA_TEST_URL)
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()

    from homeassistant.config_entries import ConfigEntryState

    entry_a = MockConfigEntry(
        domain=DOMAIN,
        data={**BASE_CONFIG, CONF_WEBHOOK_ID_SUFFIX: SUFFIX_A},
        entry_id=ENTRY_A_ID,
        unique_id="https://192.168.1.1",
    )
    entry_a.add_to_hass(hass)
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        data={
            **BASE_CONFIG,
            "controller_url": "https://192.168.2.1",
            CONF_WEBHOOK_ID_SUFFIX: SUFFIX_B,
        },
        entry_id=ENTRY_B_ID,
        unique_id="https://192.168.2.1",
    )
    entry_b.add_to_hass(hass)

    # Setting up the first entry may trigger HA to auto-set-up the second
    # too (the integration platform is now active for the domain). Only call
    # async_setup on entries that aren't already loaded so the test is robust
    # to that ordering quirk.
    for ent in (entry_a, entry_b):
        if ent.state is ConfigEntryState.NOT_LOADED:
            await hass.config_entries.async_setup(ent.entry_id)
    await hass.async_block_till_done()

    yield entry_a, entry_b

    await hass.config_entries.async_unload(entry_a.entry_id)
    await hass.config_entries.async_unload(entry_b.entry_id)
    await hass.async_block_till_done()


@pytest.mark.integration
async def test_two_entries_register_distinct_webhook_urls(hass, two_entries):
    """Each entry's stored webhook URLs must include its own suffix."""
    entry_a, entry_b = two_entries
    urls_a: dict[str, str] = entry_a.runtime_data.webhook_urls
    urls_b: dict[str, str] = entry_b.runtime_data.webhook_urls

    assert SUFFIX_A in urls_a[CATEGORY_NETWORK_WAN]
    assert SUFFIX_B in urls_b[CATEGORY_NETWORK_WAN]
    assert urls_a[CATEGORY_NETWORK_WAN] != urls_b[CATEGORY_NETWORK_WAN]


@pytest.mark.integration
async def test_post_to_entry_a_does_not_affect_entry_b(hass, two_entries, hass_client):
    """A webhook POST to entry A's URL must only update entry A's coordinator.

    Pre-fix, both entries shared webhook IDs and whichever was registered last
    won — POSTing to ``unifi_alerts_network_wan`` would invariably dispatch to
    entry B (the second-registered entry's handler) regardless of intent.
    """
    entry_a, entry_b = two_entries
    coord_a = entry_a.runtime_data.coordinator
    coord_b = entry_b.runtime_data.coordinator
    assert not coord_a.get_category_state(CATEGORY_NETWORK_WAN).is_alerting
    assert not coord_b.get_category_state(CATEGORY_NETWORK_WAN).is_alerting

    webhook_id_a = webhook_id_for_category(CATEGORY_NETWORK_WAN, SUFFIX_A)
    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{webhook_id_a}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 200
    await resp.read()
    await hass.async_block_till_done()

    # Only A flipped — B is untouched.
    assert coord_a.get_category_state(CATEGORY_NETWORK_WAN).is_alerting is True
    assert coord_b.get_category_state(CATEGORY_NETWORK_WAN).is_alerting is False


@pytest.mark.integration
async def test_post_to_entry_b_does_not_affect_entry_a(hass, two_entries, hass_client):
    """The reverse: a POST to entry B's URL must only update entry B."""
    entry_a, entry_b = two_entries
    coord_a = entry_a.runtime_data.coordinator
    coord_b = entry_b.runtime_data.coordinator

    webhook_id_b = webhook_id_for_category(CATEGORY_NETWORK_WAN, SUFFIX_B)
    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{webhook_id_b}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 200
    await resp.read()
    await hass.async_block_till_done()

    assert coord_b.get_category_state(CATEGORY_NETWORK_WAN).is_alerting is True
    assert coord_a.get_category_state(CATEGORY_NETWORK_WAN).is_alerting is False
