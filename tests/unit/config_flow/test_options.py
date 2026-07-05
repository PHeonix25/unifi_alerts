"""Tests for the options flow: credential changes, category toggles, regenerate secret."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
)

from .conftest import make_options_flow, make_session_mock

# ---------------------------------------------------------------------------
# Basic options flow tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_finish_includes_webhook_urls() -> None:
    """Options flow finish step should include webhook URL fields with the stored secret."""
    fake_secret = "options-test-secret"
    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: fake_secret}
    config_entry.options = {}

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

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

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

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

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

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
    """Full options flow: blank credentials -> categories -> finish -> create_entry."""
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

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

    flow = UniFiAlertsOptionsFlow(config_entry)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_update_entry = MagicMock()
    flow.hass = hass
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    # Step 1: blank credentials -> skip to categories
    blank_creds = {
        CONF_CONTROLLER_URL: "",
        CONF_USERNAME: "",
        CONF_PASSWORD: "",
        CONF_API_KEY: "",
        CONF_VERIFY_SSL: True,
    }
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

    # Step 3: submit finish -> create_entry
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
    # entry.options has the values from the last options save -- these must win
    saved_poll = 120
    saved_clear = 60
    saved_enabled = [ALL_CATEGORIES[0]]
    config_entry.options = {
        CONF_ENABLED_CATEGORIES: saved_enabled,
        CONF_POLL_INTERVAL: saved_poll,
        CONF_CLEAR_TIMEOUT: saved_clear,
    }

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

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
async def test_options_flow_saves_submitted_values() -> None:
    """Submitting the options flow (categories -> finish) must persist the selected categories and intervals."""
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

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

    # Only enable first category; set custom poll, clear, and site values
    first_cat = ALL_CATEGORIES[0]
    user_input = {f"cat_{cat}": (cat == first_cat) for cat in ALL_CATEGORIES}
    user_input[CONF_POLL_INTERVAL] = 300
    user_input[CONF_CLEAR_TIMEOUT] = 60
    user_input[CONF_SITE] = "secondary"

    # Submit categories (stores in _pending_options, routes to finish).
    # CONF_SITE = "secondary" triggers site validation, so mock the client.
    with (
        patch(
            "custom_components.unifi_alerts.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ),
    ):
        instance = mock_cls.return_value
        instance.authenticate = AsyncMock(return_value="apikey")
        instance.fetch_alarms = AsyncMock(return_value=[])
        await flow.async_step_categories(user_input)

    # Submit finish -> creates entry
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
async def test_options_flow_rejects_all_disabled() -> None:
    """Options flow must show error when all categories are unchecked."""
    config_entry = MagicMock()
    config_entry.data = {CONF_ENABLED_CATEGORIES: ALL_CATEGORIES, CONF_WEBHOOK_SECRET: "s"}
    config_entry.options = {}

    from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

    flow = UniFiAlertsOptionsFlow(config_entry)
    flow.hass = MagicMock()
    flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

    all_off = {f"cat_{cat}": False for cat in ALL_CATEGORIES}
    result = await flow.async_step_categories(all_off)

    assert result["step_id"] == "categories"
    call_kwargs = flow.async_show_form.call_args.kwargs
    assert call_kwargs["errors"] == {"base": "at_least_one_category"}


# ---------------------------------------------------------------------------
# Options flow -- credentials step
# ---------------------------------------------------------------------------


class TestOptionsFlowCredentials:
    """Tests for the credentials step in the options flow."""

    @pytest.mark.asyncio
    async def test_init_routes_to_credentials_step(self) -> None:
        """Opening the options flow (async_step_init) should show the credentials step first."""
        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})

        result = await flow.async_step_init(user_input=None)

        assert result["step_id"] == "credentials"
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["step_id"] == "credentials"

    @pytest.mark.asyncio
    async def test_blank_submission_skips_to_categories(self) -> None:
        """Submitting all-blank credentials skips to the categories step without any auth call."""
        flow = make_options_flow()
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
    async def test_valid_new_credentials_stages_entry_data(self) -> None:
        """Submitting new valid credentials must STAGE entry.data and continue to categories.

        Persistence is deferred to async_step_finish so abandoning the flow
        between credentials and finish leaves the original entry untouched.
        """
        flow = make_options_flow()
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
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False

            result = await flow.async_step_credentials(new_creds)

        # entry.data must NOT have been persisted yet
        flow.hass.config_entries.async_update_entry.assert_not_called()

        # The pending values must be staged, ready for async_step_finish to commit
        assert flow._pending_data[CONF_CONTROLLER_URL] == "https://10.0.0.1"
        assert flow._pending_data[CONF_PASSWORD] == "newpass"

        # Should have continued to categories
        assert result["step_id"] == "categories"

    @pytest.mark.asyncio
    async def test_invalid_credentials_shows_error_and_does_not_update(self) -> None:
        """When the new credentials fail auth, show invalid_auth and do NOT update entry.data."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})

        new_creds = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "baduser",
            CONF_PASSWORD: "wrongpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

            result = await flow.async_step_credentials(new_creds)

        assert result["step_id"] == "credentials"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "invalid_auth"}
        # entry.data must NOT have been touched and nothing should be staged
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data == {}

    @pytest.mark.asyncio
    async def test_invalid_url_scheme_shows_error(self) -> None:
        """A non-http/https URL scheme must show a field-level error without hitting the network."""
        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})

        bad_url_input = {
            CONF_CONTROLLER_URL: "ftp://192.168.1.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with patch(
            "custom_components.unifi_alerts.config_flow.async_get_clientsession",
            return_value=make_session_mock(),
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
        flow = make_options_flow(url="https://192.168.1.1")

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
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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
        assert flow._pending_data == {}

    @pytest.mark.asyncio
    async def test_after_credential_update_categories_proceeds_normally(self) -> None:
        """After a successful credentials update, categories -> finish -> create_entry works end-to-end."""
        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

        flow = make_options_flow()
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
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = True

            await flow.async_step_credentials(new_creds)

        # The credentials step must NOT persist eagerly -- the staged data is
        # only committed once async_step_finish runs.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_USERNAME] == "newadmin"

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

        # Submit finish -> create_entry. entry.data is now persisted atomically.
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        flow.hass.config_entries.async_update_entry.assert_called_once()
        committed = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert committed[CONF_USERNAME] == "newadmin"
        saved = flow.async_create_entry.call_args.kwargs["data"]
        assert saved[CONF_ENABLED_CATEGORIES] == [first_cat]
        assert saved[CONF_POLL_INTERVAL] == 90
        assert saved[CONF_CLEAR_TIMEOUT] == 15

    @pytest.mark.asyncio
    async def test_abandoning_flow_after_credentials_does_not_persist(self) -> None:
        """Submitting valid credentials and then abandoning the flow before
        finish must leave entry.data untouched.

        Regression guard for the v1.5 atomicity fix: prior to v1.5,
        async_step_credentials called async_update_entry eagerly so closing
        the dialog at the categories step left the new password persisted.
        """
        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        new_creds = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "newadmin",
            CONF_PASSWORD: "newpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False
            await flow.async_step_credentials(new_creds)

        # User abandoned the dialog: no further steps invoked.
        # entry.data must NOT have been written. The staged dict holds the
        # change that *would* have been committed if the user had finished.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_PASSWORD] == "newpass"

    @pytest.mark.asyncio
    async def test_verify_ssl_only_toggle_stages_and_skips_auth(self) -> None:
        """Flipping verify_ssl with no other changes must stage the new value
        and skip the auth call -- credentials_changed is False here.

        Regression guard: prior to v1.5 the verify_ssl flag was filtered out
        of the change-detection check, so toggling it alone was a silent no-op.
        """
        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})
        # Fixture default is verify_ssl=True; flip to False
        ssl_only = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: False,
        }

        with patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls:
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock()
            await flow.async_step_credentials(ssl_only)
            instance.authenticate.assert_not_called()

        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_VERIFY_SSL] is False
        # Other entry-data keys must be carried over unchanged
        assert flow._pending_data[CONF_USERNAME] == "admin"
        assert flow._pending_data[CONF_WEBHOOK_SECRET] == "fixed-secret"

    @pytest.mark.asyncio
    async def test_verify_ssl_only_toggle_persists_on_finish(self) -> None:
        """End-to-end: a verify_ssl flip submitted through to finish must call
        async_update_entry with the new value."""
        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

        flow = make_options_flow()
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        await flow.async_step_credentials(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: False,
            }
        )

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_POLL_INTERVAL] = 60
        cat_input[CONF_CLEAR_TIMEOUT] = 5
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            await flow.async_step_categories(cat_input)
            await flow.async_step_finish(user_input={})

        flow.hass.config_entries.async_update_entry.assert_called_once()
        committed = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert committed[CONF_VERIFY_SSL] is False

    @pytest.mark.asyncio
    async def test_verify_ssl_unchanged_no_op_skips_persist(self) -> None:
        """Submitting credentials with verify_ssl matching the stored value and
        no other fields must skip persistence entirely (no staged data)."""
        flow = make_options_flow()  # entry has verify_ssl=True
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        same_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        await flow.async_step_credentials(same_input)
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data == {}


