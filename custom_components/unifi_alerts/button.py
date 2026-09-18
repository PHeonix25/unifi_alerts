"""Button platform for UniFi Alerts — manual alert clear buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALL_CATEGORIES
from .coordinator import UniFiAlertsCoordinator
from .entity_helpers import device_info_for_entry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UniFiAlertsCoordinator = entry.runtime_data.coordinator

    entities: list[ButtonEntity] = [
        UniFiClearCategoryButton(coordinator, entry, category)
        for category in ALL_CATEGORIES
        if (state := coordinator.get_category_state(category)) is not None and state.enabled
    ]
    entities.append(UniFiClearAllButton(coordinator, entry))
    async_add_entities(entities)


class UniFiClearCategoryButton(CoordinatorEntity[UniFiAlertsCoordinator], ButtonEntity):
    """Button that manually clears the alert state for one category."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
        category: str,
    ) -> None:
        super().__init__(coordinator)
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_{category}_clear"
        self._attr_translation_key = f"clear_{category}"
        self._attr_device_info = device_info_for_entry(entry)

    @property
    def available(self) -> bool:
        state = self.coordinator.get_category_state(self._category)
        if state is None:
            return False
        return state.enabled

    async def async_press(self) -> None:
        await self.coordinator.async_clear_category(self._category)


class UniFiClearAllButton(CoordinatorEntity[UniFiAlertsCoordinator], ButtonEntity):
    """Button that clears alert state for all categories at once."""

    _attr_has_entity_name = True
    _attr_translation_key = "clear_all"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_clear_all"
        self._attr_device_info = device_info_for_entry(entry)

    @property
    def available(self) -> bool:
        return any(state.enabled for state in self.coordinator.category_states.values())

    async def async_press(self) -> None:
        await self.coordinator.async_clear_all()
