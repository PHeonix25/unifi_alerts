"""Tests for the options flow: basic finish/categories cycle and the credentials step.

Split out of test_options.py (#283) by behaviour area. See
test_options_rotation_validation.py and test_options_helpers.py for the
other pieces.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
)

from .conftest import make_options_flow, make_session_mock


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
        instance.authenticate = AsyncMock(return_value=None)
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
            CONF_API_KEY: "new-key",
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
            instance.authenticate = AsyncMock(return_value=None)
            instance.fetch_alarms = AsyncMock(return_value=[])

            result = await flow.async_step_credentials(new_creds)

        # entry.data must NOT have been persisted yet
        flow.hass.config_entries.async_update_entry.assert_not_called()

        # The pending values must be staged, ready for async_step_finish to commit
        assert flow._pending_data[CONF_CONTROLLER_URL] == "https://10.0.0.1"
        assert flow._pending_data[CONF_API_KEY] == "new-key"

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
            CONF_API_KEY: "bad-key",
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
            instance.authenticate = AsyncMock(return_value=None)
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
            CONF_API_KEY: "new-key",
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
            instance.authenticate = AsyncMock(return_value=None)
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = True

            await flow.async_step_credentials(new_creds)

        # The credentials step must NOT persist eagerly -- the staged data is
        # only committed once async_step_finish runs.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_API_KEY] == "new-key"

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
        assert committed[CONF_API_KEY] == "new-key"
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
            CONF_API_KEY: "new-key",
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
            instance.authenticate = AsyncMock(return_value=None)
            instance.fetch_alarms = AsyncMock(return_value=[])
            instance._is_unifi_os = False
            await flow.async_step_credentials(new_creds)

        # User abandoned the dialog: no further steps invoked.
        # entry.data must NOT have been written. The staged dict holds the
        # change that *would* have been committed if the user had finished.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_API_KEY] == "new-key"

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
        assert flow._pending_data[CONF_API_KEY] == "existing-api-key"
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
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        await flow.async_step_credentials(same_input)
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data == {}


# ---------------------------------------------------------------------------
# Webhook secret rotation in options flow
# ---------------------------------------------------------------------------


class TestOptionsCredentialsErrorsAndStaging:
    @pytest.mark.asyncio
    async def test_credentials_cannot_connect_shows_error(self) -> None:
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "credentials"})
        user_input = {
            CONF_CONTROLLER_URL: "https://10.0.0.1",
            CONF_API_KEY: "new-key",
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
            CONF_API_KEY: "new-key",
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
            instance.authenticate = AsyncMock(return_value=None)
            instance.fetch_alarms = AsyncMock(return_value=[])
            result = await flow.async_step_credentials(user_input)

        assert result["step_id"] == "categories"
        assert flow._pending_data[CONF_API_KEY] == "new-api-key"
