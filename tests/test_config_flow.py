"""Tests for the UniFi Alerts config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.unifi_alerts.config_flow import UniFiAlertsConfigFlow
from custom_components.unifi_alerts.const import (
    CONF_CONTROLLER_URL,
    CONF_PASSWORD,
    CONF_USERNAME,
)


def _make_flow() -> UniFiAlertsConfigFlow:
    """Create a flow instance with a minimal hass mock."""
    flow = UniFiAlertsConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    # Patch unique ID helpers — real implementations need a running hass
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


_VALID_INPUT = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
}


@pytest.mark.asyncio
async def test_duplicate_url_aborts() -> None:
    """When the controller URL is already configured, the flow should abort."""
    flow = _make_flow()
    flow._abort_if_unique_id_configured = MagicMock(
        side_effect=AbortFlow("already_configured")
    )

    with pytest.raises(AbortFlow) as exc_info:
        await flow.async_step_user(_VALID_INPUT)

    assert exc_info.value.reason == "already_configured"


@pytest.mark.asyncio
async def test_unique_id_set_to_normalised_url() -> None:
    """async_set_unique_id must be called with the URL with trailing slash stripped."""
    flow = _make_flow()
    flow.async_step_categories = AsyncMock(return_value={"type": "form"})

    with (
        patch("custom_components.unifi_alerts.config_flow.async_create_clientsession"),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.close = AsyncMock()

        await flow.async_step_user(
            {**_VALID_INPUT, CONF_CONTROLLER_URL: "https://192.168.1.1/"}
        )

    flow.async_set_unique_id.assert_called_once_with("https://192.168.1.1")


@pytest.mark.asyncio
async def test_unique_id_checked_before_auth() -> None:
    """_abort_if_unique_id_configured must be called before authentication.

    Verifies fail-fast behaviour: we never hit the network if the entry
    already exists.
    """
    flow = _make_flow()
    call_order: list[str] = []

    async def _set_unique_id(url: str) -> None:
        call_order.append("set_unique_id")

    def _abort_if_configured() -> None:
        call_order.append("abort_check")
        raise AbortFlow("already_configured")

    flow.async_set_unique_id = _set_unique_id  # type: ignore[assignment]
    flow._abort_if_unique_id_configured = _abort_if_configured

    with pytest.raises(AbortFlow):
        await flow.async_step_user(_VALID_INPUT)

    assert call_order == ["set_unique_id", "abort_check"]


@pytest.mark.asyncio
async def test_no_duplicate_proceeds_to_categories() -> None:
    """When there is no duplicate, the flow should proceed to the categories step."""
    flow = _make_flow()
    categories_result = {"type": "form", "step_id": "categories"}
    flow.async_step_categories = AsyncMock(return_value=categories_result)

    with (
        patch("custom_components.unifi_alerts.config_flow.async_create_clientsession"),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.close = AsyncMock()

        result = await flow.async_step_user(_VALID_INPUT)

    assert result == categories_result
    flow.async_set_unique_id.assert_called_once()
    flow._abort_if_unique_id_configured.assert_called_once()