# ---------------------------------------------------------------------------
# Webhook secret rotation in options flow
# ---------------------------------------------------------------------------


class TestWebhookSecretRotation:
    """Users must be able to regenerate the webhook secret without deleting and
    re-adding the integration.

    The options flow's credentials step exposes a CONF_REGENERATE_WEBHOOK_SECRET
    checkbox. When ticked:
    - With no other credential changes: persist a new secret and continue.
    - With credential changes: persist new credentials AND new secret atomically.
    """

    @pytest.mark.asyncio
    async def test_rotate_only_stages_new_secret_and_skips_auth(self) -> None:
        """Ticking only the regenerate checkbox must NOT call authenticate()
        and must NOT persist eagerly -- the new secret is staged for the
        finish step to commit atomically."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = make_options_flow()
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

        # No persistence at this stage; the secret is staged.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        # New secret must differ from the fixture-installed one
        assert flow._pending_data[CONF_WEBHOOK_SECRET] != "fixed-secret"
        # And it must be a non-empty token (token_urlsafe(32) is at least 40 chars)
        assert len(flow._pending_data[CONF_WEBHOOK_SECRET]) >= 40

    @pytest.mark.asyncio
    async def test_rotate_with_credential_change_stages_both(self) -> None:
        """Ticking regenerate alongside new creds stages the rotated secret AND new creds."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = make_options_flow()
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
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False
            await flow.async_step_credentials(new_input)

        # No eager persistence; staged for finish.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_PASSWORD] == "newpass"
        assert flow._pending_data[CONF_WEBHOOK_SECRET] != "fixed-secret"

    @pytest.mark.asyncio
    async def test_unticked_does_not_rotate(self) -> None:
        """If the checkbox is unset, the existing secret must remain intact."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = make_options_flow()
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
        # No update or staging at all because nothing changed
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data == {}

    @pytest.mark.asyncio
    async def test_finish_step_displays_new_url_after_rotation(self) -> None:
        """After secret rotation is staged, the finish step must show URLs with
        the NEW token even though entry.data has not been written yet.

        Under the staged-persistence model the finish step renders from
        ``self._pending_data`` until the user submits, so the displayed URLs
        match what the entry WILL contain after submit. If a regression made
        the finish step read straight from ``self._config_entry.data`` again,
        the user would see the OLD token alongside a regenerate confirmation:
        a confusing UX bug.
        """
        from custom_components.unifi_alerts.const import (
            CONF_REGENERATE_WEBHOOK_SECRET,
            CONF_WEBHOOK_ID_SUFFIX,
        )

        flow = make_options_flow()

        # Make data a real dict (not MagicMock) so .get() / mutation work cleanly
        flow._config_entry.data = {
            **flow._config_entry.data,
            CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
        }

        # Step 1: rotate-only credentials submission
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )
        await flow.async_step_credentials(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
                CONF_REGENERATE_WEBHOOK_SECRET: True,
            }
        )

        # Staged but not persisted: entry.data still holds the old secret.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        new_secret = flow._pending_data[CONF_WEBHOOK_SECRET]
        assert new_secret != "fixed-secret"
        assert len(new_secret) >= 40
        assert flow._config_entry.data[CONF_WEBHOOK_SECRET] == "fixed-secret"

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

        # Inspect the form schema's default URLs -- they must contain the NEW secret
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


class TestWebhookSecretRotationRepairIssue:
    """The finish step must create a repair issue when the secret was rotated,
    and must NOT create one when the secret is unchanged."""

    @pytest.mark.asyncio
    async def test_finish_submit_with_rotation_creates_repair_issue(self) -> None:
        """Submitting finish after a secret rotation creates the repair issue."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = make_options_flow()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )

        # Stage a rotation via the credentials step
        await flow.async_step_credentials(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
                CONF_REGENERATE_WEBHOOK_SECRET: True,
            }
        )
        new_secret = flow._pending_data[CONF_WEBHOOK_SECRET]
        assert new_secret != "fixed-secret"

        # Advance to categories, then submit finish
        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            side_effect=lambda hass, wid: f"http://ha.local/api/webhook/{wid}",
        ):
            await flow.async_step_categories(cat_input)

        with patch("custom_components.unifi_alerts.config_flow.ir") as mock_ir:
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        mock_ir.async_create_issue.assert_called_once()
        call_kwargs = mock_ir.async_create_issue.call_args.kwargs
        assert call_kwargs["translation_key"] == "webhook_secret_rotated"
        assert "webhook_secret_rotated_" in mock_ir.async_create_issue.call_args.args[2]

    @pytest.mark.asyncio
    async def test_finish_submit_without_rotation_does_not_create_repair_issue(self) -> None:
        """Submitting finish without a secret rotation must NOT create the repair issue."""
        from custom_components.unifi_alerts.const import (
            CONF_CLEAR_TIMEOUT,
            CONF_POLL_INTERVAL,
            CONF_SITE,
        )

        flow = make_options_flow()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        flow._pending_options = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 5,
            CONF_SITE: "default",
        }
        # _pending_data is empty: no credential/secret changes staged
        flow._pending_data = {}

        with patch("custom_components.unifi_alerts.config_flow.ir") as mock_ir:
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        mock_ir.async_create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_finish_submit_with_non_secret_data_change_does_not_create_repair_issue(
        self,
    ) -> None:
        """Changing credentials without rotating the secret must NOT create the repair issue."""
        from custom_components.unifi_alerts.const import (
            CONF_CLEAR_TIMEOUT,
            CONF_POLL_INTERVAL,
            CONF_SITE,
        )

        flow = make_options_flow()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        flow._pending_options = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_POLL_INTERVAL: 60,
            CONF_CLEAR_TIMEOUT: 5,
            CONF_SITE: "default",
        }
        # _pending_data has a new username but the SAME secret
        flow._pending_data = {
            CONF_USERNAME: "new-admin",
            CONF_WEBHOOK_SECRET: "fixed-secret",
        }

        with patch("custom_components.unifi_alerts.config_flow.ir") as mock_ir:
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        mock_ir.async_create_issue.assert_not_called()


