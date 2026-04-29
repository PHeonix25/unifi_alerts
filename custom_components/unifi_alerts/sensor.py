"""Sensor platform for UniFi Alerts."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ALL_CATEGORIES,
    CATEGORY_ICONS,
    CATEGORY_ICONS_OK,
    CATEGORY_LABELS,
    CONF_CONTROLLER_URL,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import UniFiAlertsCoordinator
from .models import CategoryState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UniFiAlertsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities: list[SensorEntity] = []
    for category in ALL_CATEGORIES:
        if coordinator.get_category_state(category) is not None:
            entities.append(UniFiCategoryMessageSensor(coordinator, entry, category))
            entities.append(UniFiCategoryCountSensor(coordinator, entry, category))

    entities.append(UniFiRollupCountSensor(coordinator, entry))
    async_add_entities(entities)


class UniFiCategoryMessageSensor(CoordinatorEntity[UniFiAlertsCoordinator], SensorEntity):
    """Sensor whose state is the last alert message for a category."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
        category: str,
    ) -> None:
        super().__init__(coordinator)
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_{category}_message"
        self._attr_name = f"{CATEGORY_LABELS[category]} — Last Message"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        state: CategoryState | None = self.coordinator.get_category_state(self._category)
        if not state or not state.last_alert:
            return "No alerts yet"
        return state.last_alert.message

    @property
    def available(self) -> bool:
        state = self.coordinator.get_category_state(self._category)
        return state is not None and state.enabled

    @property
    def icon(self) -> str:
        state = self.coordinator.get_category_state(self._category)
        if state and state.is_alerting:
            return CATEGORY_ICONS[self._category]
        return CATEGORY_ICONS_OK[self._category]

    @property
    def extra_state_attributes(self) -> dict:
        state: CategoryState | None = self.coordinator.get_category_state(self._category)
        if not state or not state.last_alert:
            return {}
        return {
            "received_at": state.last_alert.received_at.isoformat(),
            "device_name": state.last_alert.device_name,
            "alert_key": state.last_alert.key,
            "severity": state.last_alert.severity,
            "site": state.last_alert.site,
        }


class UniFiCategoryCountSensor(CoordinatorEntity[UniFiAlertsCoordinator], SensorEntity):
    """Sensor whose state is the number of open (unarchived) alarms for a category."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "alerts"
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
        category: str,
    ) -> None:
        super().__init__(coordinator)
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_{category}_count"
        self._attr_name = f"{CATEGORY_LABELS[category]} — Open Count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        state: CategoryState | None = self.coordinator.get_category_state(self._category)
        return state.open_count if state else 0

    @property
    def available(self) -> bool:
        state = self.coordinator.get_category_state(self._category)
        return state is not None and state.enabled


class UniFiRollupCountSensor(CoordinatorEntity[UniFiAlertsCoordinator], SensorEntity):
    """Sensor: total open alert count across all enabled categories."""

    _attr_has_entity_name = True
    _attr_name = "Total Open Alerts"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "alerts"
    _attr_icon = "mdi:bell-alert"

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_rollup_count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        return self.coordinator.rollup_open_count

    @property
    def extra_state_attributes(self) -> dict:
        last = self.coordinator.rollup_last_alert
        attrs: dict = {"total_webhook_count": self.coordinator.rollup_alert_count}
        if last:
            attrs["last_message"] = last.message
            attrs["last_category"] = last.category
            attrs["last_alert_at"] = last.received_at.isoformat()
        return attrs


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="UniFi Alerts",
        manufacturer="Ubiquiti",
        model="UniFi Network Controller",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=entry.data.get(CONF_CONTROLLER_URL),
    )
