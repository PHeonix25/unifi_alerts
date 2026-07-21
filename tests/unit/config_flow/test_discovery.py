"""Tests for SSDP discovery flow (async_step_ssdp)."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info import ssdp

from custom_components.unifi_alerts.const import CONF_CONTROLLER_URL, CONF_DEVICE_SERIAL

from .conftest import _VALID_INPUT, make_flow, make_session_mock


def make_ssdp_info(host: str = "192.168.1.1") -> ssdp.SsdpServiceInfo:
    """Build a minimal SsdpServiceInfo for a UDM Pro at the given host."""
    return ssdp.SsdpServiceInfo(
        ssdp_usn="uuid:abcd-1234-efgh-5678",
        ssdp_st="urn:schemas-upnp-org:device:InternetGatewayDevice:1",
        ssdp_location=f"http://{host}:1900/description.xml",
        upnp={
            ssdp.ATTR_UPNP_MANUFACTURER: "Ubiquiti Networks",
            ssdp.ATTR_UPNP_MODEL_DESCRIPTION: "UniFi Dream Machine Pro",
            ssdp.ATTR_UPNP_SERIAL: "aa:bb:cc:dd:ee:ff",
        },
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
        instance.fetch_alarms = AsyncMock(return_value=[])

        await flow.async_step_user(_VALID_INPUT)

    assert flow._credentials[CONF_DEVICE_SERIAL] == "aa:bb:cc:dd:ee:ff"