class TestOptionsFlowUniqueIdFollowsUrl:
    """The config entry's unique_id must track the controller URL (issue #276).

    Prior to the fix, async_step_finish persisted entry.data with the new
    controller URL but never passed unique_id= to async_update_entry, so the
    entry's unique_id stayed pinned to whatever URL was used at initial setup.
    That left duplicate-prevention and SSDP discovery matching (both keyed on
    unique_id) looking at a stale URL after a re-point.
    """

    @pytest.mark.asyncio
    async def test_url_change_updates_entry_unique_id(self) -> None:
        """Changing the controller URL through the options flow must update
        entry.unique_id to the new URL when finish is submitted."""
        flow = make_options_flow(url="https://192.168.1.1")
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        new_creds = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False
            await flow.async_step_credentials(new_creds)

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            await flow.async_step_categories(cat_input)
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
        assert call_kwargs["unique_id"] == "https://10.0.0.1"
        assert call_kwargs["data"][CONF_CONTROLLER_URL] == "https://10.0.0.1"

    @pytest.mark.asyncio
    async def test_unchanged_url_leaves_unique_id_untouched(self) -> None:
        """Rotating only verify_ssl/secret (URL untouched) must NOT pass
        unique_id= to async_update_entry."""
        flow = make_options_flow(url="https://192.168.1.1")
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        ssl_only = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: False,
        }
        await flow.async_step_credentials(ssl_only)

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            await flow.async_step_categories(cat_input)
            result = await flow.async_step_finish(user_input={})

        assert result["type"] == "create_entry"
        flow.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
        assert "unique_id" not in call_kwargs
        assert call_kwargs["data"][CONF_CONTROLLER_URL] == "https://192.168.1.1"

    @pytest.mark.asyncio
    async def test_url_change_unique_id_does_not_collide_with_another_entry(self) -> None:
        """The new unique_id must not collide with another entry's URL.

        _find_duplicate_entry already runs in async_step_credentials and
        aborts before staging if the new URL matches ANOTHER entry's
        entry.data[CONF_CONTROLLER_URL] -- so by the time async_step_finish
        runs and sets unique_id=new_url, no other entry can already be using
        that URL/unique_id.
        """
        from custom_components.unifi_alerts.config_flow import _find_duplicate_entry

        flow = make_options_flow(url="https://192.168.1.1")
        flow.async_show_form = MagicMock(
            side_effect=lambda **kwargs: {"type": "form", "step_id": kwargs["step_id"]}
        )
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        other_entry = MagicMock()
        other_entry.entry_id = "other-entry"
        other_entry.data = {CONF_CONTROLLER_URL: "https://172.16.0.1"}
        flow.hass.config_entries.async_entries = MagicMock(return_value=[other_entry])

        new_creds = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False
            result = await flow.async_step_credentials(new_creds)

        # Not aborted -- the new URL doesn't collide with the other entry.
        assert result["step_id"] == "categories"

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        with patch(
            "custom_components.unifi_alerts.config_flow.async_generate_url",
            return_value="http://ha.local/webhook/x",
        ):
            await flow.async_step_categories(cat_input)
            await flow.async_step_finish(user_input={})

        call_kwargs = flow.hass.config_entries.async_update_entry.call_args.kwargs
        new_unique_id = call_kwargs["unique_id"]
        assert new_unique_id == "https://10.0.0.1"
        # Confirm the helper that gated staging would still find no collision
        # for the URL that just became the entry's unique_id.
        assert _find_duplicate_entry(flow.hass, flow._config_entry.entry_id, new_unique_id) is None


