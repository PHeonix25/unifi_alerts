"""Integration tests: webhook secret rotation end-to-end.

Proves the full rotation cycle at the HTTP level:
- Old token accepted before rotation.
- Entry data updated with a new secret and integration reloaded.
- Old token rejected (401) after reload.
- New token accepted (200) after reload.

Run only these tests:
    pytest tests/integration/test_secret_rotation.py -v
"""

from __future__ import annotations

import pytest

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_WAN,
    CONF_WEBHOOK_SECRET,
    webhook_id_for_category,
)

from .conftest import (
    BASE_CONFIG,
    WEBHOOK_ID_SUFFIX,
    WEBHOOK_SECRET,
)

TEST_CATEGORY = CATEGORY_NETWORK_WAN
TEST_WEBHOOK_ID = webhook_id_for_category(TEST_CATEGORY, WEBHOOK_ID_SUFFIX)
TEST_PAYLOAD = {"key": "EVT_GW_WANTransition", "message": "WAN port went offline"}
NEW_SECRET = "rotated-secret-xyz-9876"


@pytest.mark.integration
async def test_old_token_rejected_after_secret_rotation(
    hass, entry, mock_unifi_client, hass_client
):
    """After secret rotation and reload, the old token must be rejected with 401.

    Rotation sequence:
    1. Confirm old token works before rotation.
    2. Update entry.data with a new secret (simulates options flow finish step).
    3. Reload the entry (re-registers webhooks with the new secret).
    4. POST with old token -> 401.
    """
    client = await hass_client()

    # 1. Old token accepted before rotation
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 200
    await resp.read()

    # 2. Rotate the secret in entry.data (mirrors what async_step_finish does)
    new_data = {**BASE_CONFIG, CONF_WEBHOOK_SECRET: NEW_SECRET}
    hass.config_entries.async_update_entry(entry, data=new_data)

    # 3. Reload so WebhookManager re-registers with the new secret
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # 4. Old token must now be rejected
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 401
    await resp.read()


@pytest.mark.integration
async def test_new_token_accepted_after_secret_rotation(
    hass, entry, mock_unifi_client, hass_client
):
    """After secret rotation and reload, the new token must be accepted with 200.

    Rotation sequence:
    1. Update entry.data with a new secret.
    2. Reload the entry.
    3. POST with new token -> 200.
    4. POST with old token -> 401 (cross-check).
    """
    client = await hass_client()

    # 1. Rotate the secret in entry.data
    new_data = {**BASE_CONFIG, CONF_WEBHOOK_SECRET: NEW_SECRET}
    hass.config_entries.async_update_entry(entry, data=new_data)

    # 2. Reload so WebhookManager re-registers with the new secret
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # 3. New token accepted
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={NEW_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 200
    await resp.read()

    # 4. Old token still rejected (cross-check)
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 401
    await resp.read()
