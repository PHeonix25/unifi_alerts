"""Integration tests: webhook HTTP dispatch.

Exercises the full path from an inbound HTTP POST to a binary sensor state
change, using the real HA HTTP server via hass_client.

Scenarios covered:
- Valid POST with correct token  -> binary sensor flips to ON
- POST without ?token=           -> 401, sensor stays OFF
- POST with wrong token          -> 401, sensor stays OFF
- GET to webhook URL             -> handler not called, sensor stays OFF
- No-secret config               -> POST rejected with 500 (fail-closed since v1.7)

Run only these tests:
    pytest tests/integration/test_webhook.py -v
"""

from __future__ import annotations

import pytest

from custom_components.unifi_alerts.const import (
    CATEGORY_NETWORK_DEVICE,
    CATEGORY_NETWORK_WAN,
    CONF_MIN_SEVERITY,
    CONF_WEBHOOK_SECRET,
    WEBHOOK_MAX_BODY_BYTES,
    webhook_id_for_category,
)
from custom_components.unifi_alerts.severity import SEVERITY_HIGH, SEVERITY_LOW

from .conftest import (
    BASE_CONFIG,
    ENTRY_ID,
    WEBHOOK_ID_SUFFIX,
    WEBHOOK_SECRET,
    entity_id_for,
    get_coordinator,
)

# Use network_wan for all webhook tests — a single category is enough to verify routing
TEST_CATEGORY = CATEGORY_NETWORK_WAN
TEST_WEBHOOK_ID = webhook_id_for_category(TEST_CATEGORY, WEBHOOK_ID_SUFFIX)
TEST_PAYLOAD = {"key": "EVT_GW_WANTransition", "message": "WAN port went offline"}


@pytest.mark.integration
async def test_valid_post_flips_binary_sensor(hass, entry, hass_client):
    """POST with the correct ?token= flips the matching binary sensor to ON."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 200
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "on"


@pytest.mark.integration
async def test_valid_post_with_authorization_header_flips_binary_sensor(hass, entry, hass_client):
    """POST with Authorization: Bearer <secret> (#176 preferred form) and no
    ?token= flips the matching binary sensor to ON."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}",
        json=TEST_PAYLOAD,
        headers={"Authorization": f"Bearer {WEBHOOK_SECRET}"},
    )
    assert resp.status == 200
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "on"


