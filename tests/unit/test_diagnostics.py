"""Tests for the UniFi Alerts diagnostics platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from conftest import MOCK_CONFIG

from custom_components.unifi_alerts.const import (
    ALL_CATEGORIES,
    CONF_API_KEY,
    CONF_PASSWORD,
)
from custom_components.unifi_alerts.diagnostics import async_get_config_entry_diagnostics
from custom_components.unifi_alerts.models import CategoryState

_SAMPLE_WEBHOOK_URLS = {
    cat: f"http://homeassistant.local/api/webhook/unifi_alerts_{cat}" for cat in ALL_CATEGORIES
}


def _make_entry(entry_id: str = "test_entry", extra_data: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {**MOCK_CONFIG, **(extra_data or {})}
    entry.options = {}
    return entry


def _make_entry_with_runtime(
    coordinator: MagicMock,
    entry_id: str = "test_entry",
    extra_data: dict | None = None,
) -> MagicMock:
    entry = _make_entry(entry_id=entry_id, extra_data=extra_data)
    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinator = coordinator
    entry.runtime_data.webhook_urls = _SAMPLE_WEBHOOK_URLS
    return entry


def _make_coordinator(
    any_alerting: bool = False,
    rollup_alert_count: int = 0,
    rollup_open_count: int = 0,
    category_states: dict[str, CategoryState] | None = None,
    unrecognised_keys: dict[str, int] | None = None,
) -> MagicMock:
    coordinator = MagicMock()
    coordinator.any_alerting = any_alerting
    coordinator.rollup_alert_count = rollup_alert_count
    coordinator.rollup_open_count = rollup_open_count
    coordinator.category_states = (
        category_states
        if category_states is not None
        else {cat: CategoryState(category=cat) for cat in ALL_CATEGORIES}
    )
    coordinator.unrecognised_keys = unrecognised_keys if unrecognised_keys is not None else {}
    return coordinator


class TestDiagnosticsRedaction:
    """Tests that sensitive config fields are redacted and non-sensitive fields are preserved."""

    @pytest.mark.asyncio
    async def test_redacts_password(self) -> None:
        entry = _make_entry_with_runtime(_make_coordinator())
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"][CONF_PASSWORD] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_redacts_api_key(self) -> None:
        entry = _make_entry_with_runtime(
            _make_coordinator(), extra_data={CONF_API_KEY: "super-secret-key"}
        )
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"][CONF_API_KEY] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_preserves_non_sensitive_config(self) -> None:
        entry = _make_entry_with_runtime(_make_coordinator())
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["config_entry"]["controller_url"] == "https://192.168.1.1"
        assert result["config_entry"]["username"] == "**REDACTED**"


class TestDiagnosticsContent:
    """Tests that diagnostics expose the expected coordinator state and webhook URLs."""

    @pytest.mark.asyncio
    async def test_exposes_all_webhook_urls(self) -> None:
        entry = _make_entry_with_runtime(_make_coordinator())
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["webhook_urls"] == _SAMPLE_WEBHOOK_URLS
        for cat in ALL_CATEGORIES:
            assert cat in result["webhook_urls"]

    @pytest.mark.asyncio
    async def test_includes_coordinator_state(self) -> None:
        coordinator = _make_coordinator(
            any_alerting=True, rollup_alert_count=3, rollup_open_count=5
        )
        entry = _make_entry_with_runtime(coordinator)
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["coordinator"]["any_alerting"] is True
        assert result["coordinator"]["rollup_alert_count"] == 3
        assert result["coordinator"]["rollup_open_count"] == 5

    @pytest.mark.asyncio
    async def test_exposes_per_category_state(self) -> None:
        cleared_at = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
        cat = ALL_CATEGORIES[0]
        states = {c: CategoryState(category=c) for c in ALL_CATEGORIES}
        # Use a current timestamp so webhook_health() reads "healthy" (within the
        # 7-day window) deterministically regardless of when the suite runs.
        webhook_at = datetime.now(UTC)
        states[cat] = CategoryState(
            category=cat,
            enabled=True,
            is_alerting=True,
            alert_count=4,
            open_count=2,
            last_cleared_at=cleared_at,
            last_webhook_at=webhook_at,
        )
        coordinator = _make_coordinator(category_states=states)
        entry = _make_entry_with_runtime(coordinator)
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        categories = result["coordinator"]["categories"]
        assert set(categories.keys()) == set(ALL_CATEGORIES)
        assert categories[cat] == {
            "enabled": True,
            "is_alerting": True,
            "open_count": 2,
            "alert_count": 4,
            "last_cleared_at": cleared_at.isoformat(),
            "last_webhook_at": webhook_at.isoformat(),
            "webhook_health": "healthy",
        }

    @pytest.mark.asyncio
    async def test_per_category_last_cleared_at_none_when_unset(self) -> None:
        coordinator = _make_coordinator()
        entry = _make_entry_with_runtime(coordinator)
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        for cat in ALL_CATEGORIES:
            cat_entry = result["coordinator"]["categories"][cat]
            assert cat_entry["last_cleared_at"] is None
            assert cat_entry["last_webhook_at"] is None
            assert cat_entry["webhook_health"] == "never_received"

    @pytest.mark.asyncio
    async def test_includes_unrecognised_keys(self) -> None:
        """unrecognised_keys in coordinator appear in diagnostics sorted by count descending."""
        coordinator = _make_coordinator(
            unrecognised_keys={"SOME_UNKNOWN_KEY": 3, "ANOTHER_WEIRD_KEY": 1, "FOO_BAR": 7}
        )
        entry = _make_entry_with_runtime(coordinator)
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        unrecognised = result["coordinator"]["unrecognised_keys"]
        assert unrecognised == {"FOO_BAR": 7, "SOME_UNKNOWN_KEY": 3, "ANOTHER_WEIRD_KEY": 1}
        # Verify sort order (descending by count)
        assert list(unrecognised.keys()) == ["FOO_BAR", "SOME_UNKNOWN_KEY", "ANOTHER_WEIRD_KEY"]

    @pytest.mark.asyncio
    async def test_unrecognised_keys_empty_when_all_classified(self) -> None:
        """When no unrecognised keys have been seen, the field is an empty dict."""
        coordinator = _make_coordinator(unrecognised_keys={})
        entry = _make_entry_with_runtime(coordinator)
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["coordinator"]["unrecognised_keys"] == {}


class TestDiagnosticsEdgeCases:
    """Tests for diagnostics behaviour under unusual or incomplete entry state."""

    @pytest.mark.asyncio
    async def test_handles_missing_entry_data(self) -> None:
        """Diagnostics should not raise if runtime_data is absent (e.g. during setup failure)."""
        entry = _make_entry()
        # Ensure runtime_data is not set (simulates a failed setup)
        del entry.runtime_data
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert result["webhook_urls"] == {}
        assert result["coordinator"] == {}
