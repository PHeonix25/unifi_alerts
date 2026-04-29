"""Event platform for UniFi Alerts.

Event entities fire once per alert and carry no persistent state — ideal
for automations that should trigger on *each* alert rather than a state change.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ALL_CATEGORIES,
    CATEGORY_ICONS,
    CATEGORY_LABELS,
    CONF_CONTROLLER_URL,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import UniFiAlertsCoordinator
from .models import CategoryState, UniFiAlert


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UniFiAlertsCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = [
        UniFiAlertEventEntity(coordinator, entry, category)
        for category in ALL_CATEGORIES
        if coordinator.get_category_state(category) is not None
    ]
    async_add_entities(entities)


class UniFiAlertEventEntity(CoordinatorEntity[UniFiAlertsCoordinator], EventEntity):
    """Fires an HA event each time an alert is received for this category.

    The event type is always "alert_received". The payload carries the
    full message, device name, key, and severity as event attributes.
    """

    _attr_has_entity_name = True
    _attr_event_types = ["alert_received"]

    def __init__(
        self,
        coordinator: UniFiAlertsCoordinator,
        entry: ConfigEntry,
        category: str,
    ) -> None:
        super().__init__(coordinator)
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_{category}_event"
        self._attr_name = f"{CATEGORY_LABELS[category]} — Event"
        self._attr_icon = CATEGORY_ICONS[category]
        self._attr_device_info = _device_info(entry)
        # Track alert_count to detect new alerts on coordinator update
        self._last_seen_count: int = 0

    @callback
    def _handle_coordinator_update(self) -> None:
        """Called whenever the coordinator has new data.

        We compare alert_count to detect a new webhook push and fire
        the event entity if the count has increased.
        """
        state: CategoryState | None = self.coordinator.get_category_state(self._category)
        if not state or not state.last_alert:
            super()._handle_coordinator_update()
            return

        new_count = state.alert_count
        if new_count > self._last_seen_count:
            self._last_seen_count = new_count
            alert: UniFiAlert = state.last_alert
            self._trigger_event(
                "alert_received",
                {
                    "message": alert.message,
                    "category": self._category,
                    "device_name": alert.device_name,
                    "alert_key": alert.key,
                    "severity": alert.severity,
                    "site": alert.site,
                    "received_at": alert.received_at.isoformat(),
                },
            )

        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        state = self.coordinator.get_category_state(self._category)
        return state is not None and state.enabled


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="UniFi Alerts",
        manufacturer="Ubiquiti",
        model="UniFi Network Controller",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=entry.data.get(CONF_CONTROLLER_URL),
    )
