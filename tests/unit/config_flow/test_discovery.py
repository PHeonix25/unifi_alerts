"""Tests for SSDP discovery flow (async_step_ssdp)."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components import ssdp
from homeassistant.data_entry_flow import AbortFlow

from .conftest import make_flow


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
