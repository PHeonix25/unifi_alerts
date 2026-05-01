"""Tests for the UniFi Alerts config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        instance.fetch_alarms = AsyncMock(return_value=[])

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
        instance.fetch_alarms = AsyncMock(return_value=[])

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
async def test_options_finish_includes_webhook_urls() -> None:
    """Options flow finish step should include webhook URL fields with the stored secret."""
    fake_secret = "options-test-secret"
    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: fake_secret}
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow._pending_options = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES}
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
    str_defaults = [v for v in (k.default() for k in schema.schema) if isinstance(v, str)]
    assert any(f"?token={fake_secret}" in v for v in str_defaults)
    assert any(fake_url in v for v in str_defaults)


@pytest.mark.asyncio
async def test_options_categories_submit_routes_to_finish() -> None:
    """Submitting valid categories should call async_step_finish (not create_entry directly)."""
    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: "s"}
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    finish_result = {"type": "form", "step_id": "finish"}
    flow.async_step_finish = AsyncMock(return_value=finish_result)

    cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
    result = await flow.async_step_categories(cat_input)

    flow.async_step_finish.assert_called_once()
    assert result["step_id"] == "finish"


@pytest.mark.asyncio
async def test_options_finish_submit_creates_entry() -> None:
    """Submitting the finish step (empty user_input) must call async_create_entry with pending options."""
    from custom_components.unifi_alerts.const import (
        CONF_CLEAR_TIMEOUT,
        CONF_POLL_INTERVAL,
        CONF_SITE,
    )

    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: "s"}
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow._pending_options = {
        CONF_ENABLED_CATEGORIES: [ALL_CATEGORIES[0]],
        CONF_POLL_INTERVAL: 300,
        CONF_CLEAR_TIMEOUT: 60,
        CONF_SITE: "default",
    }
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    result = await flow.async_step_finish(user_input={})

    flow.async_create_entry.assert_called_once()
    call_kwargs = flow.async_create_entry.call_args.kwargs
    assert call_kwargs["title"] == ""
    assert call_kwargs["data"] is flow._pending_options
    assert result["type"] == "create_entry"


@pytest.mark.asyncio
async def test_options_flow_full_cycle() -> None:
    """Full options flow: blank credentials → categories → finish → create_entry."""
    from custom_components.unifi_alerts.const import (
        CONF_CLEAR_TIMEOUT,
        CONF_POLL_INTERVAL,
        CONF_SITE,
    )

    config_entry = MagicMock()
    config_entry.data = {
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        CONF_WEBHOOK_SECRET: "full-cycle-secret",
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 5,
    }
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_update_entry = MagicMock()
    flow.hass = hass
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    # Step 1: blank credentials → skip to categories
    blank_creds = {CONF_CONTROLLER_URL: "", CONF_USERNAME: "", CONF_PASSWORD: "", CONF_API_KEY: "", CONF_VERIFY_SSL: True}
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})
    await flow.async_step_credentials(blank_creds)

    # Step 2: submit categories
    first_cat = ALL_CATEGORIES[0]
    cat_input = {f"cat_{cat}": (cat == first_cat) for cat in ALL_CATEGORIES}
    cat_input[CONF_POLL_INTERVAL] = 120
    cat_input[CONF_CLEAR_TIMEOUT] = 10
    cat_input[CONF_SITE] = "default"

    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url",
        return_value="http://ha.local/webhook/x",
    ):
        await flow.async_step_categories(cat_input)

    # Step 3: submit finish → create_entry
    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url",
        return_value="http://ha.local/webhook/x",
    ):
        result = await flow.async_step_finish(user_input={})

    assert result["type"] == "create_entry"
    saved = flow.async_create_entry.call_args.kwargs["data"]
    assert saved[CONF_ENABLED_CATEGORIES] == [first_cat]
    assert saved[CONF_POLL_INTERVAL] == 120
    assert saved[CONF_CLEAR_TIMEOUT] == 10


@pytest.mark.asyncio
async def test_options_categories_reads_entry_options_over_data() -> None:
    """Options flow categories step must prefer entry.options over entry.data for saved settings."""
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
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

    await flow.async_step_categories(user_input=None)

    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["step_id"] == "categories"
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


# ---------------------------------------------------------------------------
# Categories step — boundary-value and validation coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_categories_step_saves_poll_interval_and_clear_timeout() -> None:
    """Submitted poll_interval and clear_timeout must be stored in _entry_data."""
    from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    flow._detected_auth_method = "userpass"
    flow._credentials = {CONF_WEBHOOK_SECRET: "s"}
    flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

    cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
    cat_input[CONF_POLL_INTERVAL] = 120
    cat_input[CONF_CLEAR_TIMEOUT] = 30

    await flow.async_step_categories(cat_input)

    assert flow._entry_data[CONF_POLL_INTERVAL] == 120
    assert flow._entry_data[CONF_CLEAR_TIMEOUT] == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("poll_interval", [10, 3600])
async def test_categories_step_accepts_boundary_poll_intervals(poll_interval: int) -> None:
    """poll_interval boundary values 10 and 3600 must be accepted without error."""
    from custom_components.unifi_alerts.const import CONF_POLL_INTERVAL

    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    flow._detected_auth_method = "userpass"
    flow._credentials = {CONF_WEBHOOK_SECRET: "s"}
    flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

    cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
    cat_input[CONF_POLL_INTERVAL] = poll_interval

    result = await flow.async_step_categories(cat_input)

    assert result["step_id"] == "finish"


@pytest.mark.asyncio
@pytest.mark.parametrize("clear_timeout", [1, 1440])
async def test_categories_step_accepts_boundary_clear_timeouts(clear_timeout: int) -> None:
    """clear_timeout boundary values 1 and 1440 must be accepted without error."""
    from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT

    flow = _make_flow()
    flow._controller_url = "https://192.168.1.1"
    flow._detected_auth_method = "userpass"
    flow._credentials = {CONF_WEBHOOK_SECRET: "s"}
    flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

    cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
    cat_input[CONF_CLEAR_TIMEOUT] = clear_timeout

    result = await flow.async_step_categories(cat_input)

    assert result["step_id"] == "finish"


# ---------------------------------------------------------------------------
# Options flow — form submission (saving updated values)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_flow_saves_submitted_values() -> None:
    """Submitting the options flow (categories → finish) must persist the selected categories and intervals."""
    from custom_components.unifi_alerts.const import (
        CONF_CLEAR_TIMEOUT,
        CONF_POLL_INTERVAL,
        CONF_SITE,
    )

    config_entry = MagicMock()
    config_entry.data = {
        CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
        CONF_WEBHOOK_SECRET: "sec",
        CONF_POLL_INTERVAL: 60,
        CONF_CLEAR_TIMEOUT: 5,
    }
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    # Only enable first category; set custom poll, clear, and site values
    first_cat = ALL_CATEGORIES[0]
    user_input = {f"cat_{cat}": (cat == first_cat) for cat in ALL_CATEGORIES}
    user_input[CONF_POLL_INTERVAL] = 300
    user_input[CONF_CLEAR_TIMEOUT] = 60
    user_input[CONF_SITE] = "secondary"

    # Submit categories (stores in _pending_options, routes to finish)
    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url",
        return_value="http://ha.local/webhook/x",
    ):
        await flow.async_step_categories(user_input)

    # Submit finish → creates entry
    with patch(
        "custom_components.unifi_alerts.config_flow.async_generate_url",
        return_value="http://ha.local/webhook/x",
    ):
        result = await flow.async_step_finish(user_input={})

    assert result["type"] == "create_entry"
    saved = flow.async_create_entry.call_args.kwargs["data"]
    assert saved[CONF_ENABLED_CATEGORIES] == [first_cat]
    assert saved[CONF_POLL_INTERVAL] == 300
    assert saved[CONF_CLEAR_TIMEOUT] == 60
    assert saved[CONF_SITE] == "secondary"


@pytest.mark.asyncio
async def test_step_user_fetch_alarms_failure_shows_cannot_connect() -> None:
    """If fetch_alarms() raises CannotConnectError after successful auth, show cannot_connect error."""
    from custom_components.unifi_alerts.unifi_client import CannotConnectError

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
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.fetch_alarms = AsyncMock(
            side_effect=CannotConnectError("UniFi API error: api.err.InvalidObject")
        )

        result = await flow.async_step_user(_VALID_INPUT)

    assert result["step_id"] == "user"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_conf_is_unifi_os_stored_in_credentials() -> None:
    """CONF_IS_UNIFI_OS must be stored in _credentials after a successful step 1."""
    from custom_components.unifi_alerts.const import CONF_IS_UNIFI_OS

    flow = _make_flow()
    flow.async_step_categories = AsyncMock(return_value={"type": "form", "step_id": "categories"})

    with (
        patch(
            "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
            return_value=_make_session_mock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="userpass")
        instance.fetch_alarms = AsyncMock(return_value=[])
        instance._is_unifi_os = True  # simulate a detected UniFi OS controller

        await flow.async_step_user(_VALID_INPUT)

    assert CONF_IS_UNIFI_OS in flow._credentials
    assert flow._credentials[CONF_IS_UNIFI_OS] is True


@pytest.mark.asyncio
async def test_options_flow_rejects_all_disabled() -> None:
    """Options flow must show error when all categories are unchecked."""
    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: "s"}
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

    all_off = {f"cat_{cat}": False for cat in ALL_CATEGORIES}
    result = await flow.async_step_categories(all_off)

    assert result["step_id"] == "categories"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["errors"] == {"base": "at_least_one_category"}


# ---------------------------------------------------------------------------
# Reauth flow tests
# ---------------------------------------------------------------------------


def _make_reauth_flow(entry_id: str = "entry-test") -> UniFiAlertsConfigFlow:
    """Create a flow wired up for reauth tests."""
    flow = UniFiAlertsConfigFlow()
    flow.context = {"entry_id": entry_id}

    mock_entry = MagicMock()
    mock_entry.entry_id = entry_id
    mock_entry.title = "UniFi Alerts (https://192.168.1.1)"
    mock_entry.data = {
        CONF_CONTROLLER_URL: "https://192.168.1.1",
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "oldpassword",
        CONF_WEBHOOK_SECRET: "secret",
    }

    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    flow.hass = hass
    flow._reauth_entry = mock_entry  # pre-set so reauth_confirm can access it
    return flow


class TestReauthFlow:
    """Tests for the reauth flow steps."""

    @pytest.mark.asyncio
    async def test_async_step_reauth_routes_to_reauth_confirm(self) -> None:
        """async_step_reauth must store the entry and advance to reauth_confirm."""
        flow = UniFiAlertsConfigFlow()
        entry_id = "entry-reauth-1"
        flow.context = {"entry_id": entry_id}

        mock_entry = MagicMock()
        mock_entry.entry_id = entry_id
        mock_entry.title = "Test Controller"

        hass = MagicMock()
        hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        hass.config_entries.async_reload = AsyncMock()
        flow.hass = hass

        confirm_result = {"type": "form", "step_id": "reauth_confirm"}
        flow.async_step_reauth_confirm = AsyncMock(return_value=confirm_result)

        with patch(
            "custom_components.unifi_alerts.config_flow._create_auth_failed_issue"
        ):
            result = await flow.async_step_reauth({})

        assert result == confirm_result
        assert flow._reauth_entry is mock_entry

    @pytest.mark.asyncio
    async def test_async_step_reauth_creates_issue(self) -> None:
        """async_step_reauth must call _create_auth_failed_issue."""
        flow = UniFiAlertsConfigFlow()
        entry_id = "entry-issue-test"
        flow.context = {"entry_id": entry_id}

        mock_entry = MagicMock()
        mock_entry.entry_id = entry_id
        mock_entry.title = "Test"

        hass = MagicMock()
        hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
        hass.config_entries.async_reload = AsyncMock()
        flow.hass = hass
        flow.async_step_reauth_confirm = AsyncMock(return_value={"type": "form"})

        with patch(
            "custom_components.unifi_alerts.config_flow._create_auth_failed_issue"
        ) as mock_create:
            await flow.async_step_reauth({})

        mock_create.assert_called_once_with(hass, mock_entry)

    @pytest.mark.asyncio
    async def test_reauth_confirm_no_input_shows_form(self) -> None:
        """With no user_input, reauth_confirm must show the credential form."""
        flow = _make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        result = await flow.async_step_reauth_confirm(user_input=None)

        assert result["step_id"] == "reauth_confirm"
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["step_id"] == "reauth_confirm"
        assert not call_kwargs["errors"]

    @pytest.mark.asyncio
    async def test_reauth_confirm_valid_credentials_updates_entry_and_aborts(self) -> None:
        """Valid credentials must update entry.data and abort with reauth_successful."""
        flow = _make_reauth_flow()
        flow.async_abort = MagicMock(return_value={"type": "abort", "reason": "reauth_successful"})

        new_creds = {CONF_USERNAME: "admin", CONF_PASSWORD: "newpassword"}

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
            patch("custom_components.unifi_alerts.config_flow.ir.async_delete_issue") as mock_del,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance._is_unifi_os = False

            result = await flow.async_step_reauth_confirm(user_input=new_creds)

        assert result["reason"] == "reauth_successful"
        flow.hass.config_entries.async_update_entry.assert_called_once()
        flow.hass.config_entries.async_reload.assert_awaited_once()
        mock_del.assert_called_once_with(
            flow.hass, "unifi_alerts", f"auth_failed_{flow._reauth_entry.entry_id}"
        )

    @pytest.mark.asyncio
    async def test_reauth_confirm_invalid_credentials_shows_error(self) -> None:
        """Invalid credentials must re-show the form with invalid_auth error."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = _make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        new_creds = {CONF_USERNAME: "admin", CONF_PASSWORD: "wrongpassword"}

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad"))

            result = await flow.async_step_reauth_confirm(user_input=new_creds)

        assert result["step_id"] == "reauth_confirm"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_reauth_confirm_cannot_connect_shows_error(self) -> None:
        """A connection error during reauth must show cannot_connect error."""
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = _make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=CannotConnectError("down"))

            result = await flow.async_step_reauth_confirm(
                user_input={CONF_USERNAME: "admin", CONF_PASSWORD: "pass"}
            )

        assert result["step_id"] == "reauth_confirm"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_reauth_confirm_does_not_delete_issue_on_failure(self) -> None:
        """async_delete_issue must NOT be called when reauth fails."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = _make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
            patch("custom_components.unifi_alerts.config_flow.ir.async_delete_issue") as mock_del,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad"))

            await flow.async_step_reauth_confirm(
                user_input={CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"}
            )

        mock_del.assert_not_called()


# ---------------------------------------------------------------------------
# Options flow — credentials step
# ---------------------------------------------------------------------------


def _make_options_flow(
    url: str = "https://192.168.1.1",
    enabled_categories: list[str] | None = None,
) -> UniFiAlertsOptionsFlow:
    """Return an options-flow instance wired with a minimal mock config entry and hass."""
    config_entry = MagicMock()
    config_entry.entry_id = "entry-options-creds"
    config_entry.data = {
        CONF_CONTROLLER_URL: url,
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "secret",
        CONF_API_KEY: "",
        CONF_VERIFY_SSL: True,
        CONF_WEBHOOK_SECRET: "fixed-secret",
        CONF_ENABLED_CATEGORIES: enabled_categories or ALL_CATEGORIES,
    }
    config_entry.options = {}

    flow = UniFiAlertsOptionsFlow(config_entry)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_update_entry = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    flow.hass = hass
    return flow


class TestOptionsFlowCredentials:
    """Tests for the new credentials step in the options flow."""

    @pytest.mark.asyncio
    async def test_init_routes_to_credentials_step(self) -> None:
        """Opening the options flow (async_step_init) should show the credentials step first."""
        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})

        result = await flow.async_step_init(user_input=None)

        assert result["step_id"] == "credentials"
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["step_id"] == "credentials"

    @pytest.mark.asyncio
    async def test_blank_submission_skips_to_categories(self) -> None:
        """Submitting all-blank credentials skips to the categories step without any auth call."""
        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        blank_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        result = await flow.async_step_credentials(blank_input)

        # Should have proceeded to categories
        assert result["step_id"] == "categories"
        # No entry update should have occurred
        flow.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_new_credentials_updates_entry_data(self) -> None:
        """Submitting new valid credentials must update entry.data and continue to categories."""
        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        new_creds = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "newpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False

            result = await flow.async_step_credentials(new_creds)

        # entry.data must have been updated
        flow.hass.config_entries.async_update_entry.assert_called_once()
        updated_data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert updated_data[CONF_CONTROLLER_URL] == "https://10.0.0.1"
        assert updated_data[CONF_PASSWORD] == "newpass"

        # Should have continued to categories
        assert result["step_id"] == "categories"

    @pytest.mark.asyncio
    async def test_invalid_credentials_shows_error_and_does_not_update(self) -> None:
        """When the new credentials fail auth, show invalid_auth and do NOT update entry.data."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = _make_options_flow()
        flow.async_show_form = MagicMock(
            return_value={"type": "form", "step_id": "credentials"}
        )

        new_creds = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "baduser",
            CONF_PASSWORD: "wrongpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

            result = await flow.async_step_credentials(new_creds)

        assert result["step_id"] == "credentials"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "invalid_auth"}
        # entry.data must NOT have been touched
        flow.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_url_scheme_shows_error(self) -> None:
        """A non-http/https URL scheme must show a field-level error without hitting the network."""
        flow = _make_options_flow()
        flow.async_show_form = MagicMock(
            return_value={"type": "form", "step_id": "credentials"}
        )

        bad_url_input = {
            CONF_CONTROLLER_URL: "ftp://192.168.1.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with patch(
            "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
            return_value=_make_session_mock(),
        ) as mock_session_cls:
            result = await flow.async_step_credentials(bad_url_input)

        assert result["step_id"] == "credentials"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"].get(CONF_CONTROLLER_URL) == "invalid_url_scheme"
        # No network call should have been made
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_url_collision_aborts(self) -> None:
        """Changing to a URL already used by another entry must abort with already_configured."""
        flow = _make_options_flow(url="https://192.168.1.1")

        # Simulate an existing OTHER entry with the new URL
        other_entry = MagicMock()
        other_entry.entry_id = "other-entry"
        other_entry.data = {CONF_CONTROLLER_URL: "https://10.0.0.1"}
        flow.hass.config_entries.async_entries = MagicMock(return_value=[other_entry])

        flow.async_abort = MagicMock(return_value={"type": "abort", "reason": "already_configured"})

        new_creds = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False

            result = await flow.async_step_credentials(new_creds)

        assert result["reason"] == "already_configured"
        flow.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_after_credential_update_categories_proceeds_normally(self) -> None:
        """After a successful credentials update, categories → finish → create_entry works end-to-end."""
        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        # First: update credentials
        new_creds = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "newadmin",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: False,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = True

            await flow.async_step_credentials(new_creds)

        # Now: submit the categories step (stores in _pending_options, routes to finish)
        first_cat = ALL_CATEGORIES[0]
        cat_input = {f"cat_{cat}": (cat == first_cat) for cat in ALL_CATEGORIES}
        cat_input[CONF_POLL_INTERVAL] = 90
        cat_input[CONF_CLEAR_TIMEOUT] = 15

        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            await flow.async_step_categories(cat_input)

        # Submit finish → create_entry
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        saved = flow.async_create_entry.call_args.kwargs["data"]
        assert saved[CONF_ENABLED_CATEGORIES] == [first_cat]
        assert saved[CONF_POLL_INTERVAL] == 90
        assert saved[CONF_CLEAR_TIMEOUT] == 15


