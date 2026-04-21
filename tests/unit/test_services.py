"""Tests for services.py — clear_category and clear_all service handlers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CATEGORY_NETWORK_WAN,
    CATEGORY_SECURITY_THREAT,
    DATA_COORDINATOR,
    DOMAIN,
)
from custom_components.unifi_alerts.models import CategoryState
from custom_components.unifi_alerts.services import (
    ATTR_CATEGORY,
    ATTR_ENTRY_ID,
    CLEAR_ALL_SCHEMA,
    CLEAR_CATEGORY_SCHEMA,
    SERVICE_CLEAR_ALL,
    SERVICE_CLEAR_CATEGORY,
    async_register_services,
    async_unregister_services,
    _handle_clear_all,
    _handle_clear_category,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def make_state(category: str, is_alerting: bool = False, enabled: bool = True) -> CategoryState:
    return CategoryState(category=category, enabled=enabled, is_alerting=is_alerting)


def make_coordinator(states: dict[str, CategoryState] | None = None) -> MagicMock:
    coord = MagicMock()
    _states = states or {}
    coord.category_states = _states
    coord.get_category_state = lambda cat: _states.get(cat)
    coord.cancel_clear = MagicMock()
    coord.async_set_updated_data = MagicMock()
    return coord


def make_call(hass: MagicMock, data: dict) -> MagicMock:
    call = MagicMock()
    call.hass = hass
    call.data = data
    return call


def make_hass(entries: dict[str, MagicMock] | None = None) -> MagicMock:
    """Return a minimal hass mock with hass.data wired up."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    for entry_id, coordinator in (entries or {}).items():
        hass.data[DOMAIN][entry_id] = {DATA_COORDINATOR: coordinator}
    return hass


# ── schema validation ─────────────────────────────────────────────────────────


class TestClearCategorySchema:
    def test_valid_category_passes(self):
        result = CLEAR_CATEGORY_SCHEMA({ATTR_CATEGORY: CATEGORY_NETWORK_WAN})
        assert result[ATTR_CATEGORY] == CATEGORY_NETWORK_WAN

    def test_unknown_category_raises(self):
        with pytest.raises(vol.Invalid):
            CLEAR_CATEGORY_SCHEMA({ATTR_CATEGORY: "not_a_real_category"})

    def test_all_known_categories_are_valid(self):
        for cat in ALL_CATEGORIES:
            result = CLEAR_CATEGORY_SCHEMA({ATTR_CATEGORY: cat})
            assert result[ATTR_CATEGORY] == cat

    def test_optional_entry_id_accepted(self):
        result = CLEAR_CATEGORY_SCHEMA(
            {ATTR_CATEGORY: CATEGORY_NETWORK_WAN, ATTR_ENTRY_ID: "entry-abc"}
        )
        assert result[ATTR_ENTRY_ID] == "entry-abc"

    def test_missing_category_raises(self):
        with pytest.raises(vol.Invalid):
            CLEAR_CATEGORY_SCHEMA({})


class TestClearAllSchema:
    def test_empty_call_passes(self):
        result = CLEAR_ALL_SCHEMA({})
        assert ATTR_ENTRY_ID not in result

    def test_optional_entry_id_accepted(self):
        result = CLEAR_ALL_SCHEMA({ATTR_ENTRY_ID: "entry-xyz"})
        assert result[ATTR_ENTRY_ID] == "entry-xyz"


# ── _handle_clear_category ────────────────────────────────────────────────────


class TestHandleClearCategory:
    @pytest.mark.asyncio
    async def test_clears_alerting_category(self):
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coordinator = make_coordinator({CATEGORY_NETWORK_WAN: wan_state})
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN})

        await _handle_clear_category(call)

        assert wan_state.is_alerting is False

    @pytest.mark.asyncio
    async def test_cancels_pending_clear_task(self):
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coordinator = make_coordinator({CATEGORY_NETWORK_WAN: wan_state})
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN})

        await _handle_clear_category(call)

        coordinator.cancel_clear.assert_called_once_with(CATEGORY_NETWORK_WAN)

    @pytest.mark.asyncio
    async def test_calls_async_set_updated_data(self):
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coordinator = make_coordinator({CATEGORY_NETWORK_WAN: wan_state})
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN})

        await _handle_clear_category(call)

        coordinator.async_set_updated_data.assert_called_once_with(coordinator.category_states)

    @pytest.mark.asyncio
    async def test_non_alerting_category_does_not_notify(self):
        """If the category is not alerting, no update should be dispatched."""
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=False)
        coordinator = make_coordinator({CATEGORY_NETWORK_WAN: wan_state})
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN})

        await _handle_clear_category(call)

        coordinator.async_set_updated_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_id_filter_targets_only_matching_entry(self):
        """entry_id kwarg must restrict clearing to only the specified entry."""
        state_a = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        state_b = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coord_a = make_coordinator({CATEGORY_NETWORK_WAN: state_a})
        coord_b = make_coordinator({CATEGORY_NETWORK_WAN: state_b})
        hass = make_hass({"entry-a": coord_a, "entry-b": coord_b})
        call = make_call(
            hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN, ATTR_ENTRY_ID: "entry-a"}
        )

        await _handle_clear_category(call)

        assert state_a.is_alerting is False
        assert state_b.is_alerting is True  # not touched

    @pytest.mark.asyncio
    async def test_unknown_entry_id_logs_warning_and_does_nothing(self):
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coordinator = make_coordinator({CATEGORY_NETWORK_WAN: wan_state})
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(
            hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN, ATTR_ENTRY_ID: "no-such-entry"}
        )

        with patch("custom_components.unifi_alerts.services._LOGGER") as mock_log:
            await _handle_clear_category(call)

        mock_log.warning.assert_called_once()
        assert wan_state.is_alerting is True  # unchanged

    @pytest.mark.asyncio
    async def test_affects_all_entries_when_entry_id_omitted(self):
        """Without entry_id, every coordinator's state should be cleared."""
        state_a = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        state_b = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coord_a = make_coordinator({CATEGORY_NETWORK_WAN: state_a})
        coord_b = make_coordinator({CATEGORY_NETWORK_WAN: state_b})
        hass = make_hass({"entry-a": coord_a, "entry-b": coord_b})
        call = make_call(hass, {ATTR_CATEGORY: CATEGORY_NETWORK_WAN})

        await _handle_clear_category(call)

        assert state_a.is_alerting is False
        assert state_b.is_alerting is False


