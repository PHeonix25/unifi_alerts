"""Button platform for UniFi Alerts — manual alert clear buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ALL_CATEGORIES,
    CATEGORY_LABELS,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import UniFiAlertsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UniFiAlertsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[ButtonEntity] = [
        UniFiClearCategoryButton(coordinator, entry, category)
        for category in ALL_CATEGORIES
        if coordinator.get_category_state(category) is not None
    ]
    entities.append(UniFiClearAllButton(coordinator, entry))
    async_add_entities(entities)


class UniFiClearCategoryButton(ButtonEntity):
    """Button that manually clears the alert state for one category."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bell-off"

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
        category: str,
    ) -> None:
        self._coordinator = coordinator
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_{category}_clear"
        self._attr_name = f"Clear {CATEGORY_LABELS[category]}"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        self._coordinator.cancel_clear(self._category)
        state = self._coordinator.get_category_state(self._category)
        if state:
            state.clear()
            self._coordinator.async_set_updated_data(self._coordinator.category_states)


class UniFiClearAllButton(ButtonEntity):
    """Button that clears alert state for all categories at once."""

    _attr_has_entity_name = True
    _attr_name = "Clear All Alerts"
    _attr_icon = "mdi:shield-off"

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_clear_all"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        for category, state in self._coordinator.category_states.items():
            if state.is_alerting:
                self._coordinator.cancel_clear(category)
                state.clear()
        self._coordinator.async_set_updated_data(self._coordinator.category_states)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="UniFi Alerts",
        manufacturer="Ubiquiti",
        model="UniFi Network Controller",
        entry_type=DeviceEntryType.SERVICE,
    )
