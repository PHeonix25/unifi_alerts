"""Tests for the initial setup flow: async_step_user, async_step_categories, async_step_finish."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import AbortFlow

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

from .conftest import _VALID_INPUT, make_flow, make_session_mock


class TestUserStep:
    """Tests for async_step_user."""

    @pytest.mark.asyncio
    async def test_duplicate_url_aborts(self) -> None:
        """When the controller URL is already configured, the flow should abort."""
        flow = make_flow()
        flow._abort_if_unique_id_configured = MagicMock(side_effect=AbortFlow("already_configured"))

        with pytest.raises(AbortFlow) as exc_info:
            await flow.async_step_user(_VALID_INPUT)

        assert exc_info.value.reason == "already_configured"

    @pytest.mark.asyncio
    async def test_unique_id_set_to_normalised_url(self) -> None:
        """async_set_unique_id must be called with the URL with trailing slash stripped."""
        flow = make_flow()
        flow.async_step_categories = AsyncMock(return_value={"type": "form"})

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

            await flow.async_step_user(
                {**_VALID_INPUT, CONF_CONTROLLER_URL: "https://192.168.1.1/"}
            )

        flow.async_set_unique_id.assert_called_once_with("https://192.168.1.1")

    @pytest.mark.asyncio
    async def test_unique_id_checked_before_auth(self) -> None:
        """_abort_if_unique_id_configured must be called before authentication.

        Verifies fail-fast behaviour: we never hit the network if the entry
        already exists.
        """
        flow = make_flow()
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
    async def test_invalid_url_scheme_shows_error(self) -> None:
        """A controller URL that is not http/https must show a field-level error."""
        flow = make_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

        result = await flow.async_step_user(
            {**_VALID_INPUT, CONF_CONTROLLER_URL: "ftp://192.168.1.1"}
        )

        assert result["step_id"] == "user"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"].get("controller_url") == "invalid_url_scheme"
        # unique-id check and network call must NOT have happened
        flow.async_set_unique_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_proceeds_to_categories(self) -> None:
        """When there is no duplicate, the flow should proceed to the categories step."""
        flow = make_flow()
        categories_result = {"type": "form", "step_id": "categories"}
        flow.async_step_categories = AsyncMock(return_value=categories_result)

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

            result = await flow.async_step_user(_VALID_INPUT)

        assert result == categories_result
        flow.async_set_unique_id.assert_called_once()
        flow._abort_if_unique_id_configured.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_preserves_submitted_values(self) -> None:
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

        flow = make_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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
        schema_defaults = {
            str(k): k.default() for k in schema.schema if k.default is not vol.UNDEFINED
        }
        assert schema_defaults.get(CONF_CONTROLLER_URL) == "https://10.0.0.1"
        assert schema_defaults.get(CONF_USERNAME) == "myuser"
        # Password and API key fields must NOT be pre-filled — they have no default
        assert CONF_PASSWORD not in schema_defaults
        assert CONF_API_KEY not in schema_defaults
        assert schema_defaults.get(CONF_VERIFY_SSL) is False

    @pytest.mark.asyncio
    async def test_uses_ha_clientsession_with_user_verify_ssl(self) -> None:
        """async_step_user must use HA's shared clientsession with the user's verify_ssl value.

        Bare `aiohttp.ClientSession()` bypasses HA's proxy config, connection pool, and
        the user's SSL setting. The fix is to call `async_get_clientsession(hass, verify_ssl=...)`
        so HA returns the appropriately-configured shared session.
        """
        flow = make_flow()
        flow.async_step_categories = AsyncMock(return_value={"type": "form"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ) as mock_get_session,
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(return_value=[])

            await flow.async_step_user({**_VALID_INPUT, CONF_VERIFY_SSL: False})

        mock_get_session.assert_called_once_with(flow.hass, verify_ssl=False)

    @pytest.mark.asyncio
    async def test_initial_load_uses_hardcoded_defaults(self) -> None:
        """On initial load (no user_input), the form should show hardcoded defaults."""
        flow = make_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

        result = await flow.async_step_user(user_input=None)

        assert result["step_id"] == "user"
        call_kwargs = flow.async_show_form.call_args.kwargs
        schema = call_kwargs["data_schema"]
        # Only read defaults for keys that actually have one (some Optional fields don't).
        schema_defaults = {}
        for k in schema.schema:
            if (
                not isinstance(k.default, vol.Undefined.__class__)
                and k.default is not vol.UNDEFINED
            ):
                with contextlib.suppress(TypeError):
                    schema_defaults[str(k)] = k.default()
        assert schema_defaults.get(CONF_CONTROLLER_URL) == "https://192.168.1.1"
        assert schema_defaults.get(CONF_VERIFY_SSL) == DEFAULT_VERIFY_SSL

    @pytest.mark.asyncio
    async def test_fetch_alarms_failure_shows_cannot_connect(self) -> None:
        """If fetch_alarms() raises CannotConnectError after successful auth, show cannot_connect error."""
        from custom_components.unifi_alerts.unifi_client import CannotConnectError

        flow = make_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
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
    async def test_ssl_cert_error_on_authenticate_shows_invalid_ssl_cert(self) -> None:
        """SslCertificateError from authenticate() must map to the invalid_ssl_cert field error."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        flow = make_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(side_effect=SslCertificateError("cert error"))

            result = await flow.async_step_user(_VALID_INPUT)

        assert result["step_id"] == "user"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {CONF_CONTROLLER_URL: "invalid_ssl_cert"}

    @pytest.mark.asyncio
    async def test_ssl_cert_error_on_fetch_alarms_shows_invalid_ssl_cert(self) -> None:
        """SslCertificateError from fetch_alarms() must map to the invalid_ssl_cert field error."""
        from custom_components.unifi_alerts.unifi_client import SslCertificateError

        flow = make_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "user"})

        with (
            patch(
                "custom_components.unifi_alerts.config_flow.async_get_clientsession",
                return_value=make_session_mock(),
            ),
            patch("custom_components.unifi_alerts.config_flow.UniFiClient") as mock_cls,
        ):
            instance = mock_cls.return_value
            instance.authenticate = AsyncMock(return_value="userpass")
            instance.fetch_alarms = AsyncMock(side_effect=SslCertificateError("cert error"))

            result = await flow.async_step_user(_VALID_INPUT)

        assert result["step_id"] == "user"
        call_kwargs = flow.async_show_form.call_args.kwargs
        assert call_kwargs["errors"] == {CONF_CONTROLLER_URL: "invalid_ssl_cert"}

    @pytest.mark.asyncio
    async def test_ssl_cert_error_is_subclass_of_cannot_connect(self) -> None:
        """SslCertificateError must be a subclass of CannotConnectError."""
        from custom_components.unifi_alerts.unifi_client import (
            CannotConnectError,
            SslCertificateError,
        )

        assert issubclass(SslCertificateError, CannotConnectError)

    @pytest.mark.asyncio
    async def test_generates_webhook_id_suffix(self) -> None:
        from custom_components.unifi_alerts.const import CONF_WEBHOOK_ID_SUFFIX

        flow = make_flow()
        flow.async_step_categories = AsyncMock(return_value={"type": "form"})

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
            flow = make_flow()
            flow.async_step_categories = AsyncMock(return_value={"type": "form"})
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
                await flow.async_step_user(_VALID_INPUT)
            suffixes.append(flow._credentials[CONF_WEBHOOK_ID_SUFFIX])
        assert suffixes[0] != suffixes[1]


