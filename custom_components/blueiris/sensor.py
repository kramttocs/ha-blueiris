"""Sensor platform for Blue Iris."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator
from .helpers.const import DOMAIN
from .helpers.device import server_device_info


@dataclass(frozen=True, kw_only=True)
class BlueIrisSensorEntityDescription(SensorEntityDescription):
    """Describes a Blue Iris sensor entity."""


CONNECTION_HEALTH_DESCRIPTION = BlueIrisSensorEntityDescription(
    key="connection_health",
    name="Connection Health",
    icon="mdi:heart-pulse",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Create server-level diagnostic sensors for the config entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BlueIrisConnectionHealthSensor(coordinator, entry)])


class BlueIrisConnectionHealthSensor(
    CoordinatorEntity[BlueIrisData],
    SensorEntity,
):
    """Reports connection / update health for the integration."""

    entity_description = CONNECTION_HEALTH_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the connection health sensor with a stable unique id."""
        super().__init__(coordinator)
        self._entry = entry

        # Unique ID should be stable and deterministic
        self._attr_unique_id = f"{entry.entry_id}_connection_health"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach this sensor under the integration 'Server/System' device."""
        data = self.coordinator.data
        system_name = data.system_name if data else None
        name = (system_name or self._entry.title or "BlueIris").strip()

        return server_device_info(
            self._entry.entry_id,
            name=f"{name} Server",
            sw_version=(data.server_version if data else None),
        )

    @property
    def native_value(self) -> str:
        """
        Human-friendly state.

        Values:
        - connected
        - reconnecting
        - auth_failed
        - server_unreachable
        """
        # If you add the coordinator counters below, these will exist.
        auth_failures = getattr(self.coordinator, "auth_failures", 0)
        consecutive_failures = getattr(self.coordinator, "consecutive_failures", 0)

        if self.coordinator.last_update_success:
            return "connected"

        # If we have auth failures, call it auth_failed
        if auth_failures > 0:
            return "auth_failed"

        # If we’re failing but no explicit auth signal, it’s likely connectivity/BI down
        if consecutive_failures > 0:
            return "server_unreachable"

        return "reconnecting"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Helpful attributes for dashboards and troubleshooting."""
        data = self.coordinator.data
        status = data.status if data else {}
        login_data = data.data if data else {}

        return {
            "last_update_success": self.coordinator.last_update_success,
            "last_success_time": self.coordinator.last_success_time.isoformat()
            if getattr(self.coordinator, "last_success_time", None)
            else None,
            "consecutive_failures": getattr(self.coordinator, "consecutive_failures", 0),
            "auth_failures": getattr(self.coordinator, "auth_failures", 0),
            "session_id": data.session_id if data else None,
            "base_url": data.base_url if data else None,
            "system_name": data.system_name if data else None,
            "bi_version": login_data.get("version"),
            "bi_new_version": data.new_version if data else None,
            "profile": status.get("profile"),
            "schedule": status.get("schedule"),
        }
