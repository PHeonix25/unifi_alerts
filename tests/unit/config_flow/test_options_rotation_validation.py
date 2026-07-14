"""Tests for the options flow: webhook secret rotation, unique_id, and site validation.

Split out of test_options.py (#283) by behaviour area. See
test_options_credentials.py and test_options_helpers.py for the other pieces.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_SECRET,
)

from .conftest import make_options_flow, make_session_mock


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
            CONF_API_KEY: "new-key",
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
            instance.authenticate = AsyncMock(return_value=None)
            instance.fetch_alarms = AsyncMock(return_value=[])
            await flow.async_step_credentials(new_input)

        # No eager persistence; staged for finish.
        flow.hass.config_entries.async_update_entry.assert_not_called()
        assert flow._pending_data[CONF_API_KEY] == "new-key"
        assert flow._pending_data[CONF_WEBHOOK_SECRET] != "fixed-secret"

    @pytest.mark.asyncio
    async def test_unticked_does_not_rotate(self) -> None:
        """If the checkbox is unset, the existing secret must remain intact."""
        from custom_components.unifi_alerts.const import CONF_REGENERATE_WEBHOOK_SECRET

        flow = make_options_flow()
        flow.async_show_form = MagicMock(return_value={"type": "form", "step_id": "categories"})

        no_rotate = {
            CONF_CONTROLLER_URL: "",
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
        # _pending_data has a new API key but the SAME secret
        flow._pending_data = {
            CONF_API_KEY: "new-key",
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
            instance.authenticate = AsyncMock(return_value=None)
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
            instance.authenticate = AsyncMock(return_value=None)
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
            instance.authenticate = AsyncMock(return_value=None)
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
            instance.authenticate = AsyncMock(return_value=None)
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