# ── _handle_clear_all ─────────────────────────────────────────────────────────


class TestHandleClearAll:
    @pytest.mark.asyncio
    async def test_clears_all_alerting_categories(self):
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        threat_state = make_state(CATEGORY_SECURITY_THREAT, is_alerting=True)
        coordinator = make_coordinator(
            {CATEGORY_NETWORK_WAN: wan_state, CATEGORY_SECURITY_THREAT: threat_state}
        )
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {})

        await _handle_clear_all(call)

        assert wan_state.is_alerting is False
        assert threat_state.is_alerting is False

    @pytest.mark.asyncio
    async def test_skips_non_alerting_categories(self):
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        quiet_state = make_state(CATEGORY_SECURITY_THREAT, is_alerting=False)
        coordinator = make_coordinator(
            {CATEGORY_NETWORK_WAN: wan_state, CATEGORY_SECURITY_THREAT: quiet_state}
        )
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {})

        await _handle_clear_all(call)

        # Only WAN was alerting — cancel_clear should be called once for it
        coordinator.cancel_clear.assert_called_once_with(CATEGORY_NETWORK_WAN)

    @pytest.mark.asyncio
    async def test_calls_async_set_updated_data_once_per_coordinator(self):
        """Even with multiple alerting categories, only one listener dispatch per coordinator."""
        wan_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        threat_state = make_state(CATEGORY_SECURITY_THREAT, is_alerting=True)
        coordinator = make_coordinator(
            {CATEGORY_NETWORK_WAN: wan_state, CATEGORY_SECURITY_THREAT: threat_state}
        )
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {})

        await _handle_clear_all(call)

        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_dispatch_when_nothing_alerting(self):
        quiet_state = make_state(CATEGORY_NETWORK_WAN, is_alerting=False)
        coordinator = make_coordinator({CATEGORY_NETWORK_WAN: quiet_state})
        hass = make_hass({"entry-abc": coordinator})
        call = make_call(hass, {})

        await _handle_clear_all(call)

        coordinator.async_set_updated_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_id_filter_targets_only_matching_entry(self):
        state_a = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        state_b = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        coord_a = make_coordinator({CATEGORY_NETWORK_WAN: state_a})
        coord_b = make_coordinator({CATEGORY_NETWORK_WAN: state_b})
        hass = make_hass({"entry-a": coord_a, "entry-b": coord_b})
        call = make_call(hass, {ATTR_ENTRY_ID: "entry-a"})

        await _handle_clear_all(call)

        assert state_a.is_alerting is False
        assert state_b.is_alerting is True  # not touched

    @pytest.mark.asyncio
    async def test_affects_all_entries_when_entry_id_omitted(self):
        state_a = make_state(CATEGORY_NETWORK_WAN, is_alerting=True)
        state_b = make_state(CATEGORY_SECURITY_THREAT, is_alerting=True)
        coord_a = make_coordinator({CATEGORY_NETWORK_WAN: state_a})
        coord_b = make_coordinator({CATEGORY_SECURITY_THREAT: state_b})
        hass = make_hass({"entry-a": coord_a, "entry-b": coord_b})
        call = make_call(hass, {})

        await _handle_clear_all(call)

        assert state_a.is_alerting is False
        assert state_b.is_alerting is False


# ── async_register_services / async_unregister_services ──────────────────────


