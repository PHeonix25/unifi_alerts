"""Tests for the reauth flow: async_step_reauth, async_step_reauth_confirm, repair issue."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.config_flow import UniFiAlertsConfigFlow
from custom_components.unifi_alerts.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
)

from .conftest import make_reauth_flow, make_session_mock


class TestReauthStep:
    """Tests for async_step_reauth and the auth-failure issue helper."""

    @pytest.mark.asyncio
    async def test_routes_to_reauth_confirm(self) -> None:
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

        with patch("custom_components.unifi_alerts.config_flow._create_auth_failed_issue"):
            result = await flow.async_step_reauth({})

        assert result == confirm_result
        assert flow._reauth_entry is mock_entry

    @pytest.mark.asyncio
    async def test_creates_issue(self) -> None:
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

    def test_create_auth_failed_issue_calls_issue_registry(self) -> None:
        from custom_components.unifi_alerts.config_flow import _create_auth_failed_issue

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "entry-1"
        entry.title = "Controller"

        with patch(
            "custom_components.unifi_alerts.config_flow.ir.async_create_issue"
        ) as mock_create:
            _create_auth_failed_issue(hass, entry)

        mock_create.assert_called_once()
        assert mock_create.call_args.args[2] == "auth_failed_entry-1"


class TestReauthConfirmStep:
    """Tests for async_step_reauth_confirm."""

    @pytest.mark.asyncio
    async def test_no_input_shows_form(self) -> None:
        """With no user_input, reauth_confirm must show the credential form."""
        flow = make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        result = await flow.async_step_reauth_confirm(user_input=None)

        assert result["step_id"] == "reauth_confirm"
        flow.async_show_form.assert_called_once()
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["step_id"] == "reauth_confirm"
        assert not call_kwargs["errors"]

    @pytest.mark.asyncio
    async def test_valid_credentials_updates_entry_and_aborts(self) -> None:
        """Valid credentials must update entry.data and abort with reauth_successful."""
        flow = make_reauth_flow()
        flow.async_abort = MagicMock(return_value={"type": "abort", "reason": "reauth_successful"})

        new_creds = {CONF_USERNAME: "admin", CONF_PASSWORD: "newpassword"}

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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
    async def test_invalid_credentials_shows_error(self) -> None:
        """Invalid credentials must re-show the form with invalid_auth error."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        new_creds = {CONF_USERNAME: "admin", CONF_PASSWORD: "wrongpassword"}

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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
    async def test_cannot_connect_shows_error(self) -> None:
        """A connection error during reauth must show cannot_connect error."""
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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
    async def test_ssl_cert_error_shows_invalid_ssl_cert(self) -> None:
        """SslCertificateError during reauth must show invalid_ssl_cert base error."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        flow = make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=SslCertificateError("cert"))

            result = await flow.async_step_reauth_confirm(
                user_input={CONF_USERNAME: "admin", CONF_PASSWORD: "pass"}
            )

        assert result["step_id"] == "reauth_confirm"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {"base": "invalid_ssl_cert"}

    @pytest.mark.asyncio
    async def test_does_not_delete_issue_on_failure(self) -> None:
        """async_delete_issue must NOT be called when reauth fails."""
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        flow = make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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

    @pytest.mark.asyncio
    async def test_unexpected_exception_shows_unknown(self) -> None:
        flow = make_reauth_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=RuntimeError("boom"))
            result = await flow.async_step_reauth_confirm(
                user_input={CONF_USERNAME: "admin", CONF_PASSWORD: "pw"}
            )

        assert result["step_id"] == "reauth_confirm"
        assert flow.async_show_form.call_args.kwargs["errors"] == {"base": "unknown"}


class TestConfigFlowHelpers:
    """Tests for standalone config flow class methods and helpers."""

    def test_async_get_options_flow_returns_options_flow_instance(self) -> None:
        entry = MagicMock()
        options_flow = UniFiAlertsConfigFlow.async_get_options_flow(entry)
        from custom_components.unifi_alerts.config_flow import UniFiAlertsOptionsFlow

        assert isinstance(options_flow, UniFiAlertsOptionsFlow)
