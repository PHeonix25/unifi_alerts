"""Tests for async_setup_entry and async_unload_entry in __init__.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_entry, make_hass, patch_setup_entry_collaborators

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_VERIFY_SSL,
    CONF_WEBHOOK_ID_SUFFIX,
    CONF_WEBHOOK_SECRET,
    DEFAULT_CLEAR_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _patch_all(authenticate_side_effect=None, first_refresh_side_effect=None):
    """Context managers that patch away all external collaborators."""
    mock_coordinator = MagicMock()
    mock_coordinator.async_config_entry_first_refresh = AsyncMock(
        side_effect=first_refresh_side_effect
    )
    mock_coordinator.async_restore_watermarks = AsyncMock()
    mock_coordinator.async_shutdown = AsyncMock()
    mock_coordinator.push_alert = MagicMock()

    mock_client = MagicMock()
    mock_client.authenticate = AsyncMock(side_effect=authenticate_side_effect)
    mock_client.close = AsyncMock()

    mock_webhook_manager = MagicMock()
    mock_webhook_manager.register_all = MagicMock(
        return_value={"network_wan": "http://ha/hook/abc"}
    )
    mock_webhook_manager.unregister_all = MagicMock()

    return mock_client, mock_coordinator, mock_webhook_manager


# ── async_setup_entry ─────────────────────────────────────────────────────────


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_happy_path_returns_true(self):
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        with patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm):
            result = await async_setup_entry(hass, entry)

        assert result is True

    @pytest.mark.asyncio
    async def test_happy_path_stores_coordinator_in_hass_data(self):
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        with patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm):
            await async_setup_entry(hass, entry)

        assert entry.runtime_data.coordinator is mock_coordinator
        assert entry.runtime_data.webhook_urls is not None
        assert entry.runtime_data.unregister_webhooks is not None

    @pytest.mark.asyncio
    async def test_auth_failure_raises_config_entry_not_ready(self):
        from homeassistant.exceptions import ConfigEntryNotReady

        from custom_components.unifi_alerts import async_setup_entry
        from custom_components.unifi_alerts.unifi_auth import CannotConnectError

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            authenticate_side_effect=CannotConnectError("connection refused")
        )

        with (
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_first_refresh_failure_raises_config_entry_not_ready(self):
        """A ConfigEntryNotReady raised by the coordinator's first refresh propagates unmodified.

        HA core's async_config_entry_first_refresh() raises ConfigEntryNotReady
        itself on a connectivity/UpdateFailed outcome — async_setup_entry no
        longer wraps this call, so the mock must raise the same exception type
        real HA raises.
        """
        from homeassistant.exceptions import ConfigEntryNotReady

        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            first_refresh_side_effect=ConfigEntryNotReady("poll failed")
        )

        with (
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_first_refresh_auth_failure_raises_config_entry_auth_failed(self):
        """A ConfigEntryAuthFailed raised by the first refresh must not be misclassified.

        HA core raises ConfigEntryAuthFailed directly out of
        async_config_entry_first_refresh() when the coordinator's own re-auth
        attempt fails (see coordinator._async_update_data); silently
        converting it to ConfigEntryNotReady would suppress HA's reauth-repair
        flow. Regression test for the bug where a blanket `except Exception`
        around this call re-wrapped every failure as ConfigEntryNotReady.
        """
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            first_refresh_side_effect=ConfigEntryAuthFailed("credentials changed")
        )

        with (
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
            pytest.raises(ConfigEntryAuthFailed),
        ):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_invalid_auth_message_omits_underlying_error_text(self):
        """ConfigEntryAuthFailed must surface only the exception class name.

        Including ``str(err)`` risks leaking URL fragments or auth details into the
        HA repair UI / logs. The fix mirrors the pattern used in unifi_client.py.
        """
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.unifi_alerts import async_setup_entry
        from custom_components.unifi_alerts.unifi_client import InvalidAuthError

        secret_marker = "user:hunter2@controller.local/path?api_key=leakedkey"
        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            authenticate_side_effect=InvalidAuthError(secret_marker)
        )

        with (
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
            pytest.raises(ConfigEntryAuthFailed) as excinfo,
        ):
            await async_setup_entry(hass, entry)

        assert secret_marker not in str(excinfo.value)
        assert "InvalidAuthError" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_connect_failure_message_omits_underlying_error_text(self):
        """ConfigEntryNotReady on the auth path must not embed the inner error text."""
        from homeassistant.exceptions import ConfigEntryNotReady

        from custom_components.unifi_alerts import async_setup_entry
        from custom_components.unifi_alerts.unifi_auth import CannotConnectError

        secret_marker = "https://admin:secretpass@10.0.0.1:8443"
        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            authenticate_side_effect=CannotConnectError(secret_marker)
        )

        with (
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
            pytest.raises(ConfigEntryNotReady) as excinfo,
        ):
            await async_setup_entry(hass, entry)

        assert secret_marker not in str(excinfo.value)
        assert "CannotConnectError" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_ssl_disabled_logs_warning(self):
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry(
            data={
                "controller_url": "https://192.168.1.1",
                "username": "admin",
                "password": "password",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                CONF_CLEAR_TIMEOUT: DEFAULT_CLEAR_TIMEOUT,
                CONF_VERIFY_SSL: False,
                "webhook_secret": "fake-secret",
            }
        )
        mock_client, mock_coordinator, mock_wm = _patch_all()

        with (
            patch("custom_components.unifi_alerts._LOGGER") as mock_logger,
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
        ):
            await async_setup_entry(hass, entry)

        warning_messages = " ".join(str(call[0][0]) for call in mock_logger.warning.call_args_list)
        assert "SSL certificate verification is disabled" in warning_messages

    @pytest.mark.asyncio
    async def test_ssl_enabled_no_warning(self):
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()  # default has verify_ssl=True
        mock_client, mock_coordinator, mock_wm = _patch_all()

        with (
            patch("custom_components.unifi_alerts._LOGGER") as mock_logger,
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
        ):
            await async_setup_entry(hass, entry)

        warning_messages = " ".join(str(call[0][0]) for call in mock_logger.warning.call_args_list)
        assert "SSL certificate verification is disabled" not in warning_messages

    @pytest.mark.asyncio
    async def test_platforms_are_forwarded(self):
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        with patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm):
            await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_called_once()

    @pytest.mark.parametrize(
        "failing_call",
        ["async_forward_entry_setups", "async_register_services"],
    )
    @pytest.mark.asyncio
    async def test_failure_after_webhook_registration_unregisters_and_closes(self, failing_call):
        """Any failure after register_all() must leave zero webhooks registered.

        Otherwise the automatic setup retry finds every deterministic
        webhook_id already taken, register_all() skips them all, and the
        entry silently loads with an empty webhook URL map (#265).
        """
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        if failing_call == "async_forward_entry_setups":
            hass.config_entries.async_forward_entry_setups = AsyncMock(
                side_effect=RuntimeError("boom")
            )
            register_services_patch = patch(
                "custom_components.unifi_alerts.async_register_services"
            )
        else:
            register_services_patch = patch(
                "custom_components.unifi_alerts.async_register_services",
                side_effect=RuntimeError("boom"),
            )

        with (
            patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm),
            register_services_patch,
            pytest.raises(RuntimeError),
        ):
            await async_setup_entry(hass, entry)

        mock_wm.unregister_all.assert_called_once()
        mock_client.close.assert_awaited_once()
        mock_coordinator.async_shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_after_setup_failure_produces_full_webhook_url_map(self):
        """The retry after a cleaned-up failure must re-register every webhook.

        Simulates the fail-then-retry sequence directly: register_all() is
        called twice against the same WebhookManager mock, and because the
        first attempt's cleanup unregistered everything, the second call
        returns the full URL map rather than an empty one.
        """
        from custom_components.unifi_alerts import async_setup_entry

        mock_client, mock_coordinator, mock_wm = _patch_all()
        full_urls = {cat: f"http://ha/hook/{cat}" for cat in ALL_CATEGORIES}
        mock_wm.register_all.side_effect = [RuntimeError("first attempt never gets here")]

        with patch_setup_entry_collaborators(mock_client, mock_coordinator, mock_wm):
            # First attempt: forward setups fails after webhooks are registered.
            first_hass = make_hass()
            first_hass.config_entries.async_forward_entry_setups = AsyncMock(
                side_effect=RuntimeError("boom")
            )
            entry = make_entry()
            mock_wm.register_all.side_effect = None
            mock_wm.register_all.return_value = full_urls
            with pytest.raises(RuntimeError):
                await async_setup_entry(first_hass, entry)
            mock_wm.unregister_all.assert_called_once()

            # Retry: a fresh hass/entry, same underlying WebhookManager mock —
            # register_all() must return the full map again, not an empty one.
            retry_hass = make_hass()
            retry_entry = make_entry()
            result = await async_setup_entry(retry_hass, retry_entry)

        assert result is True
        assert retry_entry.runtime_data.webhook_urls == full_urls


# ── async_unload_entry ────────────────────────────────────────────────────────


class TestAsyncUnloadEntry:
    def _populate_hass(self, hass, entry, mock_coordinator, mock_client, mock_wm):
        entry.runtime_data = MagicMock()
        entry.runtime_data.coordinator = mock_coordinator
        entry.runtime_data.unregister_webhooks = mock_wm.unregister_all
        entry.runtime_data.client = mock_client
        hass.config_entries.async_entries = MagicMock(return_value=[entry])

    @pytest.mark.asyncio
    async def test_successful_unload_returns_true(self):
        from custom_components.unifi_alerts import async_unload_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()
        self._populate_hass(hass, entry, mock_coordinator, mock_client, mock_wm)

        result = await async_unload_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_unload_calls_coordinator_shutdown(self):
        from custom_components.unifi_alerts import async_unload_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()
        self._populate_hass(hass, entry, mock_coordinator, mock_client, mock_wm)

        await async_unload_entry(hass, entry)
        mock_coordinator.async_shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unload_calls_unregister_webhooks(self):
        from custom_components.unifi_alerts import async_unload_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()
        self._populate_hass(hass, entry, mock_coordinator, mock_client, mock_wm)

        await async_unload_entry(hass, entry)
        mock_wm.unregister_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_calls_client_close(self):
        from custom_components.unifi_alerts import async_unload_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()
        self._populate_hass(hass, entry, mock_coordinator, mock_client, mock_wm)

        await async_unload_entry(hass, entry)
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_platform_unload_skips_cleanup(self):
        """If platform unload fails, coordinator/webhooks/client must NOT be torn down."""
        from custom_components.unifi_alerts import async_unload_entry

        hass = make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()
        self._populate_hass(hass, entry, mock_coordinator, mock_client, mock_wm)

        result = await async_unload_entry(hass, entry)
        assert result is False
        mock_coordinator.async_shutdown.assert_not_called()
        mock_wm.unregister_all.assert_not_called()
        mock_client.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_unload_teardown_order(self):
        """CLAUDE.md constraint: teardown must be coordinator.async_shutdown()
        → unregister_all() → client.close(), in that exact order."""
        from custom_components.unifi_alerts import async_unload_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        call_order: list[str] = []
        mock_coordinator.async_shutdown = AsyncMock(
            side_effect=lambda: call_order.append("shutdown")
        )
        mock_wm.unregister_all = MagicMock(side_effect=lambda: call_order.append("unregister"))
        mock_client.close = AsyncMock(side_effect=lambda: call_order.append("close"))

        self._populate_hass(hass, entry, mock_coordinator, mock_client, mock_wm)
        await async_unload_entry(hass, entry)

        assert call_order == ["shutdown", "unregister", "close"]


# ── async_remove_entry ────────────────────────────────────────────────────────


class TestAsyncRemoveEntry:
    """async_remove_entry must delete the watermark store file and all repair issues."""

    @pytest.mark.asyncio
    async def test_removes_watermark_store_file(self):
        from custom_components.unifi_alerts import async_remove_entry

        hass = make_hass()
        entry = make_entry(entry_id="entry-xyz")

        mock_store = MagicMock()
        mock_store.async_remove = AsyncMock()

        with (
            patch(
                "custom_components.unifi_alerts.Store", return_value=mock_store
            ) as mock_store_cls,
            patch("custom_components.unifi_alerts.ir.async_delete_issue"),
        ):
            await async_remove_entry(hass, entry)

        mock_store_cls.assert_called_once()
        call_args = mock_store_cls.call_args.args
        assert call_args[0] is hass
        assert call_args[2] == f"{DOMAIN}_watermarks_entry-xyz"
        mock_store.async_remove.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_all_per_entry_repair_issues(self):
        from custom_components.unifi_alerts import async_remove_entry

        hass = make_hass()
        entry = make_entry(entry_id="entry-xyz")

        mock_store = MagicMock()
        mock_store.async_remove = AsyncMock()

        with (
            patch("custom_components.unifi_alerts.Store", return_value=mock_store),
            patch("custom_components.unifi_alerts.ir.async_delete_issue") as mock_delete_issue,
        ):
            await async_remove_entry(hass, entry)

        deleted_issue_ids = {call.args[2] for call in mock_delete_issue.call_args_list}
        assert deleted_issue_ids == {
            "auth_failed_entry-xyz",
            "webhook_secret_rotated_entry-xyz",
            "webhook_urls_changed_entry-xyz",
            "watermark_persist_failed_entry-xyz",
            "apikey_migration_required_entry-xyz",
            "webhook_legacy_query_auth_entry-xyz",
        }
        for call in mock_delete_issue.call_args_list:
            assert call.args[0] is hass
            assert call.args[1] == DOMAIN


# ── device registry ───────────────────────────────────────────────────────────


class TestDeviceRegistration:
    """async_setup_entry must proactively register the hub device."""

    @pytest.mark.asyncio
    async def test_setup_creates_service_device(self):
        """async_setup_entry must call async_get_or_create with SERVICE entry type."""
        from homeassistant.helpers.device_registry import DeviceEntryType

        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock()

        with patch_setup_entry_collaborators(
            mock_client, mock_coordinator, mock_wm, dev_reg=mock_dev_reg
        ):
            await async_setup_entry(hass, entry)

        mock_dev_reg.async_get_or_create.assert_called_once()
        call_kwargs = mock_dev_reg.async_get_or_create.call_args.kwargs
        assert call_kwargs["config_entry_id"] == entry.entry_id
        assert call_kwargs["entry_type"] == DeviceEntryType.SERVICE
        assert (DOMAIN, entry.entry_id) in call_kwargs["identifiers"]

    @pytest.mark.asyncio
    async def test_setup_device_has_configuration_url(self):
        """The registered device must carry the controller URL as configuration_url."""
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        mock_dev_reg = MagicMock()
        mock_dev_reg.async_get_or_create = MagicMock()

        with patch_setup_entry_collaborators(
            mock_client, mock_coordinator, mock_wm, dev_reg=mock_dev_reg
        ):
            await async_setup_entry(hass, entry)

        call_kwargs = mock_dev_reg.async_get_or_create.call_args.kwargs
        assert call_kwargs["configuration_url"] == entry.data[CONF_CONTROLLER_URL]


# ── _async_update_listener ────────────────────────────────────────────────────


class TestAsyncUpdateListener:
    @pytest.mark.asyncio
    async def test_listener_reloads_entry(self):
        from custom_components.unifi_alerts import _async_update_listener

        hass = make_hass()
        entry = make_entry()
        await _async_update_listener(hass, entry)
        hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


def _capture_migrate_updates(hass):
    """Wire hass.config_entries.async_update_entry to record every call.

    Returns the list the calls are appended to. The entry's ``data`` and
    ``version`` are applied as each call arrives so the sequential migration
    steps chain exactly as they do under real HA.
    """
    update_calls: list[dict] = []

    def capture_update(cfg_entry, **kwargs):
        update_calls.append(dict(kwargs))
        if "data" in kwargs:
            cfg_entry.data = kwargs["data"]
        if "version" in kwargs:
            cfg_entry.version = kwargs["version"]

    hass.config_entries.async_update_entry = capture_update
    return update_calls


class TestAsyncMigrateEntry:
    """Tests for async_migrate_entry version migration logic."""

    @pytest.mark.asyncio
    async def test_v2_missing_secret_backfills_secret_and_reaches_v4(self):
        """A v2 entry without webhook_secret gets a fresh secret and walks to version 4."""
        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            }
        )
        entry.version = 2

        update_calls = _capture_migrate_updates(hass)

        with patch("custom_components.unifi_alerts.ir.async_create_issue"):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2->v3 update carries the backfilled secret/suffix.
        v3_call = next(c for c in update_calls if c.get("version") == 3)
        assert CONF_WEBHOOK_SECRET in v3_call["data"]
        assert v3_call["data"][CONF_WEBHOOK_SECRET]  # non-empty
        assert CONF_WEBHOOK_ID_SUFFIX in v3_call["data"]
        assert v3_call["data"][CONF_WEBHOOK_ID_SUFFIX]  # non-empty
        # Migration terminates at version 4.
        assert entry.version == 4

    @pytest.mark.asyncio
    async def test_v2_with_secret_already_set_reaches_v4(self):
        """A v2 entry that already has secret/suffix bumps to v3 (data unchanged) then v4."""
        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                CONF_WEBHOOK_SECRET: "already-set-secret-value",
                CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
            }
        )
        entry.version = 2

        update_calls = _capture_migrate_updates(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        # v2->v3 bump must not rewrite data (secret/suffix already present).
        v3_call = next(c for c in update_calls if c.get("version") == 3)
        assert "data" not in v3_call
        assert entry.version == 4

    @pytest.mark.asyncio
    async def test_v1_entry_is_migrated_through_all_steps(self):
        """A v1 entry chains v1->2 (strip is_unifi_os), v2->3 (backfill), v3->4 (apikey)."""
        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                "username": "admin",
                "password": "password",
                "is_unifi_os": True,  # legacy field to be stripped in v1->2
            }
        )
        entry.version = 1

        update_calls = _capture_migrate_updates(hass)

        with patch("custom_components.unifi_alerts.ir.async_create_issue"):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        # Three update calls: v1->2, v2->3, v3->4.
        assert len(update_calls) == 3
        assert update_calls[0].get("version") == 2
        assert "is_unifi_os" not in update_calls[0].get("data", {})
        assert update_calls[1].get("version") == 3
        assert CONF_WEBHOOK_SECRET in update_calls[1].get("data", {})
        assert update_calls[2].get("version") == 4
        assert entry.version == 4

    @pytest.mark.asyncio
    async def test_v3_with_api_key_migrates_silently_to_v4(self):
        """A v3 entry with an API key drops legacy userpass keys and bumps to v4."""
        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                "username": "admin",
                "password": "password",
                "auth_method": "apikey",
                CONF_API_KEY: "existing-api-key",
                CONF_WEBHOOK_SECRET: "fake-secret",
                CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
            }
        )
        entry.version = 3

        _capture_migrate_updates(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 4
        assert entry.data[CONF_API_KEY] == "existing-api-key"
        # Legacy userpass keys (and the now-unused auth_method marker) are dropped.
        assert "username" not in entry.data
        assert "password" not in entry.data
        assert "auth_method" not in entry.data
        # Identity-preserving fields untouched.
        assert entry.data[CONF_WEBHOOK_SECRET] == "fake-secret"
        assert entry.data[CONF_WEBHOOK_ID_SUFFIX] == "deadbeef"

    @pytest.mark.asyncio
    async def test_v3_userpass_only_migrates_to_v4_without_credentials(self):
        """A v3 userpass-only entry loses its credentials, leaving no api_key for reauth."""
        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                "username": "admin",
                "password": "password",
                CONF_WEBHOOK_SECRET: "fake-secret",
                CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
            }
        )
        entry.version = 3

        _capture_migrate_updates(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 4
        assert "username" not in entry.data
        assert "password" not in entry.data
        assert CONF_API_KEY not in entry.data
        # Identity-preserving fields untouched, so entities/history/webhooks survive.
        assert entry.data[CONF_WEBHOOK_SECRET] == "fake-secret"
        assert entry.data[CONF_WEBHOOK_ID_SUFFIX] == "deadbeef"

    @pytest.mark.asyncio
    async def test_v4_entry_is_left_untouched(self):
        """An entry already at version 4 must not be updated."""
        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_API_KEY: "key",
            }
        )
        entry.version = 4

        update_calls = _capture_migrate_updates(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert update_calls == []


class TestAsyncMigrateEntryRepairIssue:
    """Repair issue is created when webhook_id_suffix is backfilled during v2->v3 migration."""

    @pytest.mark.asyncio
    async def test_repair_issue_created_when_suffix_backfilled(self):
        """A v2 entry missing webhook_id_suffix must create a Repair issue after migration."""
        from unittest.mock import patch

        from custom_components.unifi_alerts import async_migrate_entry
        from custom_components.unifi_alerts.const import DOMAIN

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
            }
        )
        entry.version = 2

        def capture_update(cfg_entry, **kwargs):
            if "data" in kwargs:
                cfg_entry.data = kwargs["data"]
            if "version" in kwargs:
                cfg_entry.version = kwargs["version"]

        hass.config_entries.async_update_entry = capture_update

        with patch("custom_components.unifi_alerts.ir.async_create_issue") as mock_create_issue:
            result = await async_migrate_entry(hass, entry)

        assert result is True
        mock_create_issue.assert_called_once()
        call_args = mock_create_issue.call_args
        # hass, domain, issue_id are positional; the rest are keyword args
        assert call_args.args[1] == DOMAIN
        assert call_args.args[2].startswith("webhook_urls_changed_")
        assert call_args.kwargs["translation_key"] == "webhook_urls_changed"
        assert call_args.kwargs["is_fixable"] is False

    @pytest.mark.asyncio
    async def test_repair_issue_not_created_when_suffix_already_present(self):
        """A v2 entry that already has webhook_id_suffix must NOT create a Repair issue."""
        from unittest.mock import patch

        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                CONF_WEBHOOK_SECRET: "existing-secret",
                CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
            }
        )
        entry.version = 2

        def capture_update(cfg_entry, **kwargs):
            if "version" in kwargs:
                cfg_entry.version = kwargs["version"]

        hass.config_entries.async_update_entry = capture_update

        with patch("custom_components.unifi_alerts.ir.async_create_issue") as mock_create_issue:
            result = await async_migrate_entry(hass, entry)

        assert result is True
        mock_create_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_repair_issue_not_created_when_only_secret_missing(self):
        """A v2 entry missing only webhook_secret (suffix present) must NOT create a Repair issue.

        The URL structure is unchanged when only the secret is backfilled; the suffix
        determines the URL path, not the secret token.
        """
        from unittest.mock import patch

        from custom_components.unifi_alerts import async_migrate_entry

        hass = make_hass()
        entry = make_entry(
            data={
                CONF_CONTROLLER_URL: "https://192.168.1.1",
                CONF_ENABLED_CATEGORIES: ALL_CATEGORIES,
                CONF_WEBHOOK_ID_SUFFIX: "deadbeef",
                # No webhook_secret
            }
        )
        entry.version = 2

        def capture_update(cfg_entry, **kwargs):
            if "data" in kwargs:
                cfg_entry.data = kwargs["data"]
            if "version" in kwargs:
                cfg_entry.version = kwargs["version"]

        hass.config_entries.async_update_entry = capture_update

        with patch("custom_components.unifi_alerts.ir.async_create_issue") as mock_create_issue:
            result = await async_migrate_entry(hass, entry)

        assert result is True
        mock_create_issue.assert_not_called()
