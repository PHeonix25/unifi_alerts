"""Tests for the UniFi Alerts config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.unifi_alerts.config_flow import UniFiAlertsConfigFlow, UniFiAlertsOptionsFlow
from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_WEBHOOK_SECRET,
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


@pytest.mark.asyncio
async def test_categories_proceeds_to_finish() -> None:
    """Submitting categories should proceed to the finish step, not create the entry."""
    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    flow._detected_auth_method = "userpass"
    flow._credentials = dict(_VALID_INPUT)

    finish_result = {"type": "form", "step_id": "finish"}
    flow.async_step_finish = AsyncMock(return_value=finish_result)

    cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
    result = await flow.async_step_categories(cat_input)

    assert result == finish_result
    flow.async_step_finish.assert_called_once()


@pytest.mark.asyncio
async def test_finish_shows_webhook_urls() -> None:
    """async_step_finish with no input should show a form with webhook URL placeholders."""
    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    fake_secret = "test-secret-token"
    flow._entry_data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: fake_secret}
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "finish"})

    fake_url = "http://homeassistant.local:8123/api/webhook/unifi_alerts_network_device"
    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url",
        return_value=fake_url,
    ):
        result = await flow.async_step_finish(user_input=None)

    assert result["step_id"] == "finish"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert "description_placeholders" in call_kwargs
    url_list = call_kwargs["description_placeholders"]["webhook_url_list"]
    assert fake_url in url_list
    assert f"?token={fake_secret}" in url_list


@pytest.mark.asyncio
async def test_finish_submit_creates_entry() -> None:
    """async_step_finish with empty input (form submitted) should create the config entry."""
    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    flow._entry_data = {
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        **_VALID_INPUT,
    }
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    result = await flow.async_step_finish(user_input={})

    flow.async_create_entry.assert_called_once()
    call_kwargs = flow.async_create_entry.call_args.kwargs
    assert call_kwargs["title"] == "UniFi Alerts (https://192.168.1.1)"
    assert call_kwargs["data"] is flow._entry_data


@pytest.mark.asyncio
async def test_options_init_includes_webhook_urls() -> None:
    """Options flow init should include webhook_url_list in description_placeholders."""
    fake_secret = "options-test-secret"
    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: fake_secret}
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "init"})

    fake_url = "http://homeassistant.local:8123/api/webhook/unifi_alerts_network_device"
    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url",
        return_value=fake_url,
    ):
        result = await flow.async_step_init(user_input=None)

    assert result["step_id"] == "init"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert "description_placeholders" in call_kwargs
    url_list = call_kwargs["description_placeholders"]["webhook_url_list"]
    assert fake_url in url_list
    assert f"?token={fake_secret}" in url_list
