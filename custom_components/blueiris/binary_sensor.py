"""Binary sensor platform for Blue Iris (MQTT driven)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator
from .helpers.mqtt import mqtt_key, topic_for_camera
from .helpers.const import (
    AI_ANIMAL_MOTION,
    AI_MOTION_TYPES,
    AI_PERSON_MOTION,
    AI_VEHICLE_MOTION,
    CAMERA_SENSORS,
    CAMERA_TYPE_MAPPING,
    DEFAULT_ICON,
    DOMAIN,
    MQTT_TOPIC_STATUS_SUFFIX,
    NEGATIVE_SENSOR_STATE,
    SENSOR_AUDIO_NAME,
    SENSOR_CONNECTIVITY_NAME,
    SENSOR_DIO_NAME,
    SENSOR_EXTERNAL_NAME,
    SENSOR_MOTION_NAME,
)
from .helpers.device import camera_device_info, server_device_info, server_device_name, camera_model
from .helpers.entity import base_name, is_allowed, is_explicitly_enabled, unique_id_binary_sensor


AI_DISPLAY_NAMES: Final[dict[str, str]] = {
    AI_PERSON_MOTION: "Motion Person",
    AI_VEHICLE_MOTION: "Motion Vehicle",
    AI_ANIMAL_MOTION: "Motion Animal",
}


def _default_state(sensor_type_name: str) -> bool:
    """Return the default state when no MQTT state exists yet."""
    return sensor_type_name in NEGATIVE_SENSOR_STATE


def _mqtt_state(
    coordinator: BlueIrisDataUpdateCoordinator,
    camera_id: str,
    sensor_type_name: str,
) -> bool:
    """Return the current MQTT-derived state for a camera+sensor."""
    topic = topic_for_camera(coordinator.mqtt_root, coordinator.api.system_name or "", camera_id, suffix=MQTT_TOPIC_STATUS_SUFFIX)
    default_state = _default_state(sensor_type_name)

    data = coordinator.data
    if data is None:
        return default_state

    # IMPORTANT: honor default_state when key is missing (common right after startup)
    st = data.mqtt.get(mqtt_key(topic, sensor_type_name))
    return st.value if st is not None else default_state


def _is_allowed_sensor(coordinator: BlueIrisDataUpdateCoordinator, camera, sensor_type_name: str) -> bool:
    """Return True if a given camera+sensor type should be created.

    Preserves the current option-driven behavior, including the special
    handling for DIO/External sensors (disabled unless explicitly selected).
    """
    cfg = coordinator.api.config

    if camera.is_system:
        return False

    if sensor_type_name == SENSOR_AUDIO_NAME and not camera.has_audio:
        return False

    # Treat AI memo-driven motion sensors as motion for allow-list purposes.
    allow_name = SENSOR_MOTION_NAME if sensor_type_name in AI_MOTION_TYPES else sensor_type_name

    allowed_map = {
        SENSOR_MOTION_NAME: cfg.allowed_motion_sensor,
        SENSOR_AUDIO_NAME: cfg.allowed_audio_sensor,
        SENSOR_CONNECTIVITY_NAME: cfg.allowed_connectivity_sensor,
        SENSOR_DIO_NAME: cfg.allowed_dio_sensor,
        SENSOR_EXTERNAL_NAME: cfg.allowed_external_sensor,
    }
    allowed = allowed_map.get(allow_name)

    # DIO/External should be OFF unless explicitly selected in Options
    if allow_name in (SENSOR_DIO_NAME, SENSOR_EXTERNAL_NAME):
        return is_explicitly_enabled(allowed, camera.id)

    return is_allowed(allowed, camera.id)


@dataclass(frozen=True, kw_only=True)
class BlueIrisBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description for Blue Iris camera sensors."""
    sensor_type_name: str
    expose_motion_attrs: bool = False


def _camera_sensor_descriptions() -> tuple[BlueIrisBinarySensorDescription, ...]:
    """Build entity descriptions for all camera sensor types (declarative registry)."""
    descriptions: list[BlueIrisBinarySensorDescription] = []

    for sensor_type_name, device_class in CAMERA_SENSORS.items():
        descriptions.append(
            BlueIrisBinarySensorDescription(
                key=sensor_type_name,
                sensor_type_name=sensor_type_name,
                device_class=device_class if isinstance(device_class, BinarySensorDeviceClass) else None,
                expose_motion_attrs=(
                    sensor_type_name == SENSOR_MOTION_NAME or sensor_type_name in AI_MOTION_TYPES
                ),
            )
        )

    return tuple(descriptions)


