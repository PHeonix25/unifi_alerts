"""Integration tests for the SSDP discovery flow against a real HomeAssistant instance.

The unit tests in ``tests/unit/config_flow/test_discovery.py`` call
``async_step_ssdp`` directly on a flow object with a mocked ``hass`` and
stubbed unique-id helpers. Those stubs hide everything Home Assistant's real
flow manager contributes, so this module drives the genuine
``hass.config_entries.flow`` machinery instead (UniFiClient HTTP calls are
still mocked):

- A discovery payload walks the whole flow, SSDP > user > categories > finish,
  and ends in a created config entry.
- The pre-filled controller URL is a real form default: submitting only the API
  key accepts it, and submitting a different URL overrides it.
- Validation failures (bad API key, unreachable host, untrusted certificate,
  missing alarm endpoint) re-show the user form with the right error and the
  user can recover on retry.
- Concurrent discoveries are independent per host, and a repeat discovery of a
  host that already has a flow in progress or a configured entry is aborted by
  Home Assistant's real unique-id handling.

Run only these tests:
    pytest tests/integration/test_discovery_flow.py -v
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_SSDP, SOURCE_USER, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info import ssdp
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_DEVICE_SERIAL,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_SITE,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID_SUFFIX,
    CONF_WEBHOOK_SECRET,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SITE,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from custom_components.unifi_alerts.unifi_auth import InvalidAuthError
from custom_components.unifi_alerts.unifi_client import (
    AlarmEndpointUnavailableError,
    CannotConnectError,
    SslCertificateError,
)

from .conftest import HA_TEST_URL

HOST_A = "192.168.1.1"
HOST_B = "192.168.1.2"
URL_A = f"https://{HOST_A}"
URL_B = f"https://{HOST_B}"
SERIAL_A = "aa:bb:cc:dd:ee:ff"
SERIAL_B = "11:22:33:44:55:66"
API_KEY = "discovered-api-key"


def _ssdp_info(host: str = HOST_A, serial: str | None = SERIAL_A) -> ssdp.SsdpServiceInfo:
    """Build the SSDP payload a UniFi Dream Machine Pro announces at `host`."""
    upnp = {
        ssdp.ATTR_UPNP_MANUFACTURER: "Ubiquiti Networks",
        ssdp.ATTR_UPNP_MODEL_DESCRIPTION: "UniFi Dream Machine Pro",
    }
    if serial is not None:
        upnp[ssdp.ATTR_UPNP_SERIAL] = serial
    return ssdp.SsdpServiceInfo(
        ssdp_usn=f"uuid:{host}-usn",
        ssdp_st="urn:schemas-upnp-org:device:InternetGatewayDevice:1",
        ssdp_location=f"http://{host}:1900/description.xml",
        upnp=upnp,
    )


def _make_client_mock() -> MagicMock:
    """Return a UniFiClient mock that passes both setup validation and the first refresh."""
    instance = MagicMock()
    instance.authenticate = AsyncMock(return_value=None)
    instance.validate_connectivity = AsyncMock(return_value="v2")
    instance.categorise_alarms = AsyncMock(return_value={})
    instance.probe_system_log_endpoint = AsyncMock(return_value=False)
    instance.legacy_alarm_endpoint_confirmed_unavailable = MagicMock(return_value=False)
    instance.fetch_controller_version = AsyncMock(return_value=None)
    instance.close = AsyncMock()
    return instance


@contextmanager
def _patched_client(client: MagicMock) -> Iterator[MagicMock]:
    """Patch UniFiClient in both the config flow (validation) and __init__ (entry setup)."""
    with (
        patch("custom_components.unifi_alerts.config_flow.UniFiClient", return_value=client),
        patch("custom_components.unifi_alerts.UniFiClient", return_value=client),
    ):
        yield client


async def _prepare_hass(hass) -> None:
    """Give HA a URL and an active webhook view so the finish step and entry setup work."""
    await hass.config.async_update(internal_url=HA_TEST_URL)
    await async_setup_component(hass, "webhook", {})
    await hass.async_block_till_done()


async def _discover(hass, host: str = HOST_A, serial: str | None = SERIAL_A) -> dict[str, Any]:
    """Start a flow exactly as Home Assistant's ssdp component does for a matched device."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_SSDP}, data=_ssdp_info(host, serial)
    )


