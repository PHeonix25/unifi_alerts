"""Tests for SSDP discovery flow (async_step_ssdp)."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info import ssdp

from custom_components.unifi_alerts.const import (
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_DEVICE_SERIAL,
)

from .conftest import _VALID_INPUT, make_flow, make_session_mock


def make_ssdp_info(
    host: str = "192.168.1.1", serial: str | None = "aa:bb:cc:dd:ee:ff"
) -> ssdp.SsdpServiceInfo:
    """Build a minimal SsdpServiceInfo for a UDM Pro at the given host.

    `serial` defaults to a stand-in UPnP serial; pass `None` to simulate a
    discovery payload that lacks one, as seen on some firmware/device
    combinations.
    """
    upnp = {
        ssdp.ATTR_UPNP_MANUFACTURER: "Ubiquiti Networks",
        ssdp.ATTR_UPNP_MODEL_DESCRIPTION: "UniFi Dream Machine Pro",
    }
    if serial is not None:
        upnp[ssdp.ATTR_UPNP_SERIAL] = serial
    return ssdp.SsdpServiceInfo(
        ssdp_usn="uuid:abcd-1234-efgh-5678",
        ssdp_st="urn:schemas-upnp-org:device:InternetGatewayDevice:1",
        ssdp_location=f"http://{host}:1900/description.xml",
        upnp=upnp,
    )


@pytest.mark.asyncio
async def test_ssdp_prefills_controller_url() -> None:
    """async_step_ssdp pre-fills _controller_url from the discovered host."""
    flow = make_flow()
    flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})

    await flow.async_step_ssdp(make_ssdp_info("10.0.0.1"))

    assert flow._controller_url == "https://10.0.0.1"


@pytest.mark.asyncio
async def test_ssdp_sets_unique_id() -> None:
    """async_step_ssdp must set the unique_id to the controller URL."""
    flow = make_flow()
    flow.async_step_user = AsyncMock(return_value={"type": "form"})

    await flow.async_step_ssdp(make_ssdp_info("192.168.1.1"))

    flow.async_set_unique_id.assert_called_once_with("https://192.168.1.1")


@pytest.mark.asyncio
async def test_ssdp_aborts_when_already_configured() -> None:
    """async_step_ssdp must abort if the unique_id is already configured."""
    flow = make_flow()
    flow._abort_if_unique_id_configured = MagicMock(side_effect=AbortFlow("already_configured"))

    with pytest.raises(AbortFlow) as exc_info:
        await flow.async_step_ssdp(make_ssdp_info("192.168.1.1"))

    assert exc_info.value.reason == "already_configured"


@pytest.mark.asyncio
async def test_ssdp_aborts_on_missing_host() -> None:
    """async_step_ssdp aborts with cannot_connect when no host can be extracted."""
    flow = make_flow()
    flow.async_abort = MagicMock(return_value={"type": "abort", "reason": "cannot_connect"})

    # Pass an SsdpServiceInfo with no ssdp_location
    info = ssdp.SsdpServiceInfo(
        ssdp_usn="uuid:abcd",
        ssdp_st="urn:test",
        ssdp_location=None,
        upnp={},
    )
    result = await flow.async_step_ssdp(info)

    flow.async_abort.assert_called_once_with(reason="cannot_connect")
    assert result["reason"] == "cannot_connect"


@pytest.mark.asyncio
async def test_ssdp_sets_title_placeholder() -> None:
    """async_step_ssdp populates context title_placeholders with the host."""
    flow = make_flow()
    flow.async_step_user = AsyncMock(return_value={"type": "form"})

    await flow.async_step_ssdp(make_ssdp_info("192.168.50.1"))

    assert flow.context.get("title_placeholders", {}).get("name") == "192.168.50.1"


@pytest.mark.asyncio
async def test_ssdp_rediscovery_with_changed_ip_updates_existing_entry() -> None:
    """A known console rediscovered at a new IP updates the stale entry in place.

    The unique_id (URL-keyed) check does not match here — that is the whole
    bug (#343) — so the entry is found via its stored UPnP serial instead,
    which does not change when the controller's IP does.
    """
    existing_entry = MagicMock()
    existing_entry.data = {
        CONF_CONTROLLER_URL: "https://192.168.1.1",
        CONF_DEVICE_SERIAL: "aa:bb:cc:dd:ee:ff",
    }

    flow = make_flow()
    flow.hass.config_entries.async_entries = MagicMock(return_value=[existing_entry])
    flow.async_abort = MagicMock(return_value={"type": "abort", "reason": "already_configured"})
    flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})

    result = await flow.async_step_ssdp(make_ssdp_info("10.0.0.99"))

    flow.hass.config_entries.async_update_entry.assert_called_once()
    call = flow.hass.config_entries.async_update_entry.call_args
    assert call.args[0] is existing_entry
    assert call.kwargs["data"][CONF_CONTROLLER_URL] == "https://10.0.0.99"
    assert call.kwargs["data"][CONF_DEVICE_SERIAL] == "aa:bb:cc:dd:ee:ff"
    assert call.kwargs["unique_id"] == "https://10.0.0.99"
    flow.async_abort.assert_called_once_with(reason="already_configured")
    assert result["reason"] == "already_configured"
    flow.async_step_user.assert_not_called()


@pytest.mark.asyncio
async def test_ssdp_rediscovery_same_url_does_not_update_entry() -> None:
    """Rediscovery of an entry already at the current URL is a no-op update-wise."""
    existing_entry = MagicMock()
    existing_entry.data = {
        CONF_CONTROLLER_URL: "https://192.168.1.1",
        CONF_DEVICE_SERIAL: "aa:bb:cc:dd:ee:ff",
    }

    flow = make_flow()
    flow.hass.config_entries.async_entries = MagicMock(return_value=[existing_entry])
    flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})

    await flow.async_step_ssdp(make_ssdp_info("192.168.1.1"))

    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.async_step_user.assert_called_once()


@pytest.mark.asyncio
async def test_ssdp_no_matching_serial_continues_to_user_step() -> None:
    """A genuinely new device (no serial match) proceeds to the user step as before."""
    other_entry = MagicMock()
    other_entry.data = {
        CONF_CONTROLLER_URL: "https://192.168.1.50",
        CONF_DEVICE_SERIAL: "11:22:33:44:55:66",
    }

    flow = make_flow()
    flow.hass.config_entries.async_entries = MagicMock(return_value=[other_entry])
    flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})

    result = await flow.async_step_ssdp(make_ssdp_info("10.0.0.5"))

    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.async_step_user.assert_called_once()
    assert flow._device_serial == "aa:bb:cc:dd:ee:ff"
    assert result == {"type": "form", "step_id": "user"}


@pytest.mark.asyncio
async def test_ssdp_discovery_without_serial_continues_to_user_step() -> None:
    """A discovery payload with no UPnP serial skips the rediscovery lookup.

    Matches pre-#343 behaviour for devices/firmware whose SSDP response
    never carries a serial.
    """
    flow = make_flow()
    flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})

    result = await flow.async_step_ssdp(make_ssdp_info("10.0.0.7", serial=None))

    flow.hass.config_entries.async_entries.assert_not_called()
    flow.hass.config_entries.async_update_entry.assert_not_called()
    flow.async_step_user.assert_called_once()
    assert flow._device_serial == ""
    assert result == {"type": "form", "step_id": "user"}


@pytest.mark.asyncio
async def test_user_step_uses_ssdp_url_as_default() -> None:
    """When _controller_url is pre-filled by SSDP, async_step_user uses it as the form default."""
    import voluptuous as vol

    from custom_components.unifi_alerts.const import CONF_CONTROLLER_URL

    flow = make_flow()
    flow._controller_url = "https://10.10.10.1"

    result = await flow.async_step_user()

    assert result["type"] == "form"
    schema = result["data_schema"]
    # Extract defaults from voluptuous key objects (default lives on the key, not the validator).
    schema_defaults: dict[str, object] = {}
    for key in schema.schema:
        if hasattr(key, "default") and not isinstance(key.default, vol.Undefined.__class__):
            with contextlib.suppress(Exception):
                schema_defaults[key.schema] = key.default()

    assert schema_defaults.get(CONF_CONTROLLER_URL) == "https://10.10.10.1"


@pytest.mark.asyncio
async def test_user_step_carries_ssdp_serial_into_credentials() -> None:
    """A serial captured by async_step_ssdp is threaded into _credentials on setup.

    So a future rediscovery at a different address can find this entry via
    _find_entry_by_serial (#343).
    """
    flow = make_flow()
    flow._device_serial = "aa:bb:cc:dd:ee:ff"
    flow.async_step_categories = AsyncMock(return_value={"type": "form", "step_id": "categories"})

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.async_get_clientsession",
            return_value=make_session_mock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value=None)
        instance.validate_connectivity = AsyncMock(return_value="v2")

        await flow.async_step_user(_VALID_INPUT)

    assert flow._credentials[CONF_DEVICE_SERIAL] == "aa:bb:cc:dd:ee:ff"


@pytest.mark.asyncio
async def test_ssdp_location_port_and_path_are_dropped_from_controller_url() -> None:
    """Only the hostname of the SSDP location survives: its port and path are not carried over.

    The SSDP location points at the UPnP description document (port 1900 in the
    fixtures), not at the UniFi OS HTTPS console, so the pre-filled URL must be
    the bare `https://{host}`.
    """
    flow = make_flow()
    flow.async_step_user = AsyncMock(return_value={"type": "form", "step_id": "user"})

    await flow.async_step_ssdp(make_ssdp_info("10.1.2.3"))

    assert flow._controller_url == "https://10.1.2.3"
    flow.async_set_unique_id.assert_called_once_with("https://10.1.2.3")


@pytest.mark.asyncio
async def test_ssdp_missing_host_aborts_before_any_state_is_touched() -> None:
    """An unusable SSDP location aborts without claiming a unique_id or touching entries."""
    flow = make_flow()
    info = ssdp.SsdpServiceInfo(
        ssdp_usn="uuid:abcd",
        ssdp_st="urn:test",
        ssdp_location="not-a-url",
        upnp={ssdp.ATTR_UPNP_SERIAL: "aa:bb:cc:dd:ee:ff"},
    )

    result = await flow.async_step_ssdp(info)

    assert result["type"] == "abort"
    assert result["reason"] == "cannot_connect"
    assert flow._controller_url == ""
    assert flow._device_serial == ""
    flow.async_set_unique_id.assert_not_called()
    flow.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_discovered_form_accepts_api_key_only_and_keeps_prefilled_url() -> None:
    """Submitting only the API key to the discovery-pre-filled form validates to the discovered URL.

    Home Assistant runs submitted input through the form schema before calling
    the step, so the schema default is what an untouched URL field becomes.
    """
    flow = make_flow()
    await flow.async_step_ssdp(make_ssdp_info("10.0.0.8"))
    result = await flow.async_step_user()

    validated = result["data_schema"]({CONF_API_KEY: "k"})

    assert validated[CONF_CONTROLLER_URL] == "https://10.0.0.8"
    assert validated[CONF_API_KEY] == "k"


@pytest.mark.asyncio
async def test_discovery_then_user_submit_creates_credentials_for_discovered_host() -> None:
    """SSDP then a valid user submit: the client is built for the discovered host and serial kept.

    Drives the real `async_step_ssdp` and `async_step_user` back to back on one
    flow object (rather than seeding `_device_serial` by hand) and asserts the
    UniFiClient is constructed against the discovered URL.
    """
    flow = make_flow()
    flow.async_step_categories = AsyncMock(return_value={"type": "form", "step_id": "categories"})

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.async_get_clientsession",
            return_value=make_session_mock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value=None)
        instance.validate_connectivity = AsyncMock(return_value="v2")

        await flow.async_step_ssdp(make_ssdp_info("10.0.0.9", serial="de:ad:be:ef:00:01"))
        # The step shown to the user pre-filled the URL; they submit it unchanged.
        await flow.async_step_user({CONF_CONTROLLER_URL: "https://10.0.0.9", CONF_API_KEY: "k"})

    assert mock_cls.call_args.args[1] == "https://10.0.0.9"
    assert flow._controller_url == "https://10.0.0.9"
    assert flow._credentials[CONF_DEVICE_SERIAL] == "de:ad:be:ef:00:01"
    assert flow._credentials[CONF_API_KEY] == "k"


def test_manifest_ssdp_matchers_cover_the_discovery_payload_shape() -> None:
    """manifest.json declares SSDP matchers for Ubiquiti UniFi Dream Machine consoles.

    SSDP is the only discovery mechanism the integration supports (no
    zeroconf/dhcp entries), and `async_step_ssdp` only ever runs for payloads
    Home Assistant matched against these entries. Every matcher must carry both
    keys so a non-UniFi Ubiquiti device is not offered, and the payload shape
    used throughout these tests must be matched by one of them.
    """
    manifest_path = (
        Path(__file__).resolve().parents[3] / "custom_components" / "unifi_alerts" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    matchers = manifest["ssdp"]
    assert matchers, "manifest.json must declare at least one SSDP matcher"
    assert all(
        set(m) == {ssdp.ATTR_UPNP_MANUFACTURER, ssdp.ATTR_UPNP_MODEL_DESCRIPTION} for m in matchers
    )
    assert "zeroconf" not in manifest
    assert "dhcp" not in manifest

    upnp = make_ssdp_info().upnp
    assert any(all(upnp.get(key) == value for key, value in m.items()) for m in matchers)