CAMERA_SENSOR_DESCRIPTIONS: Final[tuple[BlueIrisBinarySensorDescription, ...]] = _camera_sensor_descriptions()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Create camera binary sensors and the aggregate alerts sensor for this entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    if coordinator.data is None:
        return

    entities: list[BinarySensorEntity] = []

    # Per-camera sensors
    for cam_id, cam in coordinator.data.cameras.items():
        for desc in CAMERA_SENSOR_DESCRIPTIONS:
            if _is_allowed_sensor(coordinator, cam, desc.sensor_type_name):
                entities.append(BlueIrisCameraBinarySensor(coordinator, cam_id, desc))

    # Main alerts sensor (only if any per-camera sensors exist)
    if entities:
        entities.insert(0, BlueIrisAlertsBinarySensor(coordinator))

    async_add_entities(entities)


class _BaseBIBinarySensor(CoordinatorEntity[BlueIrisData], BinarySensorEntity):
    """Shared CoordinatorEntity base for Blue Iris binary sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator) -> None:
        """Initialize the shared Blue Iris binary sensor base class."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the sensor to the Blue Iris server device in Home Assistant."""
        data = self.coordinator.data
        return server_device_info(
            self.coordinator.entry.entry_id,
            name=server_device_name(self.coordinator),
            sw_version=(data.server_version if data else None),
        )


class BlueIrisCameraBinarySensor(_BaseBIBinarySensor):
    """Per-camera MQTT-driven binary sensor."""

    entity_description: BlueIrisBinarySensorDescription

    def __init__(
        self,
        coordinator: BlueIrisDataUpdateCoordinator,
        camera_id: str,
        description: BlueIrisBinarySensorDescription,
    ) -> None:
        """Initialize a per-camera binary sensor for the supplied event type."""
        super().__init__(coordinator)
        self.camera_id = camera_id
        self.entity_description = description
        self.sensor_type_name = description.sensor_type_name

        # Preserve existing unique_id format
        self._attr_unique_id = unique_id_binary_sensor(
            coordinator.entry.entry_id,
            camera_id,
            self.sensor_type_name,
        )

        # Preserve display naming behavior
        self._attr_name = AI_DISPLAY_NAMES.get(self.sensor_type_name, self.sensor_type_name)

    @property
    def device_info(self) -> DeviceInfo:
        cam = self.coordinator.data.cameras.get(self.camera_id) if self.coordinator.data else None
        base = base_name(self.coordinator)

        model = camera_model(cam.type if cam else None)

        return camera_device_info(
            self.coordinator.entry.entry_id,
            self.camera_id,
            name=f"{base} {cam.name if cam else self.camera_id}",
            model=model,
        )

    @property
    def is_on(self) -> bool:
        """Return the current MQTT-derived state for this camera sensor."""
        return _mqtt_state(self.coordinator, self.camera_id, self.sensor_type_name)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose MQTT memo + label details for motion-related sensors."""
        data = self.coordinator.data
        if data is None:
            return {}

        if not self.entity_description.expose_motion_attrs:
            return {}

        topic = topic_for_camera(self.coordinator.mqtt_root, self.coordinator.api.system_name or "", self.camera_id, suffix=MQTT_TOPIC_STATUS_SUFFIX)
        key = mqtt_key(topic, self.sensor_type_name)

        st = data.mqtt.get(key)
        if not st or not st.memo:
            return {}
        
        attrs: dict[str, Any] = {"memo": st.memo}
        
        if st.labels is not None:
            attrs["labels"] = st.labels
        if st.matched_labels is not None:
            attrs["matched_labels"] = st.matched_labels
        if st.last_detection is not None:
            attrs["last_detection"] = st.last_detection
        return attrs


class BlueIrisAlertsBinarySensor(_BaseBIBinarySensor):
    """Aggregated alert sensor (same idea as legacy 'Alerts' entity)."""

    _attr_icon = DEFAULT_ICON

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator) -> None:
        """Initialize the aggregate alerts sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}-{coordinator.entry.entry_id}-bs-main-alerts"
        self._attr_name = "Alerts"

    @property
    def is_on(self) -> bool:
        """Return True when any alert attribute is currently populated."""
        attrs = self.extra_state_attributes or {}
        return any(k != "friendly_name" for k in attrs)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {"friendly_name": self._attr_name}

        alerts: dict[str, list[str]] = {}

        for cam_id, cam in data.cameras.items():
            for desc in CAMERA_SENSOR_DESCRIPTIONS:
                sensor_type_name = desc.sensor_type_name
                if not _is_allowed_sensor(self.coordinator, cam, sensor_type_name):
                    continue

                state = _mqtt_state(self.coordinator, cam_id, sensor_type_name)

                # Connectivity is inverted in legacy alerts view
                is_alert_on = (not state) if sensor_type_name == SENSOR_CONNECTIVITY_NAME else state
                if is_alert_on:
                    alerts.setdefault(sensor_type_name, []).append(
                        f"{base_name(self.coordinator)} {cam.name} {sensor_type_name}"
                    )

        attrs: dict[str, Any] = {"friendly_name": self._attr_name}
        for k, names in alerts.items():
            attrs[k] = ", ".join(names)
        return attrs