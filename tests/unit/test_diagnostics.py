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
    DATA_COORDINATOR,
    DATA_WEBHOOK_IDS,
    DOMAIN,
)
from custom_components.unifi_alerts.diagnostics import async_get_config_entry_diagnostics
from custom_components.unifi_alerts.models import CategoryState

_SAMPLE_WEBHOOK_URLS = {
    cat: f"http://homeassistant.local/api/webhook/unifi_alerts_{cat}" for cat in ALL_CATEGORIES
}


def _make_hass(entry_id: str, coordinator: MagicMock) -> MagicMock:
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            entry_id: {
                DATA_COORDINATOR: coordinator,
                DATA_WEBHOOK_IDS: _SAMPLE_WEBHOOK_URLS,
            }
        }
    }
    return hass


def _make_entry(entry_id: str = "test_entry", extra_data: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {**MOCK_CONFIG, **(extra_data or {})}
    entry.options = {}
    return entry


def _make_coordinator(
    any_alerting: bool = False,
    rollup_alert_count: int = 0,
    rollup_open_count: int = 0,
    category_states: dict[str, CategoryState] | None = None,
) -> MagicMock:
    coordinator = MagicMock()
    coordinator.any_alerting = any_alerting
    coordinator.rollup_alert_count = rollup_alert_count
    coordinator.rollup_open_count = rollup_open_count
    coordinator.category_states = category_states if category_states is not None else {
        cat: CategoryState(category=cat) for cat in ALL_CATEGORIES
    }
    return coordinator


@pytest.mark.asyncio
async def test_diagnostics_redacts_password() -> None:
    entry = _make_entry()
    hass = _make_hass(entry.entry_id, _make_coordinator())

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config_entry"][CONF_PASSWORD] == "**REDACTED**"


@pytest.mark.asyncio
async def test_diagnostics_redacts_api_key() -> None:
    entry = _make_entry(extra_data={CONF_API_KEY: "super-secret-key"})
    hass = _make_hass(entry.entry_id, _make_coordinator())

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config_entry"][CONF_API_KEY] == "**REDACTED**"


@pytest.mark.asyncio
async def test_diagnostics_exposes_all_webhook_urls() -> None:
    entry = _make_entry()
    hass = _make_hass(entry.entry_id, _make_coordinator())

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["webhook_urls"] == _SAMPLE_WEBHOOK_URLS
    for cat in ALL_CATEGORIES:
        assert cat in result["webhook_urls"]


@pytest.mark.asyncio
async def test_diagnostics_includes_coordinator_state() -> None:
    coordinator = _make_coordinator(any_alerting=True, rollup_alert_count=3, rollup_open_count=5)
    entry = _make_entry()
    hass = _make_hass(entry.entry_id, coordinator)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["coordinator"]["any_alerting"] is True
    assert result["coordinator"]["rollup_alert_count"] == 3
    assert result["coordinator"]["rollup_open_count"] == 5


@pytest.mark.asyncio
async def test_diagnostics_handles_missing_entry_data() -> None:
    """Diagnostics should not raise if entry data is absent (e.g. during setup failure)."""
    entry = _make_entry()
    hass = MagicMock()
    hass.data = {DOMAIN: {}}  # entry_id not present

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["webhook_urls"] == {}
    assert result["coordinator"] == {}


@pytest.mark.asyncio
async def test_diagnostics_preserves_non_sensitive_config() -> None:
    entry = _make_entry()
    hass = _make_hass(entry.entry_id, _make_coordinator())

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config_entry"]["controller_url"] == "https://192.168.1.1"
    assert result["config_entry"]["username"] == "**REDACTED**"


@pytest.mark.asyncio
async def test_diagnostics_exposes_per_category_state() -> None:
    cleared_at = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
    cat = ALL_CATEGORIES[0]
    states = {c: CategoryState(category=c) for c in ALL_CATEGORIES}
    states[cat] = CategoryState(
        category=cat,
        enabled=True,
        is_alerting=True,
        alert_count=4,
        open_count=2,
        last_cleared_at=cleared_at,
    )
    coordinator = _make_coordinator(category_states=states)
    entry = _make_entry()
    hass = _make_hass(entry.entry_id, coordinator)

    result = await async_get_config_entry_diagnostics(hass, entry)

    categories = result["coordinator"]["categories"]
    assert set(categories.keys()) == set(ALL_CATEGORIES)
    assert categories[cat] == {
        "enabled": True,
        "is_alerting": True,
        "open_count": 2,
        "alert_count": 4,
        "last_cleared_at": cleared_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_diagnostics_per_category_last_cleared_at_none_when_unset() -> None:
    coordinator = _make_coordinator()
    entry = _make_entry()
    hass = _make_hass(entry.entry_id, coordinator)

    result = await async_get_config_entry_diagnostics(hass, entry)

    for cat in ALL_CATEGORIES:
        assert result["coordinator"]["categories"][cat]["last_cleared_at"] is None
