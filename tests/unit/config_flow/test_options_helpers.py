"""Tests for the options flow's standalone parsing/validation/building helpers.

Split out of test_options.py (#283) by behaviour area. See
test_options_credentials.py and test_options_rotation_validation.py for the
other pieces.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.unifi_alerts.const import (
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
)

from .conftest import make_session_mock


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
