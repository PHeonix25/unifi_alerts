"""Shared fixtures for integration tests.

These tests use a real HomeAssistant instance via the ``hass`` fixture from
pytest_homeassistant_custom_component.  All UniFiClient HTTP calls are still
mocked — integration tests exercise the HA lifecycle (entity creation, webhook
routing, coordinator state, options reload) without hitting a real controller.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_SITE,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
    DATA_COORDINATOR,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

# ── Session-level pycares warmup ─────────────────────────────────────────────
# aiohttp's TCPConnector uses aiodns → pycares, which starts a process-level
# daemon thread named "Thread-1 (_run_safe_shutdown_loop)" on first use.
# Without this fixture, that thread starts during the first test (when the
# entry fixture sets up the webhook HTTP server), AFTER verify_cleanup from
# pytest_homeassistant_custom_component has already captured its "threads
# before" snapshot — causing a spurious teardown ERROR on the first test only.
# Calling pycares._shutdown_manager.start() here at session scope ensures
# Thread-1 is alive before any test's verify_cleanup snapshot is taken.


@pytest.fixture(autouse=True, scope="session")
def _prime_pycares_shutdown_thread() -> None:
    """Pre-start the pycares shutdown thread so verify_cleanup does not flag it."""
    import pycares  # noqa: PLC0415

    pycares._shutdown_manager.start()


# ── Constants shared across integration tests ─────────────────────────────────

ENTRY_ID = "test-entry-integration"
WEBHOOK_SECRET = "integration-test-secret"
HA_TEST_URL = "http://homeassistant.test:8123"

BASE_CONFIG: dict = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    "username": "admin",
    "password": "password",
    CONF_ENABLED_CATEGORIES: list(ALL_CATEGORIES),
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
    CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
    CONF_VERIFY_SSL: False,
    CONF_WEBHOOK_SECRET: WEBHOOK_SECRET,
    "auth_method": "userpass",
    CONF_SITE: "default",
}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations from custom_components/ for every test."""
    return enable_custom_integrations


@pytest.fixture
def mock_unifi_client():
    """Patch UniFiClient at the __init__.py import point.

    Integration tests call async_setup_entry which instantiates UniFiClient
    directly.  We patch the name as it appears in the integration's __init__
    module so the real constructor is never reached.
    """
    with patch("custom_components.unifi_alerts.UniFiClient") as mock_cls:
        instance = MagicMock()
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.categorise_alarms = AsyncMock(return_value={})
        instance.close = AsyncMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
async def entry(hass, mock_unifi_client):
    """Set up the integration and return the live MockConfigEntry.

    Configures a test internal URL so async_generate_url succeeds, sets up
    the webhook component so HTTP routing is active, then runs async_setup_entry.

    The entry is unloaded on teardown so auto-clear tasks don't linger.
    """
    # Give the test HA instance a URL so async_generate_url doesn't raise
    await hass.config.async_update(internal_url=HA_TEST_URL)

    # Ensure the webhook HTTP view is registered before our integration
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=dict(BASE_CONFIG),
        entry_id=ENTRY_ID,
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    yield config_entry

    # Unload entry on teardown — this calls coordinator.async_shutdown() which
    # cancels any pending auto-clear asyncio tasks and prevents lingering-task
    # failures in the pytest-homeassistant-custom-component verify_cleanup hook.
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()


# ── Helpers ───────────────────────────────────────────────────────────────────


def get_coordinator(hass, config_entry):
    """Return the live coordinator from hass.data."""
    return hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]


def entity_id_for(hass, platform: str, unique_id: str) -> str | None:
    """Resolve an entity_id from a platform name and unique_id."""
    from homeassistant.helpers import entity_registry as er

    ent_reg = er.async_get(hass)
    return ent_reg.async_get_entity_id(platform, DOMAIN, unique_id)
