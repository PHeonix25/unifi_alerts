"""Tests for the UniFi Alerts config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import AbortFlow

from custom_components.unifi_alerts.config_flow import UniFiAlertsConfigFlow, UniFiAlertsOptionsFlow
from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
    DEFAULT_VERIFY_SSL,
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


def _make_session_mock() -> AsyncMock:
    """Return a mock that behaves as an async context manager (aiohttp.ClientSession)."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


_VALID_INPUT = {
    CONF_CONTROLLER_URL: "https://192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "secret",
}


@pytest.mark.asyncio
async def test_duplicate_url_aborts() -> None:
    """When the controller URL is already configured, the flow should abort."""
    flow = _make_flow()
    flow._abort_if_unique_id_configured = MagicMock(side_effect=AbortFlow("already_configured"))

    with pytest.raises(AbortFlow) as exc_info:
        await flow.async_step_user(_VALID_INPUT)

    assert exc_info.value.reason == "already_configured"


@pytest.mark.asyncio
async def test_unique_id_set_to_normalised_url() -> None:
    """async_set_unique_id must be called with the URL with trailing slash stripped."""
    flow = _make_flow()
    flow.async_step_categories = AsyncMock(return_value={"type": "form"})

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
            return_value=_make_session_mock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")

        await flow.async_step_user({**_VALID_INPUT, CONF_CONTROLLER_URL: "https://192.168.1.1/"})

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
async def test_invalid_url_scheme_shows_error() -> None:
    """A controller URL that is not http/https must show a field-level error."""
    flow = _make_flow()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

    result = await flow.async_step_user({**_VALID_INPUT, CONF_CONTROLLER_URL: "ftp://192.168.1.1"})

    assert result["step_id"] == "user"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["errors"].get("controller_url") == "invalid_url_scheme"
    # unique-id check and network call must NOT have happened
    flow.async_set_unique_id.assert_not_called()


@pytest.mark.asyncio
async def test_no_duplicate_proceeds_to_categories() -> None:
    """When there is no duplicate, the flow should proceed to the categories step."""
    flow = _make_flow()
    categories_result = {"type": "form", "step_id": "categories"}
    flow.async_step_categories = AsyncMock(return_value=categories_result)

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
            return_value=_make_session_mock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")

        result = await flow.async_step_user(_VALID_INPUT)

    assert result == categories_result
    flow.async_set_unique_id.assert_called_once()
    flow._abort_if_unique_id_configured.assert_called_once()


@pytest.mark.asyncio
async def test_categories_all_disabled_shows_error() -> None:
    """Submitting categories with nothing selected must show an error, not proceed."""
    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    flow._detected_auth_method = "userpass"
    flow._credentials = dict(_VALID_INPUT)
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

    all_off = {f"cat_{cat}": False for cat in ALL_CATEGORIES}
    result = await flow.async_step_categories(all_off)

    assert result["step_id"] == "categories"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["errors"] == {"base": "at_least_one_category"}


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
    """async_step_finish with no input should show a form with webhook URL fields in data_schema."""
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
    schema = call_kwargs["data_schema"]
    # Webhook URLs must be present as field defaults in the schema
    schema_defaults = {str(k): k.default() for k in schema.schema}
    assert any(f"?token={fake_secret}" in v for v in schema_defaults.values())
    assert any(fake_url in v for v in schema_defaults.values())


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

    await flow.async_step_finish(user_input={})

    flow.async_create_entry.assert_called_once()
    call_kwargs = flow.async_create_entry.call_args.kwargs
    assert call_kwargs["title"] == "UniFi Alerts (https://192.168.1.1)"
    assert call_kwargs["data"] is flow._entry_data


@pytest.mark.asyncio
async def test_options_init_includes_webhook_urls() -> None:
    """Options flow init should include webhook URL fields in data_schema."""
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
    schema = call_kwargs["data_schema"]
    # Webhook URLs must be present as field defaults in the schema (filter to strings only
    # because the options schema also contains booleans for category toggles).
    str_defaults = [v for v in (k.default() for k in schema.schema) if isinstance(v, str)]
    assert any(f"?token={fake_secret}" in v for v in str_defaults)
    assert any(fake_url in v for v in str_defaults)


