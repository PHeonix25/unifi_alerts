"""Integration tests for the version-3 to version-4 API-key migration (#278).

Exercises both migration shapes end to end against a real HomeAssistant
instance (UniFiClient HTTP calls are mocked):

- An entry that already carries an API key migrates silently to version 4,
  drops its legacy username/password, and sets up without user action.
- A username/password-only entry migrates to version 4 with its credentials
  removed, lands in the reauth flow with an explanatory repair issue, and is
  restored end to end when a valid API key is supplied. Across the whole
  journey the entry id, unique id, webhook id suffix, and webhook secret are
  preserved, so entities, history, and Alarm Manager URLs survive.

Run only these tests:
    pytest tests/integration/test_apikey_migration.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_SITE,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID_SUFFIX,
    CONF_WEBHOOK_SECRET,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    ISSUE_ID_APIKEY_MIGRATION,
)
from custom_components.unifi_alerts.unifi_auth import InvalidAuthError

from .conftest import HA_TEST_URL

CONTROLLER_URL = "https://192.168.1.1"
WEBHOOK_SECRET = "migration-test-secret"
WEBHOOK_ID_SUFFIX = "abadcafe"


def _make_client_mock() -> MagicMock:
    """Return a mock UniFiClient wired for the coordinator's first refresh."""
    instance = MagicMock()
    instance.authenticate = AsyncMock(return_value=None)
    instance.categorise_alarms = AsyncMock(return_value={})
    instance.probe_system_log_endpoint = AsyncMock(return_value=False)
    instance.close = AsyncMock()
    return instance


def _v3_entry(data: dict) -> MockConfigEntry:
    """Build a version-3 MockConfigEntry with the given data overlaid on a base."""
    base: dict = {
        CONF_CONTROLLER_URL: CONTROLLER_URL,
        CONF_ENABLED_CATEGORIES: list(ALL_CATEGORIES),
        CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
        CONF_VERIFY_SSL: False,
        CONF_WEBHOOK_SECRET: WEBHOOK_SECRET,
        CONF_WEBHOOK_ID_SUFFIX: WEBHOOK_ID_SUFFIX,
        CONF_SITE: "default",
    }
    base.update(data)
    return MockConfigEntry(
        domain=DOMAIN,
        data=base,
        entry_id="migration-test-entry",
        unique_id=CONTROLLER_URL,
        version=3,
    )


async def _prepare_hass(hass) -> None:
    """Give HA a URL and an active webhook view, mirroring the `entry` fixture."""
    await hass.config.async_update(internal_url=HA_TEST_URL)
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()


@pytest.mark.integration
async def test_apikey_entry_migrates_silently_to_v4(hass):
    """A v3 entry with an API key migrates to v4 and sets up with no user action."""
    await _prepare_hass(hass)

    entry = _v3_entry(
        {
            "username": "admin",
            "password": "password",
            CONF_API_KEY: "existing-api-key",
        }
    )
    entry.add_to_hass(hass)

    client = _make_client_mock()
    with patch("custom_components.unifi_alerts.UniFiClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Silently migrated and loaded.
        assert entry.state is ConfigEntryState.LOADED
        assert entry.version == 4
        assert entry.data[CONF_API_KEY] == "existing-api-key"
        assert "auth_method" not in entry.data
        assert "username" not in entry.data
        assert "password" not in entry.data

        # Identity-preserving fields untouched.
        assert entry.entry_id == "migration-test-entry"
        assert entry.unique_id == CONTROLLER_URL
        assert entry.data[CONF_WEBHOOK_ID_SUFFIX] == WEBHOOK_ID_SUFFIX
        assert entry.data[CONF_WEBHOOK_SECRET] == WEBHOOK_SECRET

        # Entities exist for enabled categories.
        ent_reg = er.async_get(hass)
        for cat in ALL_CATEGORIES:
            uid = f"{entry.entry_id}_{cat}_binary"
            assert ent_reg.async_get_entity_id("binary_sensor", DOMAIN, uid) is not None

        # No migration repair issue for the silent path.
        issue_reg = ir.async_get(hass)
        assert (
            issue_reg.async_get_issue(DOMAIN, f"{ISSUE_ID_APIKEY_MIGRATION}_{entry.entry_id}")
            is None
        )

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.integration
async def test_userpass_entry_migrates_and_is_restored_via_reauth(hass):
    """A v3 userpass-only entry migrates to v4, lands in reauth, and is restored by an API key."""
    await _prepare_hass(hass)

    entry = _v3_entry({"username": "admin", "password": "password"})
    entry.add_to_hass(hass)

    client = _make_client_mock()
    # Migration strips the credentials, so the first authenticate fails and
    # setup raises ConfigEntryAuthFailed, which launches the reauth flow.
    client.authenticate = AsyncMock(side_effect=InvalidAuthError("No API key provided"))

    with (
        patch("custom_components.unifi_alerts.UniFiClient", return_value=client),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient", return_value=client),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Migrated to v4 with credentials removed, but not loaded (awaiting reauth).
        assert entry.version == 4
        assert "username" not in entry.data
        assert "password" not in entry.data
        assert CONF_API_KEY not in entry.data
        assert "auth_method" not in entry.data
        assert entry.state is not ConfigEntryState.LOADED

        # The explanatory migration repair issue is raised (not a generic auth failure).
        issue_reg = ir.async_get(hass)
        migration_issue_id = f"{ISSUE_ID_APIKEY_MIGRATION}_{entry.entry_id}"
        assert issue_reg.async_get_issue(DOMAIN, migration_issue_id) is not None

        # A reauth flow is in progress.
        reauth_flows = [
            flow
            for flow in hass.config_entries.flow.async_progress()
            if flow["context"].get("source") == "reauth"
            and flow["context"].get("entry_id") == entry.entry_id
        ]
        assert len(reauth_flows) == 1
        flow_id = reauth_flows[0]["flow_id"]

        # Supplying a valid API key restores the connection.
        client.authenticate = AsyncMock(return_value=None)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_API_KEY: "new-api-key"}
        )
        await hass.async_block_till_done()

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

        # Entry reloaded and now carries the API key.
        assert entry.state is ConfigEntryState.LOADED
        assert entry.data[CONF_API_KEY] == "new-api-key"
        assert "auth_method" not in entry.data

        # Identity-preserving fields survived the whole journey.
        assert entry.entry_id == "migration-test-entry"
        assert entry.unique_id == CONTROLLER_URL
        assert entry.data[CONF_WEBHOOK_ID_SUFFIX] == WEBHOOK_ID_SUFFIX
        assert entry.data[CONF_WEBHOOK_SECRET] == WEBHOOK_SECRET

        # Repair issue cleared on successful reauth.
        assert issue_reg.async_get_issue(DOMAIN, migration_issue_id) is None

        # Entities exist for enabled categories after reload.
        ent_reg = er.async_get(hass)
        for cat in ALL_CATEGORIES:
            uid = f"{entry.entry_id}_{cat}_binary"
            assert ent_reg.async_get_entity_id("binary_sensor", DOMAIN, uid) is not None

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
