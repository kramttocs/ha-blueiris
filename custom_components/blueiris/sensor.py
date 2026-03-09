"""Sensor platform for Blue Iris."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator, CameraLastEvent
from .helpers.const import DOMAIN, SENSOR_MOTION_NAME
from .helpers.device import camera_device_info, camera_model, server_device_info
from .helpers.entity import base_name, is_allowed


@dataclass(frozen=True, kw_only=True)
class BlueIrisSensorEntityDescription(SensorEntityDescription):
    """Describes a Blue Iris sensor entity."""


CONNECTION_HEALTH_DESCRIPTION = BlueIrisSensorEntityDescription(
    key="connection_health",
    name="Connection Health",
    icon="mdi:heart-pulse",
)

LAST_EVENT_DESCRIPTION = BlueIrisSensorEntityDescription(
    key="last_event",
    name="Last Event",
    icon="mdi:image-search",
)


def _motion_sensor_enabled(coordinator: BlueIrisDataUpdateCoordinator, camera_id: str) -> bool:
    """Return True when the camera's Motion sensor is allowed/created."""
    allowed = coordinator.api.config.allowed_motion_sensor
    return is_allowed(allowed, camera_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Create server-level and per-camera sensors for the config entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [BlueIrisConnectionHealthSensor(coordinator, entry)]

    if coordinator.data is not None:
        for cam_id, cam in coordinator.data.cameras.items():
            if cam.is_system:
                continue
            if not _motion_sensor_enabled(coordinator, cam_id):
                continue
            entities.append(BlueIrisCameraLastEventSensor(coordinator, cam_id))

    async_add_entities(entities)


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
        self._attr_unique_id = f"{entry.entry_id}_connection_health"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach this sensor under the integration server device."""
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
        """Return the high-level connectivity state for the integration."""
        auth_failures = getattr(self.coordinator, "auth_failures", 0)
        consecutive_failures = getattr(self.coordinator, "consecutive_failures", 0)

        if self.coordinator.last_update_success:
            return "connected"
        if auth_failures > 0:
            return "auth_failed"
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


class BlueIrisCameraLastEventSensor(CoordinatorEntity[BlueIrisData], SensorEntity):
    """High-level per-camera latest AI event sensor."""

    entity_description = LAST_EVENT_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator, camera_id: str) -> None:
        super().__init__(coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{camera_id}_last_event"

    @property
    def _camera(self):
        data = self.coordinator.data
        if not data:
            return None
        return data.cameras.get(self.camera_id)

    @property
    def _event(self) -> CameraLastEvent | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.last_events.get(self.camera_id)

    @property
    def device_info(self) -> DeviceInfo:
        cam = self._camera
        return camera_device_info(
            self.coordinator.entry.entry_id,
            self.camera_id,
            name=f"{base_name(self.coordinator)} {cam.name if cam else self.camera_id}",
            model=camera_model(cam.type if cam else None),
        )

    @property
    def available(self) -> bool:
        cam = self._camera
        return cam is not None and self.coordinator.last_update_success

    @property
    def native_value(self) -> str | None:
        event = self._event
        return event.state if event is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self._event
        if event is None:
            return {"camera_id": self.camera_id}

        return {
            "camera_id": self.camera_id,
            "event_type": event.event_type,
            "snapshot_url": event.snapshot_url,
            "last_detection": event.last_detection,
            "memo": event.memo,
            "labels": event.labels,
            "matched_labels": event.matched_labels,
            "stored_path": event.stored_path,
        }