def _form_default(result: dict[str, Any], key: str) -> Any:
    """Return the default Home Assistant would apply for `key` in a form's schema."""
    for marker in result["data_schema"].schema:
        if marker.schema == key:
            default = marker.default
            return default() if callable(default) else default
    raise AssertionError(f"{key!r} not in schema")


async def _finish_setup(hass, flow_id: str) -> dict[str, Any]:
    """Drive a flow sitting on the categories step through to entry creation."""
    result = await hass.config_entries.flow.async_configure(
        flow_id, {f"cat_{cat}": True for cat in ALL_CATEGORIES}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "finish"
    return await hass.config_entries.flow.async_configure(flow_id, {})


@pytest.fixture
async def prepared_hass(hass):
    """A HomeAssistant instance ready to run the config flow end to end."""
    await _prepare_hass(hass)
    return hass


async def _unload_all(hass) -> None:
    """Unload every loaded entry so no coordinator tasks outlive the test."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.integration
async def test_ssdp_discovery_runs_to_a_created_entry(prepared_hass):
    """A valid SSDP payload walks user, categories and finish and creates a loaded entry."""
    hass = prepared_hass
    with _patched_client(_make_client_mock()):
        result = await _discover(hass)

        # Step 1: the user form, titled with the discovered host.
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert not result["errors"]
        in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert len(in_progress) == 1
        assert in_progress[0]["context"]["source"] == SOURCE_SSDP
        assert in_progress[0]["context"]["unique_id"] == URL_A
        assert in_progress[0]["context"]["title_placeholders"] == {"name": HOST_A}

        # Step 2: credentials accepted, on to category selection.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: API_KEY}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "categories"

        # Steps 3 and 4: categories chosen, webhook URLs acknowledged, entry created.
        result = await _finish_setup(hass, result["flow_id"])
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == f"UniFi Alerts ({URL_A})"
        data = result["data"]
        assert data[CONF_CONTROLLER_URL] == URL_A
        assert data[CONF_API_KEY] == API_KEY
        assert data[CONF_VERIFY_SSL] is DEFAULT_VERIFY_SSL
        assert data[CONF_DEVICE_SERIAL] == SERIAL_A
        assert data[CONF_ENABLED_CATEGORIES] == list(ALL_CATEGORIES)
        assert data[CONF_POLL_INTERVAL] == DEFAULT_POLL_INTERVAL
        assert data[CONF_CLEAR_TIMEOUT] == DEFAULT_CLEAR_TIMEOUT
        assert data[CONF_SITE] == DEFAULT_SITE
        assert data[CONF_WEBHOOK_SECRET]
        assert len(data[CONF_WEBHOOK_ID_SUFFIX]) == 8

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == URL_A
        assert entry.state is ConfigEntryState.LOADED
        assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)

        await _unload_all(hass)


@pytest.mark.integration
async def test_discovered_url_is_the_form_default_and_accepted_as_is(prepared_hass):
    """The user form pre-fills the discovered URL and submitting only the API key accepts it.

    Home Assistant validates `user_input` against the form schema and applies
    its defaults, so omitting the URL is exactly what a user who leaves the
    pre-filled field alone sends.
    """
    hass = prepared_hass
    client = _make_client_mock()
    with _patched_client(client):
        result = await _discover(hass)

        assert _form_default(result, CONF_CONTROLLER_URL) == URL_A
        assert _form_default(result, CONF_VERIFY_SSL) is DEFAULT_VERIFY_SSL

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: API_KEY}
        )
        assert result["step_id"] == "categories"

        # The pre-filled URL (not the example placeholder) was what got validated.
        client.authenticate.assert_awaited_once()
        client.validate_connectivity.assert_awaited_once()

        result = await _finish_setup(hass, result["flow_id"])
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_CONTROLLER_URL] == URL_A
        await _unload_all(hass)


@pytest.mark.integration
async def test_user_can_override_the_discovered_host(prepared_hass):
    """Typing a different URL over the pre-filled one configures that URL instead.

    The entry is keyed on the URL the user submitted, not the discovered one.
    The UPnP serial captured at discovery is still stored: the flow carries it
    over regardless of which URL is submitted, so a rediscovery of the original
    console would later match this entry by serial.
    """
    hass = prepared_hass
    with _patched_client(_make_client_mock()):
        result = await _discover(hass, HOST_A)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONTROLLER_URL: "https://unifi.example.test", CONF_API_KEY: API_KEY},
        )
        assert result["step_id"] == "categories"

        result = await _finish_setup(hass, result["flow_id"])
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "UniFi Alerts (https://unifi.example.test)"
        assert result["data"][CONF_CONTROLLER_URL] == "https://unifi.example.test"
        assert result["data"][CONF_DEVICE_SERIAL] == SERIAL_A
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == "https://unifi.example.test"
        await _unload_all(hass)


@pytest.mark.integration
async def test_overridden_url_with_trailing_slash_is_normalised(prepared_hass):
    """A trailing slash on the edited URL is stripped from the entry's unique_id and title.

    Only the identity (unique_id, title) is asserted: the raw submitted value
    is what lands in ``entry.data``, which the client normalises itself.
    """
    hass = prepared_hass
    with _patched_client(_make_client_mock()):
        result = await _discover(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_URL: f"{URL_A}/", CONF_API_KEY: API_KEY}
        )
        result = await _finish_setup(hass, result["flow_id"])
        await hass.async_block_till_done()

        assert result["title"] == f"UniFi Alerts ({URL_A})"
        assert hass.config_entries.async_entries(DOMAIN)[0].unique_id == URL_A
        await _unload_all(hass)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("raised", "error_key", "error_code"),
    [
        (InvalidAuthError("bad key"), "base", "invalid_auth"),
        (CannotConnectError("unreachable"), "base", "cannot_connect"),
        (SslCertificateError("self-signed"), CONF_CONTROLLER_URL, "invalid_ssl_cert"),
        (AlarmEndpointUnavailableError("no alarm API"), "base", "alarm_endpoint_unavailable"),
    ],
    ids=["auth_failure", "unreachable_host", "untrusted_certificate", "no_alarm_endpoint"],
)
async def test_validation_failure_reshows_user_form_then_retry_succeeds(
    prepared_hass, raised, error_key, error_code
):
    """A discovered console that fails validation re-shows the form with the error; a retry recovers.

    The re-shown form keeps the URL the user submitted as its default and the
    flow stays on the same discovery flow id, so nothing is created until the
    controller validates.
    """
    hass = prepared_hass
    client = _make_client_mock()
    with _patched_client(client):
        result = await _discover(hass)
        flow_id = result["flow_id"]

        client.authenticate = AsyncMock(side_effect=raised)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_CONTROLLER_URL: URL_A, CONF_API_KEY: "wrong"}
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["flow_id"] == flow_id
        assert result["errors"] == {error_key: error_code}
        assert _form_default(result, CONF_CONTROLLER_URL) == URL_A
        assert not hass.config_entries.async_entries(DOMAIN)

        # Still the one in-progress discovery flow; the failure did not abandon it.
        in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert [f["flow_id"] for f in in_progress] == [flow_id]

        # Retry against a now-healthy controller carries on to the categories step.
        client.authenticate = AsyncMock(return_value=None)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_CONTROLLER_URL: URL_A, CONF_API_KEY: API_KEY}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "categories"

        result = await _finish_setup(hass, flow_id)
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_API_KEY] == API_KEY
        await _unload_all(hass)


@pytest.mark.integration
async def test_validation_failure_keeps_edited_url_as_form_default(prepared_hass):
    """After a failure on an edited URL, the re-shown form offers the edit, not the discovered URL."""
    hass = prepared_hass
    client = _make_client_mock()
    client.authenticate = AsyncMock(side_effect=CannotConnectError("unreachable"))
    with _patched_client(client):
        result = await _discover(hass, HOST_A)

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CONTROLLER_URL: "https://typo.example.test", CONF_API_KEY: "k"}
        )

        assert result["errors"] == {"base": "cannot_connect"}
        assert _form_default(result, CONF_CONTROLLER_URL) == "https://typo.example.test"


@pytest.mark.integration
async def test_concurrent_discoveries_of_different_hosts_are_independent(prepared_hass):
    """Two consoles discovered at once get separate flows that complete independently."""
    hass = prepared_hass
    with _patched_client(_make_client_mock()):
        result_a = await _discover(hass, HOST_A, SERIAL_A)
        result_b = await _discover(hass, HOST_B, SERIAL_B)

        assert result_a["type"] is FlowResultType.FORM
        assert result_b["type"] is FlowResultType.FORM
        assert result_a["flow_id"] != result_b["flow_id"]
        assert _form_default(result_a, CONF_CONTROLLER_URL) == URL_A
        assert _form_default(result_b, CONF_CONTROLLER_URL) == URL_B

        in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert {f["context"]["unique_id"] for f in in_progress} == {URL_A, URL_B}
        assert {f["context"]["title_placeholders"]["name"] for f in in_progress} == {
            HOST_A,
            HOST_B,
        }

        # Finish B first; A must be untouched and still completable afterwards.
        step_b = await hass.config_entries.flow.async_configure(
            result_b["flow_id"], {CONF_API_KEY: "key-b"}
        )
        created_b = await _finish_setup(hass, step_b["flow_id"])
        await hass.async_block_till_done()
        assert created_b["type"] is FlowResultType.CREATE_ENTRY
        assert created_b["data"][CONF_CONTROLLER_URL] == URL_B
        assert created_b["data"][CONF_DEVICE_SERIAL] == SERIAL_B

        remaining = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert [f["flow_id"] for f in remaining] == [result_a["flow_id"]]

        step_a = await hass.config_entries.flow.async_configure(
            result_a["flow_id"], {CONF_API_KEY: "key-a"}
        )
        created_a = await _finish_setup(hass, step_a["flow_id"])
        await hass.async_block_till_done()
        assert created_a["type"] is FlowResultType.CREATE_ENTRY
        assert created_a["data"][CONF_CONTROLLER_URL] == URL_A
        assert created_a["data"][CONF_API_KEY] == "key-a"
        assert created_b["data"][CONF_API_KEY] == "key-b"
        # Each flow minted its own webhook identity.
        assert created_a["data"][CONF_WEBHOOK_SECRET] != created_b["data"][CONF_WEBHOOK_SECRET]
        assert (
            created_a["data"][CONF_WEBHOOK_ID_SUFFIX] != created_b["data"][CONF_WEBHOOK_ID_SUFFIX]
        )

        entries = hass.config_entries.async_entries(DOMAIN)
        assert {e.unique_id for e in entries} == {URL_A, URL_B}
        await _unload_all(hass)


@pytest.mark.integration
async def test_repeat_discovery_of_host_with_flow_in_progress_is_aborted(prepared_hass):
    """SSDP re-announcing a host whose discovery flow is still open aborts as already_in_progress.

    The integration relies on Home Assistant's `async_set_unique_id` default
    (`raise_on_progress=True`) for this; there is no integration-side
    in-progress tracking. SSDP re-announces on every advertisement cycle, so
    without it the user would accumulate duplicate discovery cards.
    """
    hass = prepared_hass
    with _patched_client(_make_client_mock()):
        first = await _discover(hass, HOST_A)
        assert first["type"] is FlowResultType.FORM

        second = await _discover(hass, HOST_A)

        assert second["type"] is FlowResultType.ABORT
        assert second["reason"] == "already_in_progress"
        in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert [f["flow_id"] for f in in_progress] == [first["flow_id"]]


@pytest.mark.integration
async def test_manual_setup_of_host_with_discovery_in_progress_is_aborted(prepared_hass):
    """Submitting a URL manually while its discovery flow is open aborts the manual flow.

    The user step also claims the URL as its unique_id with the default
    `raise_on_progress=True`, so the discovery flow and a hand-started flow
    cannot both proceed for the same console.
    """
    hass = prepared_hass
    with _patched_client(_make_client_mock()):
        discovery = await _discover(hass, HOST_A)
        manual = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert manual["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            manual["flow_id"], {CONF_CONTROLLER_URL: URL_A, CONF_API_KEY: API_KEY}
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_in_progress"
        in_progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert [f["flow_id"] for f in in_progress] == [discovery["flow_id"]]


@pytest.mark.integration
async def test_discovery_of_already_configured_host_is_aborted(prepared_hass):
    """Discovering a console that already has a config entry aborts as already_configured."""
    hass = prepared_hass
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=URL_A,
        data={CONF_CONTROLLER_URL: URL_A, CONF_API_KEY: "existing", CONF_DEVICE_SERIAL: SERIAL_A},
        version=4,
    )
    entry.add_to_hass(hass)

    result = await _discover(hass, HOST_A)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert entry.data[CONF_CONTROLLER_URL] == URL_A


@pytest.mark.integration
async def test_rediscovery_at_new_ip_updates_entry_through_real_registry(prepared_hass):
    """A configured console reappearing at a new IP has its entry refreshed in place (#343).

    Unlike the mock-driven unit test, this runs the real
    `async_update_entry(..., unique_id=...)` call, so it also proves the
    entry's unique_id is genuinely rewritten and that the credentials and
    webhook identity survive the update.
    """
    hass = prepared_hass
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=URL_A,
        data={
            CONF_CONTROLLER_URL: URL_A,
            CONF_API_KEY: "existing",
            CONF_DEVICE_SERIAL: SERIAL_A,
            CONF_WEBHOOK_SECRET: "kept-secret",
            CONF_WEBHOOK_ID_SUFFIX: "keptsuff",
        },
        version=4,
    )
    entry.add_to_hass(hass)

    result = await _discover(hass, "10.0.0.99", SERIAL_A)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == "https://10.0.0.99"
    assert entry.data[CONF_CONTROLLER_URL] == "https://10.0.0.99"
    assert entry.data[CONF_API_KEY] == "existing"
    assert entry.data[CONF_WEBHOOK_SECRET] == "kept-secret"
    assert entry.data[CONF_WEBHOOK_ID_SUFFIX] == "keptsuff"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


@pytest.mark.integration
async def test_discovery_with_unknown_serial_beside_existing_entry_starts_new_flow(
    prepared_hass,
):
    """A different console (new URL, new serial) alongside an existing entry gets its own flow."""
    hass = prepared_hass
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=URL_A,
        data={CONF_CONTROLLER_URL: URL_A, CONF_API_KEY: "existing", CONF_DEVICE_SERIAL: SERIAL_A},
        version=4,
    )
    entry.add_to_hass(hass)

    result = await _discover(hass, HOST_B, SERIAL_B)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert _form_default(result, CONF_CONTROLLER_URL) == URL_B
    assert entry.data[CONF_CONTROLLER_URL] == URL_A
    assert entry.unique_id == URL_A