class TestCategoriesStep:
    """Tests for async_step_categories."""

    @pytest.mark.asyncio
    async def test_all_disabled_shows_error(self) -> None:
        """Submitting categories with nothing selected must show an error, not proceed."""
        flow = make_flow()
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
    async def test_proceeds_to_finish(self) -> None:
        """Submitting categories should proceed to the finish step, not create the entry."""
        flow = make_flow()
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
    async def test_saves_poll_interval_and_clear_timeout(self) -> None:
        """Submitted poll_interval and clear_timeout must be stored in _entry_data."""
        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT, CONF_POLL_INTERVAL

        flow = make_flow()
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
    async def test_accepts_boundary_poll_intervals(self, poll_interval: int) -> None:
        """poll_interval boundary values 10 and 3600 must be accepted without error."""
        from custom_components.unifi_alerts.const import CONF_POLL_INTERVAL

        flow = make_flow()
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
    async def test_accepts_boundary_clear_timeouts(self, clear_timeout: int) -> None:
        """clear_timeout boundary values 1 and 1440 must be accepted without error."""
        from custom_components.unifi_alerts.const import CONF_CLEAR_TIMEOUT

        flow = make_flow()
        flow._controller_url = "https://192.168.1.1"
        flow._detected_auth_method = "userpass"
        flow._credentials = {CONF_WEBHOOK_SECRET: "s"}
        flow.async_step_finish = AsyncMock(return_value={"type": "form", "step_id": "finish"})

        cat_input = {f"cat_{cat}": True for cat in ALL_CATEGORIES}
        cat_input[CONF_CLEAR_TIMEOUT] = clear_timeout

        result = await flow.async_step_categories(cat_input)

        assert result["step_id"] == "finish"


class TestFinishStep:
    """Tests for async_step_finish."""

    @pytest.mark.asyncio
    async def test_shows_webhook_urls(self) -> None:
        """async_step_finish with no input should show a form with webhook URL fields in data_schema."""
        flow = make_flow()
        flow._controller_url = "https://192.168.1.1"
        fake_secret = "test-secret-token"
        flow._entry_data = {
            CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            CONF_WEBHOOK_SECRET: fake_secret,
        }
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
    async def test_submit_creates_entry(self) -> None:
        """async_step_finish with empty input (form submitted) should create the config entry."""
        flow = make_flow()
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


class TestMigration:
    """Tests for async_migrate_entry."""

    @pytest.mark.asyncio
    async def test_strips_conf_is_unifi_os(self) -> None:
        """async_migrate_entry must remove is_unifi_os and ultimately reach version 3.

        A v1 entry passes through v1->2 (strip is_unifi_os) and then v2->3
        (backfill webhook_secret / webhook_id_suffix) in the same call.
        """
        from custom_components.unifi_alerts import async_migrate_entry

        entry = MagicMock()
        entry.entry_id = "test-entry-migrate"
        entry.version = 1
        entry.data = {
            CONF_CONTROLLER_URL: "https://192.168.1.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
            CONF_VERIFY_SSL: True,
            "is_unifi_os": True,  # stale key from v1
        }

        # Simulate HA's async_update_entry: update version and data in-place
        def _fake_update(entry, *, data=None, version=None, **kwargs):
            if data is not None:
                entry.data = data
            if version is not None:
                entry.version = version

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock(side_effect=_fake_update)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v1->2->3: the chained migration ends at version 3
        assert entry.version == 3
        assert "is_unifi_os" not in entry.data
        # Remaining fields must be preserved
        assert entry.data[CONF_CONTROLLER_URL] == "https://192.168.1.1"