class TestOptionsCredentialsErrorsAndStaging:
    @pytest.mark.asyncio
    async def test_credentials_cannot_connect_shows_error(self) -> None:
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})
        user_input = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "newpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=CannotConnectError("down"))
            result = await flow.async_step_credentials(user_input)

        assert result["step_id"] == "credentials"
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_credentials_ssl_cert_error_shows_invalid_ssl_cert(self) -> None:
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})
        user_input = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_USERNAME: "",
            CONF_PASSWORD: "newpass",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=SslCertificateError("cert"))
            result = await flow.async_step_credentials(user_input)

        assert result["step_id"] == "credentials"
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "invalid_ssl_cert"}

    @pytest.mark.asyncio
    async def test_credentials_stages_api_key_update(self) -> None:
        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})
        user_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "new-api-key",
            CONF_VERIFY_SSL: True,
        }

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="apikey")
            instance.fetch_alarms = AsyncMock(return_value=[])
            result = await flow.async_step_credentials(user_input)

        assert result["step_id"] == "categories"
        assert flow._pending_data[CONF_API_KEY] == "new-api-key"


class TestOptionsFlowSiteValidation:
    """Site validation in the options flow categories step."""

    @pytest.mark.asyncio
    async def test_invalid_site_shows_error(self) -> None:
        """A non-default site that does not exist shows invalid_site on the site field."""
        from custom_components.unifi_alerts.const import CONF_SITE
        from custom_components.unifi_alerts.unifi_client import InvalidSiteError

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_SITE] = "bogus-site"

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="apikey")
            instance.fetch_alarms = AsyncMock(
                side_effect=InvalidSiteError("Site 'bogus-site' not found")
            )
            result = await flow.async_step_categories(cat_input)

        assert result["step_id"] == "categories"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"].get(CONF_SITE) == "invalid_site"

    @pytest.mark.asyncio
    async def test_default_site_skips_validation(self) -> None:
        """Keeping the default site skips the extra network call."""
        from custom_components.unifi_alerts.const import CONF_SITE, DEFAULT_SITE

        flow = make_options_flow()
        flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_SITE] = DEFAULT_SITE

        with patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls:
            result = await flow.async_step_categories(cat_input)

        mock_cls.assert_not_called()
        assert result["step_id"] == "finish"

    @pytest.mark.asyncio
    async def test_valid_non_default_site_proceeds_to_finish(self) -> None:
        """A non-default site that validates successfully proceeds to the finish step."""
        from custom_components.unifi_alerts.const import CONF_SITE

        flow = make_options_flow()
        flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_SITE] = "myhome"

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="apikey")
            instance.fetch_alarms = AsyncMock(return_value=[])
            result = await flow.async_step_categories(cat_input)

        assert result["step_id"] == "finish"
        assert flow._pending_options[CONF_SITE] == "myhome"

    @pytest.mark.asyncio
    async def test_site_validation_uses_pending_data_when_credentials_changed(self) -> None:
        """Site validation must use pending_data credentials (from step 1) if set."""
        from custom_components.unifi_alerts.const import CONF_SITE

        flow = make_options_flow()
        flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})
        flow._pending_data = {
            **flow._config_entry.data,
            CONF_CONTROLLER_URL: "https://10.0.0.2",
        }

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_SITE] = "newsite"

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="apikey")
            instance.fetch_alarms = AsyncMock(return_value=[])
            result = await flow.async_step_categories(cat_input)

        # Client must have been created with the pending (updated) controller URL
        call_args = mock_cls.call_args
        assert call_args.args[1] == "https://10.0.0.2"
        assert result["step_id"] == "finish"

    @pytest.mark.asyncio
    async def test_cannot_connect_during_site_validation_shows_error(self) -> None:
        """A CannotConnectError during site validation maps to cannot_connect base error."""
        from custom_components.unifi_alerts.const import CONF_SITE
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_SITE] = "sitename"

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="apikey")
            instance.fetch_alarms = AsyncMock(side_effect=CannotConnectError("Connection refused"))
            result = await flow.async_step_categories(cat_input)

        assert result["step_id"] == "categories"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"].get("base") == "cannot_connect"


