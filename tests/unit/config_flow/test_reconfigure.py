"""Tests for the dedicated reconfigure flow: async_step_reconfigure (#344).

Covers HA's Gold-tier `reconfiguration-flow` quality-scale entry point,
distinct from the options flow's "Configure" step tested in
test_options_credentials.py. async_step_reconfigure reuses the same
credential-validation helpers as the options flow's credentials step, so
these tests mirror the structure of TestOptionsFlowCredentials and
TestReauthConfirmStep in test_reauth.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_VERIFY_SSL,
)

from .conftest import make_reconfigure_flow, make_session_mock


class TestReconfigureStep:
    """Tests for async_step_reconfigure."""

    @pytest.mark.asyncio
    async def test_no_input_shows_form(self) -> None:
        """With no user_input, reconfigure must show the credentials form."""
        flow = make_reconfigure_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reconfigure"})

        result = await flow.async_step_reconfigure(user_input=None)

        assert result["step_id"] == "reconfigure"
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["step_id"] == "reconfigure"
        assert not call_kwargs["errors"]
        assert call_kwargs["description_placeholders"]["current_url"] == "https://192.168.1.1"

    @pytest.mark.asyncio
    async def test_form_offers_credential_fields(self) -> None:
        """The reconfigure form must present controller URL, API key, and verify_ssl fields."""
        flow = make_reconfigure_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reconfigure"})

        await flow.async_step_reconfigure(user_input=None)

        schema = flow.async_show_form.call_args.kwargs["data_schema"]
        field_names = {str(key) for key in schema.schema}
        assert field_names == {CONF_CONTROLLER_URL, CONF_API_KEY, CONF_VERIFY_SSL}

    @pytest.mark.asyncio
    async def test_blank_submission_is_a_noop_abort(self) -> None:
        """All-blank fields with verify_ssl unchanged must abort without updating anything."""
        flow = make_reconfigure_flow()
        flow.async_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )

        blank_input = {
            CONF_CONTROLLER_URL: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,  # matches the fixture's stored value
        }

        result = await flow.async_step_reconfigure(blank_input)

        assert result["reason"] == "reconfigure_successful"
        flow.async_abort.assert_called_once_with(reason="reconfigure_successful")
        flow.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_new_credentials_updates_and_reloads(self) -> None:
        """Submitting valid new credentials must update the entry and reload it."""
        flow = make_reconfigure_flow()
        flow.async_update_reload_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )

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

            result = await flow.async_step_reconfigure(new_creds)

        assert result["reason"] == "reconfigure_successful"
        flow.async_update_reload_and_abort.assert_called_once()
        call = flow.async_update_reload_and_abort.call_args
        assert call.args[0] is flow._get_reconfigure_entry.return_value
        assert call.kwargs["data"][CONF_CONTROLLER_URL] == "https://10.0.0.1"
        assert call.kwargs["data"][CONF_API_KEY] == "new-key"
        assert call.kwargs["unique_id"] == "https://10.0.0.1"
        assert call.kwargs["reason"] == "reconfigure_successful"

    @pytest.mark.asyncio
    async def test_same_url_does_not_pass_unique_id(self) -> None:
        """Updating only the API key (URL unchanged) must not touch unique_id."""
        flow = make_reconfigure_flow()
        flow.async_update_reload_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )

        new_creds = {
            CONF_CONTROLLER_URL: "",
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

            await flow.async_step_reconfigure(new_creds)

        call_kwargs = flow.async_update_reload_and_abort.call_args.kwargs
        assert "unique_id" not in call_kwargs
        assert call_kwargs["data"][CONF_API_KEY] == "new-key"
        assert call_kwargs["data"][CONF_CONTROLLER_URL] == "https://192.168.1.1"

    @pytest.mark.asyncio
    async def test_verify_ssl_only_toggle_updates_without_auth_call(self) -> None:
        """Flipping verify_ssl alone must update the entry without an auth round-trip."""
        flow = make_reconfigure_flow()
        flow.async_update_reload_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )

        ssl_only = {
            CONF_CONTROLLER_URL: "",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: False,  # fixture default is True
        }

        with patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls:
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock()
            result = await flow.async_step_reconfigure(ssl_only)
            instance.authenticate.assert_not_called()

        assert result["reason"] == "reconfigure_successful"
        call_kwargs = flow.async_update_reload_and_abort.call_args.kwargs
        assert call_kwargs["data"][CONF_VERIFY_SSL] is False
        # Other stored fields must be carried over unchanged
        assert call_kwargs["data"][CONF_API_KEY] == "old-api-key"

    @pytest.mark.asyncio
    async def test_invalid_credentials_shows_error_and_does_not_update(self) -> None:
        """Invalid credentials during reconfigure must re-show the form with an error."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = make_reconfigure_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reconfigure"})

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

            result = await flow.async_step_reconfigure(new_creds)

        assert result["step_id"] == "reconfigure"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "invalid_auth"}
        flow.hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_cannot_connect_shows_error(self) -> None:
        """A connection error during reconfigure must show cannot_connect error."""
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = make_reconfigure_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reconfigure"})

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
            instance.authenticate = AsyncMock(side_effect=CannotConnectError("down"))

            result = await flow.async_step_reconfigure(new_creds)

        assert result["step_id"] == "reconfigure"
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_ssl_cert_error_shows_invalid_ssl_cert(self) -> None:
        """SslCertificateError during reconfigure must show invalid_ssl_cert base error."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        flow = make_reconfigure_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reconfigure"})

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
            instance.authenticate = AsyncMock(side_effect=SslCertificateError("cert"))

            result = await flow.async_step_reconfigure(new_creds)

        assert result["step_id"] == "reconfigure"
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "invalid_ssl_cert"}

    @pytest.mark.asyncio
    async def test_invalid_url_scheme_shows_error(self) -> None:
        """A non-http/https URL scheme must show a field-level error without hitting the network."""
        flow = make_reconfigure_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reconfigure"})

        bad_url_input = {
            CONF_CONTROLLER_URL: "ftp://192.168.1.1",
            CONF_API_KEY: "",
            CONF_VERIFY_SSL: True,
        }

        with patch(
            "custom_components.unifi_alerts.config_flow.async_get_clientsession",
            return_value=make_session_mock(),
        ) as mock_session:
            result = await flow.async_step_reconfigure(bad_url_input)

        assert result["step_id"] == "reconfigure"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"].get(CONF_CONTROLLER_URL) == "invalid_url_scheme"
        # No network call should have been made
        mock_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_url_collision_aborts(self) -> None:
        """Changing to a URL already used by another entry must abort with already_configured."""
        flow = make_reconfigure_flow()

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

            result = await flow.async_step_reconfigure(new_creds)

        assert result["reason"] == "already_configured"
        flow.hass.config_entries.async_update_entry.assert_not_called()