# ---------------------------------------------------------------------------
# Webhook secret rotation in options flow
# ---------------------------------------------------------------------------


class TestWebhookSecretRotation:
    """Cluster A: users must be able to regenerate the webhook secret without
    deleting and re-adding the integration.

    The options flow's credentials step now exposes a
    ``CONF_REGENERATE_WEBHOOK_SECRET`` checkbox. When ticked:
    - With no other credential changes: persist a new secret and continue.
    - With credential changes: persist new credentials AND new secret atomically.
    """

    @pytest.mark.asyncio
    async def test_rotate_only_persists_new_secret_and_skips_auth(self) -> None:
        """Ticking only the regenerate checkbox must NOT call authenticate()."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        rotate_only = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
            CONF_REGENERATE_WEBHOOK_SECRET: True,
        }

        with patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls:
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock()  # must NOT be called
            await flow.async_step_credentials(rotate_only)
            instance.authenticate.assert_not_called()

        flow.hass.config_entries.async_update_entry.assert_called_once()
        updated = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        # New secret must differ from the fixture-installed one
        assert updated[CONF_WEBHOOK_SECRET] != "fixed-secret"
        # And it must be a non-empty token (token_urlsafe(32) is at least 40 chars)
        assert len(updated[CONF_WEBHOOK_SECRET]) >= 40

    @pytest.mark.asyncio
    async def test_rotate_with_credential_change_updates_both(self) -> None:
        """Ticking regenerate alongside new creds rotates the secret AND updates creds."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        new_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "newpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
            CONF_REGENERATE_WEBHOOK_SECRET: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.aiohttp.ClientSession",
                return_value=_make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False
            await flow.async_step_credentials(new_input)

        flow.hass.config_entries.async_update_entry.assert_called_once()
        updated = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert updated[CONF_PASSWORD] == "newpass"
        assert updated[CONF_WEBHOOK_SECRET] != "fixed-secret"

    @pytest.mark.asyncio
    async def test_unticked_does_not_rotate(self) -> None:
        """If the checkbox is unset, the existing secret must remain intact."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = _make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        no_rotate = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
            CONF_REGENERATE_WEBHOOK_SECRET: False,
        }

        await flow.async_step_credentials(no_rotate)
        # No update at all because nothing changed
        flow.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_finish_step_displays_new_url_after_rotation(self) -> None:
        """After secret rotation, the finish step must show URLs with the NEW token.

        Regression guard: HA's ``async_update_entry`` mutates ``entry.data``
        synchronously via ``object.__setattr__(entry, "data", ...)``. Our flow
        relies on that — between calling ``async_update_entry`` and reading
        ``self._config_entry.data[CONF_WEBHOOK_SECRET]`` in the finish step,
        no awaits intervene that could swap data. If HA ever changed those
        semantics (or if a regression introduced an extra await between the
        update and the read), users would see the OLD token displayed in the
        finish step despite the new one being persisted — a confusing UX
        bug. This test simulates the real HA behaviour and asserts the URL
        contains the freshly-rotated secret.
        """
        from custom_components.unifi_alerts.const import (
            CONF_REGENERATE_WEBHOOK_SECRET,
            CONF_WEBHOOK_ID_SUFFIX,
        )

        flow = _make_options_flow()

        # Simulate HA's real async_update_entry: mutate entry.data in-place
        def _fake_update(entry, *, data=None, **kwargs):
            if data is not None:
                entry.data = data

        flow.hass.config_entries.async_update_entry = MagicMock(side_effect=_fake_update)
        # Make data a real dict (not MagicMock) so .get() / mutation work cleanly
        flow._config_entry.data = {
            **flow._config_entry.data,
            CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
        }

        # Step 1: rotate-only credentials submission
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )
        await flow.async_step_credentials({
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
            CONF_REGENERATE_WEBHOOK_SECRET: True,
        })

        # Capture the new secret that was just persisted
        new_secret = flow._config_entry.data[CONF_WEBHOOK_SECRET]
        assert new_secret != "fixed-secret"
        assert len(new_secret) >= 40

        # Step 2: submit categories so the flow advances to finish. The
        # categories step calls async_step_finish() internally to render the
        # URL display form, so the async_generate_url patch must wrap this
        # call too.
        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            side_effect=lambda hass, wid: f"http://ha.local/api/webhook/{wid}",
        ):
            await flow.async_step_categories(cat_input)

        # Inspect the form schema's default URLs — they must contain the NEW secret
        finish_call = flow.async_show_form.call_args_list[-1]
        schema = finish_call.kwargs["data_schema"]
        url_defaults = [
            marker.default()
            for marker in schema.schema
            if isinstance(marker, vol.Optional)
            and isinstance(marker.schema, str)
            and marker.schema.startswith("webhook_url_")
        ]
        assert url_defaults, "Expected at least one webhook_url_* field on the finish step"
        for url in url_defaults:
            assert new_secret in url, (
                f"Finish step displayed an old/wrong token. URL: {url}, "
                f"expected new secret: {new_secret}"
            )


# ---------------------------------------------------------------------------
# CONF_WEBHOOK_ID_SUFFIX generated for new entries (multi-entry collision fix)
# ---------------------------------------------------------------------------


class TestWebhookIdSuffix:
    """Cluster A: new entries must get a per-entry CONF_WEBHOOK_ID_SUFFIX so
    two config entries can never collide on the same webhook ID."""

    @pytest.mark.asyncio
    async def test_user_step_generates_webhook_id_suffix(self) -> None:
        from custom_components.unifi_alerts.const import CONF_WEBHOOK_ID_SUFFIX

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
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False

            await flow.async_step_user(_VALID_INPUT)

        suffix = flow._credentials.get(CONF_WEBHOOK_ID_SUFFIX)
        assert suffix is not None
        assert len(suffix) == 8  # token_hex(4) → 8 hex chars
        assert all(c in "0123456789abcdef" for c in suffix)

    @pytest.mark.asyncio
    async def test_two_distinct_setups_get_distinct_suffixes(self) -> None:
        """Running two independent config flows must produce two distinct suffixes
        (collisions would be vanishingly rare on 32 bits but the test guards
        against accidentally hardcoding the value)."""
        from custom_components.unifi_alerts.const import CONF_WEBHOOK_ID_SUFFIX

        suffixes: list[str] = []
        for _ in range(2):
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
                instance.fetch_alarms = AsyncMock(return_value=[])
                instance._is_unifi_os = False
                await flow.async_step_user(_VALID_INPUT)
            suffixes.append(flow._credentials[CONF_WEBHOOK_ID_SUFFIX])
        assert suffixes[0] != suffixes[1]