# ---------------------------------------------------------------------------
# Extracted credentials-step helpers (issue #238)
#
# async_step_credentials was refactored into a thin orchestrator that calls
# these standalone functions. The tests above already cover the orchestrator
# end to end; the tests below exercise each helper in isolation so logic
# like duplicate-entry detection and URL validation doesn't require driving
# the full flow step.
# ---------------------------------------------------------------------------


class TestParseCredentialsFormInput:
    """Tests for _parse_credentials_form_input, the pure input-normalization helper."""

    def test_blank_input_reports_no_changes(self) -> None:
        from custom_components.unifi_alerts.config_flow import _parse_credentials_form_input

        current_data = {CONF_VERIFY_SSL: True}
        blank_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        parsed = _parse_credentials_form_input(blank_input, current_data)

        assert parsed.credentials_changed is False
        assert parsed.verify_ssl_changed is False
        assert parsed.regenerate_secret is False

    def test_whitespace_only_fields_are_stripped_to_blank(self) -> None:
        from custom_components.unifi_alerts.config_flow import _parse_credentials_form_input

        current_data = {CONF_VERIFY_SSL: True}
        whitespace_input = {
            CONF_CONTROLLER_URL: "   ",
            CONF_USERNAME: "  ",
            CONF_PASSWORD: " ",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        parsed = _parse_credentials_form_input(whitespace_input, current_data)

        assert parsed.new_url_raw == ""
        assert parsed.new_username == ""
        assert parsed.new_password == ""
        assert parsed.credentials_changed is False

    def test_url_change_marks_credentials_changed(self) -> None:
        from custom_components.unifi_alerts.config_flow import _parse_credentials_form_input

        current_data = {CONF_VERIFY_SSL: True}
        user_input = {
            CONF_CONTROLLER_URL: "https://10.0.0.5",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        parsed = _parse_credentials_form_input(user_input, current_data)

        assert parsed.credentials_changed is True
        assert parsed.new_url_raw == "https://10.0.0.5"

    def test_verify_ssl_change_is_detected_against_current_data(self) -> None:
        from custom_components.unifi_alerts.config_flow import _parse_credentials_form_input

        current_data = {CONF_VERIFY_SSL: True}
        user_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: False,
        }

        parsed = _parse_credentials_form_input(user_input, current_data)

        assert parsed.verify_ssl_changed is True
        assert parsed.new_verify_ssl is False
        assert parsed.credentials_changed is False

    def test_verify_ssl_defaults_to_current_value_when_absent(self) -> None:
        from custom_components.unifi_alerts.config_flow import _parse_credentials_form_input

        current_data = {CONF_VERIFY_SSL: False}
        user_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
        }

        parsed = _parse_credentials_form_input(user_input, current_data)

        assert parsed.new_verify_ssl is False
        assert parsed.verify_ssl_changed is False

    def test_regenerate_secret_flag_is_parsed(self) -> None:
        from custom_components.unifi_alerts.config_flow import _parse_credentials_form_input
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        current_data = {CONF_VERIFY_SSL: True}
        user_input = {
            CONF_CONTROLLER_URL: "",
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
            CONF_REGENERATE_WEBHOOK_SECRET: True,
        }

        parsed = _parse_credentials_form_input(user_input, current_data)

        assert parsed.regenerate_secret is True
        assert parsed.credentials_changed is False