class TestServiceRegistration:
    def _make_hass_with_services(self, has_category: bool = False, has_all: bool = False):
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.has_service = MagicMock(
            side_effect=lambda domain, name: (
                (name == SERVICE_CLEAR_CATEGORY and has_category)
                or (name == SERVICE_CLEAR_ALL and has_all)
            )
        )
        hass.services.async_register = MagicMock()
        hass.services.async_remove = MagicMock()
        return hass

    def test_registers_both_services_on_first_call(self):
        hass = self._make_hass_with_services()
        async_register_services(hass)
        assert hass.services.async_register.call_count == 2

    def test_idempotent_when_services_already_registered(self):
        hass = self._make_hass_with_services(has_category=True, has_all=True)
        async_register_services(hass)
        hass.services.async_register.assert_not_called()

    def test_registers_only_missing_service(self):
        # category already registered, clear_all missing
        hass = self._make_hass_with_services(has_category=True, has_all=False)
        async_register_services(hass)
        # Only clear_all should be registered
        assert hass.services.async_register.call_count == 1
        registered_name = hass.services.async_register.call_args[0][1]
        assert registered_name == SERVICE_CLEAR_ALL

    def test_unregister_removes_both_services(self):
        hass = self._make_hass_with_services(has_category=True, has_all=True)
        async_unregister_services(hass)
        assert hass.services.async_remove.call_count == 2

    def test_unregister_is_safe_when_services_not_registered(self):
        hass = self._make_hass_with_services(has_category=False, has_all=False)
        async_unregister_services(hass)  # must not raise
        hass.services.async_remove.assert_not_called()


# ── integration with __init__.py wiring ───────────────────────────────────────


class TestServicesWiredFromInit:
    """Verify that __init__.async_setup_entry calls register_services and
    async_unload_entry calls unregister_services only when last entry is gone."""

    def _make_setup_patches(self):
        mock_coordinator = MagicMock()
        mock_coordinator.async_config_entry_first_refresh = MagicMock(return_value=None)
        mock_coordinator.async_config_entry_first_refresh.__await__ = lambda self: iter([None])
        from unittest.mock import AsyncMock

        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_coordinator.push_alert = MagicMock()

        mock_client = MagicMock()
        mock_client.authenticate = AsyncMock()
        mock_client.close = AsyncMock()

        mock_wm = MagicMock()
        mock_wm.register_all = MagicMock(return_value={})
        mock_wm.unregister_all = MagicMock()
        return mock_client, mock_coordinator, mock_wm

    @pytest.mark.asyncio
    async def test_register_services_called_on_setup(self):
        from conftest import make_entry, make_hass

        from custom_components.unifi_alerts import async_setup_entry

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coord, mock_wm = self._make_setup_patches()

        with (
            patch(
                "custom_components.unifi_alerts.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.unifi_alerts.UniFiClient", return_value=mock_client),
            patch(
                "custom_components.unifi_alerts.UniFiAlertsCoordinator",
                return_value=mock_coord,
            ),
            patch("custom_components.unifi_alerts.WebhookManager", return_value=mock_wm),
            patch(
                "custom_components.unifi_alerts.async_register_services"
            ) as mock_register,
        ):
            await async_setup_entry(hass, entry)

        mock_register.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_unregister_services_called_when_last_entry_unloads(self):
        from conftest import make_entry, make_hass

        from custom_components.unifi_alerts import async_unload_entry
        from custom_components.unifi_alerts.const import DATA_COORDINATOR, DATA_UNREGISTER_WEBHOOKS, DATA_WEBHOOK_IDS

        hass = make_hass()
        entry = make_entry()
        mock_client, mock_coord, mock_wm = self._make_setup_patches()

        # Populate as if setup completed
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            DATA_COORDINATOR: mock_coord,
            DATA_WEBHOOK_IDS: {},
            DATA_UNREGISTER_WEBHOOKS: mock_wm.unregister_all,
            "client": mock_client,
        }

        with patch(
            "custom_components.unifi_alerts.async_unregister_services"
        ) as mock_unregister:
            await async_unload_entry(hass, entry)

        mock_unregister.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_unregister_services_not_called_when_entries_remain(self):
        from conftest import make_entry, make_hass

        from custom_components.unifi_alerts import async_unload_entry
        from custom_components.unifi_alerts.const import DATA_COORDINATOR, DATA_UNREGISTER_WEBHOOKS, DATA_WEBHOOK_IDS

        hass = make_hass()
        entry1 = make_entry(entry_id="entry-1")
        entry2 = make_entry(entry_id="entry-2")
        mock_client, mock_coord, mock_wm = self._make_setup_patches()

        # Two entries registered
        hass.data.setdefault(DOMAIN, {})
        for eid in (entry1.entry_id, entry2.entry_id):
            hass.data[DOMAIN][eid] = {
                DATA_COORDINATOR: mock_coord,
                DATA_WEBHOOK_IDS: {},
                DATA_UNREGISTER_WEBHOOKS: mock_wm.unregister_all,
                "client": mock_client,
            }

        with patch(
            "custom_components.unifi_alerts.async_unregister_services"
        ) as mock_unregister:
            # Unload only entry1 — entry2 still remains
            await async_unload_entry(hass, entry1)

        mock_unregister.assert_not_called()