@pytest.mark.integration
async def test_wrong_authorization_header_and_no_query_returns_401(hass, entry, hass_client):
    """A wrong Authorization header with no ?token= must return 401."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}",
        json=TEST_PAYLOAD,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status == 401
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_valid_post_also_flips_rollup_sensor(hass, entry, hass_client):
    """A successful webhook POST should also flip the rollup binary sensor to ON."""
    rollup_eid = entity_id_for(hass, "binary_sensor", f"{ENTRY_ID}_rollup_binary")
    assert hass.states.get(rollup_eid).state == "off"

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(rollup_eid).state == "on"


@pytest.mark.integration
async def test_missing_token_returns_401_and_sensor_stays_off(hass, entry, hass_client):
    """POST without ?token= must return 401 and leave the sensor OFF."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}",  # no token
        json=TEST_PAYLOAD,
    )
    assert resp.status == 401
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_wrong_token_returns_401_and_sensor_stays_off(hass, entry, hass_client):
    """POST with a wrong token must return 401 and leave the sensor OFF."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token=WRONG-TOKEN",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 401
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_get_request_does_not_dispatch_alert(hass, entry, hass_client):
    """GET to a webhook URL must not trigger an alert (health-check pattern)."""
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)

    client = await hass_client()
    # HA rejects non-POST methods for webhooks registered with allowed_methods=["POST"]
    resp = await client.get(f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}")
    await resp.read()
    await hass.async_block_till_done()

    # Regardless of HTTP status, the coordinator must not have dispatched an alert
    coordinator = get_coordinator(hass, entry)
    assert not coordinator.get_category_state(TEST_CATEGORY).is_alerting
    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_oversized_body_returns_413_and_sensor_stays_off(hass, entry, hass_client):
    """A body larger than WEBHOOK_MAX_BODY_BYTES must be rejected with HTTP 413.

    Unit coverage in test_webhook_handler.py exercises this against a mocked
    request; this integration test proves the same contract holds over the
    real HA HTTP server (Issue #381).
    """
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    client = await hass_client()
    oversized_body = b"x" * (WEBHOOK_MAX_BODY_BYTES + 1)
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        data=oversized_body,
    )
    assert resp.status == 413
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_malformed_json_returns_400_and_sensor_stays_off(hass, entry, hass_client):
    """A body that fails JSON parsing must be rejected with HTTP 400.

    Unit coverage in test_webhook_handler.py exercises this against a mocked
    request; this integration test proves the same contract holds over the
    real HA HTTP server (Issue #381).
    """
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        data=b"not valid json {{",
    )
    assert resp.status == 400
    await resp.read()
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "off"


@pytest.mark.integration
async def test_webhook_arrives_after_coordinator_shutdown_before_unregister(
    hass, entry, hass_client
):
    """A webhook landing in the unload window between coordinator.async_shutdown()
    and WebhookManager.unregister_all() must be handled gracefully.

    custom_components/unifi_alerts/__init__.py's async_unload_entry calls
    coordinator.async_shutdown() (cancels pending auto-clear tasks) *before*
    runtime_data.unregister_webhooks() (tears down the HTTP route) — so this
    window is real in production, not synthetic (Issue #382). We reproduce it
    deterministically by driving the two steps directly in that order rather
    than racing real concurrency, which would be non-deterministic in a test.
    coordinator.async_shutdown() has no "dead" flag, so push_alert still runs
    normally; the entry's own teardown (which unloads again) cancels the
    fresh auto-clear task this webhook schedules, so nothing leaks past this
    test.
    """
    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    coordinator = get_coordinator(hass, entry)

    # Step 1 of the unload sequence: cancel pending auto-clear tasks.
    await coordinator.async_shutdown()

    # Step 2 (unregister_webhooks) has not run yet - the route is still live.
    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
        json=TEST_PAYLOAD,
    )
    assert resp.status == 200
    await resp.read()
    await hass.async_block_till_done()

    # Coordinator state must still update correctly despite shutdown having run.
    state = coordinator.get_category_state(TEST_CATEGORY)
    assert state.is_alerting is True
    assert state.alert_count == 1
    assert hass.states.get(eid).state == "on"


@pytest.mark.integration
async def test_post_after_unload_does_not_dispatch_and_entity_is_gone(
    hass, entry, hass_client, caplog
):
    """A webhook POST after the entry is unloaded must not reach our handler.

    Regression guard for #265's setup-failure cleanup mechanism (which
    unregisters webhooks via the same `unregister_all()` path unload uses):
    without unregistration, a stale webhook_id would stay routable and its
    handler closure would still be bound to a coordinator that no longer
    exists in any live entry.

    HA's real webhook dispatch (`async_handle_webhook`) deliberately returns
    HTTP 200 for both a genuinely-processed webhook AND an unregistered one
    ("Always respond successfully to not give away if a hook exists or not"),
    so the HTTP status alone cannot prove the unload worked — a naive
    `assert resp.status == 404` would be asserting behaviour HA does not
    have. Instead assert on what unload actually changes: HA logs the
    unregistered-webhook path, and the category's entity goes `unavailable`
    (confirmed empirically — unload does not remove the state machine entry
    outright, it marks it unavailable), so there is nothing live that could
    have reflected a dispatched alert.
    """
    import logging

    from homeassistant.const import STATE_UNAVAILABLE

    uid = f"{ENTRY_ID}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state != STATE_UNAVAILABLE  # sanity: live before unload

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()
    with caplog.at_level(logging.INFO, logger="homeassistant.components.webhook"):
        resp = await client.post(
            f"/api/webhook/{TEST_WEBHOOK_ID}?token={WEBHOOK_SECRET}",
            json=TEST_PAYLOAD,
        )
        await resp.read()
        await hass.async_block_till_done()

    assert resp.status == 200  # HA always responds 200, registered or not — see docstring
    assert "unregistered webhook" in caplog.text.lower()
    assert hass.states.get(eid).state == STATE_UNAVAILABLE  # nothing live could have flipped


async def _setup_min_severity_entry(hass, category, min_sev_suffix):
    """Set up a config entry with min_severity=HIGH on the given category."""
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_alerts.const import CONF_WEBHOOK_ID_SUFFIX, DOMAIN

    await hass.config.async_update(internal_url="http://homeassistant.test:8123")
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()

    min_sev_config = {
        **BASE_CONFIG,
        CONF_WEBHOOK_ID_SUFFIX: min_sev_suffix,
        CONF_MIN_SEVERITY: {category: SEVERITY_HIGH},
    }
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=min_sev_config,
        entry_id="test-entry-min-severity",
        version=3,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _post_webhook(hass_client, webhook_id, payload):
    client = await hass_client()
    resp = await client.post(
        f"/api/webhook/{webhook_id}?token={WEBHOOK_SECRET}",
        json=payload,
    )
    assert resp.status == 200
    await resp.read()
    return resp


@pytest.mark.integration
async def test_below_threshold_push_then_at_or_above_threshold_push(
    hass, mock_unifi_client, hass_client
):
    """A below-threshold push is a true no-op except for the webhook health
    signal; a subsequent at/above-threshold push is accepted exactly as
    before this feature existed.

    Full config-entry setup with a non-default ``min_severity`` for one
    category (network_device -> HIGH), exercised end to end via the real
    HTTP webhook path.
    """
    category = CATEGORY_NETWORK_DEVICE
    min_sev_suffix = "minsev"
    config_entry = await _setup_min_severity_entry(hass, category, min_sev_suffix)

    uid = f"{config_entry.entry_id}_{category}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)
    assert hass.states.get(eid).state == "off"

    coordinator = get_coordinator(hass, config_entry)
    webhook_id = webhook_id_for_category(category, min_sev_suffix)

    # Below-threshold push (LOW < HIGH): must not flip the sensor, must not
    # touch alert_count/open_count/last_alert, but must still advance the
    # webhook health signal (last_webhook_at).
    below_payload = {
        "key": "EVT_AP_Disconnected",
        "message": "AP offline (low severity)",
        "severity": SEVERITY_LOW,
    }
    await _post_webhook(hass_client, webhook_id, below_payload)
    await hass.async_block_till_done()

    state = coordinator.get_category_state(category)
    assert hass.states.get(eid).state == "off"
    assert state.alert_count == 0
    assert state.open_count == 0
    assert state.last_alert is None
    assert state.last_webhook_at is not None

    # At/above-threshold push (HIGH >= HIGH): accepted exactly as before
    # this feature existed — sensor flips on, counts increment.
    above_payload = {
        "key": "EVT_AP_Disconnected",
        "message": "AP offline (high severity)",
        "severity": SEVERITY_HIGH,
    }
    await _post_webhook(hass_client, webhook_id, above_payload)
    await hass.async_block_till_done()

    assert hass.states.get(eid).state == "on"
    assert state.alert_count == 1
    assert state.open_count == 1
    assert state.last_alert is not None
    assert state.last_alert.message == "AP offline (high severity)"

    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.integration
async def test_no_secret_config_rejects_post_with_500(hass, mock_unifi_client, hass_client):
    """When CONF_WEBHOOK_SECRET is empty, any POST is rejected with HTTP 500.

    Pre-v1.7 an empty secret bypassed the token check entirely and accepted
    all requests silently. The VERSION 3 migration backfills a secret for every
    entry that lacks one, so an empty secret in production means something went
    wrong. The handler now fails closed rather than silently accepting requests.
    """
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.unifi_alerts.const import CONF_WEBHOOK_ID_SUFFIX, DOMAIN

    # Set up HTTP and webhook infrastructure (normally done by the entry fixture)
    await hass.config.async_update(internal_url="http://homeassistant.test:8123")
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()

    no_secret_suffix = "nosecret"
    no_secret_config = {
        **BASE_CONFIG,
        CONF_WEBHOOK_SECRET: "",
        CONF_WEBHOOK_ID_SUFFIX: no_secret_suffix,
    }
    no_secret_entry_id = "test-entry-no-secret"

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=no_secret_config,
        entry_id=no_secret_entry_id,
        version=3,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    uid = f"{no_secret_entry_id}_{TEST_CATEGORY}_binary"
    eid = entity_id_for(hass, "binary_sensor", uid)

    client = await hass_client()
    webhook_id = webhook_id_for_category(TEST_CATEGORY, no_secret_suffix)
    resp = await client.post(
        f"/api/webhook/{webhook_id}",  # no token, empty secret configured
        json=TEST_PAYLOAD,
    )
    # Handler must fail closed — HTTP 500 when no secret is configured
    assert resp.status == 500
    await resp.read()
    await hass.async_block_till_done()

    # Sensor must stay off because the POST was rejected
    assert hass.states.get(eid).state == "off"

    # Unload the entry to cancel any auto-clear tasks and prevent lingering state
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