class TestIsValidUrlScheme:
    """Tests for _is_valid_url_scheme, the pure URL scheme-validation helper."""

    @pytest.mark.parametrize("url", ["https://192.168.1.1", "http://192.168.1.1"])
    def test_accepts_http_and_https(self, url: str) -> None:
        from custom_components.unifi_alerts.config_flow import _is_valid_url_scheme

        assert _is_valid_url_scheme(url) is True

    @pytest.mark.parametrize("url", ["ftp://192.168.1.1", "ws://192.168.1.1", "not-a-url"])
    def test_rejects_other_schemes(self, url: str) -> None:
        from custom_components.unifi_alerts.config_flow import _is_valid_url_scheme

        assert _is_valid_url_scheme(url) is False

    def test_accepts_loopback_and_link_local_hosts(self) -> None:
        """Same trust model as async_step_user: only the scheme is validated."""
        from custom_components.unifi_alerts.config_flow import _is_valid_url_scheme

        assert _is_valid_url_scheme("http://127.0.0.1") is True
        assert _is_valid_url_scheme("https://169.254.1.1") is True


class TestFindDuplicateEntry:
    """Tests for _find_duplicate_entry, the pure(ish) duplicate-detection helper."""

    def test_returns_none_when_no_entries_exist(self) -> None:
        from custom_components.unifi_alerts.config_flow import _find_duplicate_entry

        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[])

        result = _find_duplicate_entry(hass, "current-id", "https://10.0.0.1")

        assert result is None

    def test_returns_none_when_only_match_is_self(self) -> None:
        from custom_components.unifi_alerts.config_flow import _find_duplicate_entry

        self_entry = MagicMock()
        self_entry.entry_id = "current-id"
        self_entry.data = {CONF_CONTROLLER_URL: "https://10.0.0.1"}

        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[self_entry])

        result = _find_duplicate_entry(hass, "current-id", "https://10.0.0.1")

        assert result is None

    def test_returns_other_entry_when_url_collides(self) -> None:
        from custom_components.unifi_alerts.config_flow import _find_duplicate_entry

        other_entry = MagicMock()
        other_entry.entry_id = "other-id"
        other_entry.data = {CONF_CONTROLLER_URL: "https://10.0.0.1"}

        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[other_entry])

        result = _find_duplicate_entry(hass, "current-id", "https://10.0.0.1")

        assert result is other_entry

    def test_returns_none_when_urls_differ(self) -> None:
        from custom_components.unifi_alerts.config_flow import _find_duplicate_entry

        other_entry = MagicMock()
        other_entry.entry_id = "other-id"
        other_entry.data = {CONF_CONTROLLER_URL: "https://10.0.0.2"}

        hass = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[other_entry])

        result = _find_duplicate_entry(hass, "current-id", "https://10.0.0.1")

        assert result is None


