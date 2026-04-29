"""Tests for async_setup_entry and async_unload_entry in __init__.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_entry, make_hass

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_CLEAR_TIMEOUT,
    CONF_CONTROLLER_URL,
    CONF_ENABLED_CATEGORIES,
    CONF_POLL_INTERVAL,
    CONF_VERIFY_SSL,
    DATA_COORDINATOR,
    DATA_UNREGISTER_WEBHOOKS,
    DATA_WEBHOOK_IDS,
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
        return_value={"network_wan": "http://ha/hook/abc?token=x"}
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

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
        ):
            result = await async_setup_entry(hass, entry)

        assert result is True

    @pytest.mark.asyncio
    async def test_happy_path_stores_coordinator_in_hass_data(self):
        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all()

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
        ):
            await async_setup_entry(hass, entry)

        entry_data = hass.data[DOMAIN][entry.entry_id]
        assert entry_data[DATA_COORDINATOR] is mock_coordinator
        assert DATA_WEBHOOK_IDS in entry_data
        assert DATA_UNREGISTER_WEBHOOKS in entry_data

    @pytest.mark.asyncio
    async def test_auth_failure_raises_config_entry_not_ready(self):
        from homeassistant.exceptions import ConfigEntryNotReady

        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            authenticate_side_effect=Exception("connection refused")
        )

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)

    @pytest.mark.asyncio
    async def test_first_refresh_failure_raises_config_entry_not_ready(self):
        from homeassistant.exceptions import ConfigEntryNotReady

        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coordinator, mock_wm = _patch_all(
            first_refresh_side_effect=Exception("poll failed")
        )

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, entry)

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
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
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
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
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

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=MagicMock()),
        ):
            await async_setup_entry(hass, entry)

        hass.config_entries.async_forward_entry_setups.assert_called_once()


# ── async_unload_entry ────────────────────────────────────────────────────────


class TestAsyncUnloadEntry:
    def _populate_hass(self, hass, entry, mock_coordinator, mock_client, mock_wm):
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            DATA_COORDINATOR: mock_coordinator,
            DATA_WEBHOOK_IDS: {},
            DATA_UNREGISTER_WEBHOOKS: mock_wm.unregister_all,
            "client": mock_client,
        }

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

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=mock_dev_reg),
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

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession", return_value=MagicMock()
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coordinator,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch("custom_components.unifi_alerts.dr.async_get", return_value=mock_dev_reg),
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


class TestRedactWebhookToken:
    """`?token=<secret>` must be stripped from URLs before they hit DEBUG logs."""

    def test_redacts_token_query_param(self):
        from custom_components.unifi_alerts import _redact_webhook_token

        url = "http://homeassistant.local:8123/api/webhook/unifi_alerts_x?token=supersecret123"
        redacted = _redact_webhook_token(url)
        assert "supersecret123" not in redacted
        assert redacted.endswith("?token=***")

    def test_passthrough_when_no_token_present(self):
        from custom_components.unifi_alerts import _redact_webhook_token

        url = "http://homeassistant.local:8123/api/webhook/unifi_alerts_x"
        assert _redact_webhook_token(url) == url

    def test_redacted_when_token_anywhere_after_question_mark(self):
        """Even if the token is the only query param, redaction stops at end-of-string."""
        from custom_components.unifi_alerts import _redact_webhook_token

        url = "http://h/api/webhook/x?token=abc"
        redacted = _redact_webhook_token(url)
        assert "abc" not in redacted