@pytest.mark.asyncio
async def test_options_init_reads_entry_options_over_data() -> None:
    """Options flow must prefer entry.options over entry.data for saved settings."""
    from custom_components.unifi_alerts.const import (
        CONF_CLEAR_TIMEOUT,
        CONF_POLL_INTERVAL,
        DEFAULT_CLEAR_TIMEOUT,
        DEFAULT_POLL_INTERVAL,
    )

    config_entry = MagicMock()
    # entry.data has the original values from initial setup
    config_entry.data = {
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        CONF_WEBHOOK_SECRET: "secret",
        CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
    }
    # entry.options has the values from the last options save — these must win
    saved_poll = 120
    saved_clear = 60
    saved_enabled = [ALL_CATEGORIES[0]]
    config_entry.options = {
        CONF_ENABLED_CATEGORIES: saved_enabled,
        CONF_POLL_INTERVAL: saved_poll,
        CONF_CLEAR_TIMEOUT: saved_clear,
    }

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "init"})

    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url", return_value="http://x"
    ):
        await flow.async_step_init(user_input=None)

    call_kwargs = flow.async_show_form.call_args.kwargs
    schema = call_kwargs["data_schema"]
    # The schema's defaults must reflect the options values, not the data values
    schema_defaults = {str(k): k.default() for k in schema.schema}
    assert schema_defaults.get(CONF_POLL_INTERVAL) == saved_poll
    assert schema_defaults.get(CONF_CLEAR_TIMEOUT) == saved_clear
    assert schema_defaults.get(f"cat_{ALL_CATEGORIES[0]}") is True
    # A category not in saved_enabled should default to False
    assert schema_defaults.get(f"cat_{ALL_CATEGORIES[1]}") is False


@pytest.mark.asyncio
async def test_user_step_error_preserves_submitted_values() -> None:
    """On a validation error, the form must re-populate with the user's submitted values.

    If the user types a controller URL (and other fields) and auth fails, the
    schema defaults for the re-shown form must reflect what was submitted, not
    the original hardcoded defaults.
    """
    from custom_components.unifi_alerts.unifi_client import InvalidAuthError

    submitted = {
        CONF_CONTROLLER_URL: "https://10.0.0.1",
        CONF_USERNAME: "myuser",
        CONF_PASSWORD: "mypassword",
        CONF_API_KEY: "",
        CONF_VERIFY_SSL: False,
    }

    flow = _make_flow()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
            return_value=_make_session_mock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

        result = await flow.async_step_user(submitted)

    assert result["step_id"] == "user"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["errors"] == {"base": "invalid_auth"}

    # Schema defaults must reflect submitted values, not hardcoded "https://192.168.1.1"
    schema = call_kwargs["data_schema"]
    schema_defaults = {str(k): k.default() for k in schema.schema if k.default is not vol.UNDEFINED}
    assert schema_defaults.get(CONF_CONTROLLER_URL) == "https://10.0.0.1"
    assert schema_defaults.get(CONF_USERNAME) == "myuser"
    # Password and API key fields must NOT be pre-filled — they have no default
    assert CONF_PASSWORD not in schema_defaults
    assert CONF_API_KEY not in schema_defaults
    assert schema_defaults.get(CONF_VERIFY_SSL) is False


@pytest.mark.asyncio
async def test_config_flow_session_closed_on_auth_error() -> None:
    """The aiohttp ClientSession context manager must exit (clean up) even on auth error."""
    from custom_components.unifi_alerts.unifi_client import InvalidAuthError

    flow = _make_flow()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})
    mock_session = _make_session_mock()

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
            return_value=mock_session,
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

        await flow.async_step_user(_VALID_INPUT)

    mock_session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_step_initial_load_uses_hardcoded_defaults() -> None:
    """On initial load (no user_input), the form should show hardcoded defaults."""
    flow = _make_flow()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

    result = await flow.async_step_user(user_input=None)

    assert result["step_id"] == "user"
    call_kwargs = flow.async_show_form.call_args.kwargs
    schema = call_kwargs["data_schema"]
    # Only read defaults for keys that actually have one (some Optional fields don't).
    schema_defaults = {}
    import contextlib

    for k in schema.schema:
        if not isinstance(k.default, vol.Undefined.__class__) and k.default is not vol.UNDEFINED:
            with contextlib.suppress(TypeError):
                schema_defaults[str(k)] = k.default()
    assert schema_defaults.get(CONF_CONTROLLER_URL) == "https://192.168.1.1"
    assert schema_defaults.get(CONF_VERIFY_SSL) == DEFAULT_VERIFY_SSL