class TestCredentialOverrides:
    """Tests for _credential_overrides, the sparse-dict merge helper."""

    def test_blank_fields_are_omitted(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _credential_overrides,
            _parse_credentials_form_input,
        )

        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
            },
            {CONF_VERIFY_SSL: True},
        )

        assert _credential_overrides(parsed) == {}

    def test_only_populated_fields_are_included(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _credential_overrides,
            _parse_credentials_form_input,
        )

        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "newpass",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
            },
            {CONF_VERIFY_SSL: True},
        )

        assert _credential_overrides(parsed) == {CONF_PASSWORD: "newpass"}


class TestBuildVerifySslAndSecretOnlyPending:
    """Tests for _build_verify_ssl_and_secret_only_pending."""

    def test_verify_ssl_flip_only_carries_over_other_fields(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _build_verify_ssl_and_secret_only_pending,
            _parse_credentials_form_input,
        )

        current_data = {
            CONF_CONTROLLER_URL: "https://192.168.1.1",
            CONF_USERNAME: "admin",
            CONF_VERIFY_SSL: True,
            CONF_WEBHOOK_SECRET: "fixed-secret",
        }
        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: False,
            },
            current_data,
        )

        pending = _build_verify_ssl_and_secret_only_pending(current_data, parsed)

        assert pending[CONF_VERIFY_SSL] is False
        assert pending[CONF_USERNAME] == "admin"
        assert pending[CONF_WEBHOOK_SECRET] == "fixed-secret"

    def test_regenerate_secret_replaces_webhook_secret(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _build_verify_ssl_and_secret_only_pending,
            _parse_credentials_form_input,
        )
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        current_data = {CONF_VERIFY_SSL: True, CONF_WEBHOOK_SECRET: "fixed-secret"}
        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "",
                CONF_USERNAME: "",
                CONF_PASSWORD: "",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
                CONF_REGENERATE_WEBHOOK_SECRET: True,
            },
            current_data,
        )

        pending = _build_verify_ssl_and_secret_only_pending(current_data, parsed)

        assert pending[CONF_WEBHOOK_SECRET] != "fixed-secret"


class TestBuildCredentialsTestData:
    """Tests for _build_credentials_test_data, used to validate new credentials
    against the controller before staging them."""

    def test_merges_new_url_and_overrides_over_current_data(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _build_credentials_test_data,
            _parse_credentials_form_input,
        )

        current_data = {
            CONF_CONTROLLER_URL: "https://192.168.1.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "oldpass",
            CONF_VERIFY_SSL: True,
        }
        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "https://10.0.0.1",
                CONF_USERNAME: "",
                CONF_PASSWORD: "newpass",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
            },
            current_data,
        )

        test_data = _build_credentials_test_data(current_data, "https://10.0.0.1", parsed)

        assert test_data[CONF_CONTROLLER_URL] == "https://10.0.0.1"
        assert test_data[CONF_PASSWORD] == "newpass"
        # Username was left blank, so the stored value carries over unchanged
        assert test_data[CONF_USERNAME] == "admin"


class TestBuildCredentialsPendingData:
    """Tests for _build_credentials_pending_data, used to stage entry.data
    after new credentials validate successfully."""

    def test_includes_auth_method_and_overrides(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _build_credentials_pending_data,
            _parse_credentials_form_input,
        )
        from custom_components.unifi_alerts.const import CONF_AUTH_METHOD

        current_data = {
            CONF_CONTROLLER_URL: "https://192.168.1.1",
            CONF_VERIFY_SSL: True,
            CONF_WEBHOOK_SECRET: "fixed-secret",
        }
        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "https://10.0.0.1",
                CONF_USERNAME: "",
                CONF_PASSWORD: "newpass",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
            },
            current_data,
        )

        pending = _build_credentials_pending_data(
            current_data, "https://10.0.0.1", "userpass", parsed
        )

        assert pending[CONF_CONTROLLER_URL] == "https://10.0.0.1"
        assert pending[CONF_AUTH_METHOD] == "userpass"
        assert pending[CONF_PASSWORD] == "newpass"
        # No rotation requested, so the secret carries over unchanged
        assert pending[CONF_WEBHOOK_SECRET] == "fixed-secret"

    def test_regenerate_secret_alongside_credential_change(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _build_credentials_pending_data,
            _parse_credentials_form_input,
        )
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        current_data = {
            CONF_CONTROLLER_URL: "https://192.168.1.1",
            CONF_VERIFY_SSL: True,
            CONF_WEBHOOK_SECRET: "fixed-secret",
        }
        parsed = _parse_credentials_form_input(
            {
                CONF_CONTROLLER_URL: "https://10.0.0.1",
                CONF_USERNAME: "",
                CONF_PASSWORD: "newpass",
                CONF_API_KEY: "",
                CONF_VERIFY_SSL: True,
                CONF_REGENERATE_WEBHOOK_SECRET: True,
            },
            current_data,
        )

        pending = _build_credentials_pending_data(
            current_data, "https://10.0.0.1", "userpass", parsed
        )

        assert pending[CONF_WEBHOOK_SECRET] != "fixed-secret"


class TestAsyncValidateControllerCredentials:
    """Tests for _async_validate_controller_credentials, the extracted API-validation helper."""

    @pytest.mark.asyncio
    async def test_returns_auth_method_on_success(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _async_validate_controller_credentials,
        )

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ) as mock_get_session,
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="apikey")
            instance.fetch_alarms = AsyncMock(return_value=[])

            auth_method = await _async_validate_controller_credentials(
                MagicMock(), "https://10.0.0.1", True, {CONF_API_KEY: "key"}
            )

        assert auth_method == "apikey"
        mock_get_session.assert_called_once()
        instance.authenticate.assert_awaited_once()
        instance.fetch_alarms.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_auth_error_propagates_unchanged(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _async_validate_controller_credentials,
        )
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=InvalidAuthError("bad creds"))

            with pytest.raises(InvalidAuthError):
                await _async_validate_controller_credentials(
                    MagicMock(), "https://10.0.0.1", True, {}
                )

    @pytest.mark.asyncio
    async def test_ssl_certificate_error_propagates_unchanged(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _async_validate_controller_credentials,
        )
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=SslCertificateError("cert"))

            with pytest.raises(SslCertificateError):
                await _async_validate_controller_credentials(
                    MagicMock(), "https://10.0.0.1", True, {}
                )

    @pytest.mark.asyncio
    async def test_cannot_connect_error_propagates_unchanged(self) -> None:
        from custom_components.unifi_alerts.config_flow import (
            _async_validate_controller_credentials,
        )
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(side_effect=CannotConnectError("down"))

            with pytest.raises(CannotConnectError):
                await _async_validate_controller_credentials(
                    MagicMock(), "https://10.0.0.1", True, {}
                )
