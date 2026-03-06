"""Constants for the Blue Iris integration."""

from __future__ import annotations

from datetime import timedelta
from homeassistant.const import Platform
from typing import Final

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

DOMAIN: Final[str] = "blueiris"
DEFAULT_NAME: Final[str] = "BlueIris"
DEFAULT_PORT: Final[int] = 81
DEFAULT_VERSION: Final[str] = "0.0.0.0"

CONF_LOG_LEVEL: Final[str] = "log_level"
LOG_LEVEL_DEFAULT: Final[str] = "Default"

CONF_HOLD_PROFILE_CHANGES: Final[str] = "hold_profile_changes"
DEFAULT_HOLD_PROFILE_CHANGES: Final[bool] = True

CONF_ALLOWED_CAMERA: Final[str] = "allowed_camera"
CONF_ALLOWED_PROFILE: Final[str] = "allowed_profile"
CONF_ALLOWED_SCHEDULE: Final[str] = "allowed_schedule"
CONF_ALLOWED_MOTION_SENSOR: Final[str] = "allowed_motion_sensor"
CONF_ALLOWED_AUDIO_SENSOR: Final[str] = "allowed_audio_sensor"
CONF_ALLOWED_CONNECTIVITY_SENSOR: Final[str] = "allowed_connectivity_sensor"
CONF_ALLOWED_DIO_SENSOR: Final[str] = "allowed_dio_sensor"
CONF_ALLOWED_EXTERNAL_SENSOR: Final[str] = "allowed_external_sensor"


# AI label customization (one label per line in options UI; normalized to lowercase)
CONF_AI_PERSON_LABELS: Final[str] = "ai_person_labels"
CONF_AI_VEHICLE_LABELS: Final[str] = "ai_vehicle_labels"
CONF_AI_ANIMAL_LABELS: Final[str] = "ai_animal_labels"

CONF_SUPPORT_STREAM: Final[str] = "support_stream"

# NOTE: This key uses a hyphen in your current codebase/config entries.
# Keep as-is unless you also migrate existing stored options + translations.
CONF_STREAM_TYPE: Final[str] = "stream-type"
STREAM_TYPE_H264: Final[str] = "H264"
STREAM_TYPE_MJPG: Final[str] = "MJPEG"
DEFAULT_STREAM_TYPE: Final[str] = STREAM_TYPE_H264

STREAM_VIDEO: Final[dict[str, dict[str, str]]] = {
    STREAM_TYPE_H264: {"file_name": "temp.m3u8", "stream_name": "h264"},
    STREAM_TYPE_MJPG: {"stream_name": "mjpg"},
}

DOMAIN_LOGGER: Final[str] = "logger"
DOMAIN_STREAM: Final[str] = "stream"

DEFAULT_CONTENT_TYPE: Final[str] = "image/jpeg"
DEFAULT_QOS: Final[int] = 0

SCAN_INTERVAL = timedelta(seconds=25)

DEFAULT_ICON: Final[str] = "mdi:eye-circle"
PROFILE_ICON: Final[str] = "mdi:shield-home"
SCHEDULE_ICON: Final[str] = "mdi:calendar-clock"

SERVICE_SET_LEVEL: Final[str] = "set_level"
SERVICE_TRIGGER_CAMERA: Final[str] = "trigger_camera"
SERVICE_MOVE_TO_PRESET: Final[str] = "move_to_preset"
SERVICE_RELOAD: Final[str] = "reload"
SERVICE_RELOAD_ENTRY_ID: Final[str] = "entry_id"

ATTR_ADMIN_PROFILE: Final[str] = "Profile"
ATTR_ADMIN_SCHEDULE: Final[str] = "Schedule"

# System camera ids
ATTR_SYSTEM_CAMERA_ALL_ID: Final[str] = "index"
ATTR_SYSTEM_CAMERA_CYCLE_ID: Final[str] = "@index"
SYSTEM_CAMERA_ID: Final[set[str]] = {ATTR_SYSTEM_CAMERA_ALL_ID, ATTR_SYSTEM_CAMERA_CYCLE_ID}

# Blue Iris API attribute keys
BI_ATTR_NAME: Final[str] = "optionDisplay"
BI_ATTR_ID: Final[str] = "optionValue"
BI_ATTR_AUDIO: Final[str] = "audio"
BI_ATTR_IS_ONLINE: Final[str] = "isOnline"
BI_ATTR_IS_ENABLED: Final[str] = "isEnabled"
BI_ATTR_IS_ACTIVE: Final[str] = "active"
BI_ATTR_GROUP: Final[str] = "group"
BI_ATTR_TYPE: Final[str] = "type"
BI_ATTR_SYSTEM_NAME: Final[str] = "system name"

# Camera type ids
BI_CAMERA_TYPE_GENERIC: Final[int] = -3
BI_CAMERA_TYPE_GROUP: Final[int] = -1
BI_CAMERA_TYPE_SYSTEM: Final[int] = 0
BI_CAMERA_TYPE_NETWORK_IP: Final[int] = 4
BI_CAMERA_TYPE_BROADCAST: Final[int] = 5
BI_CAMERA_TYPE_SCREEN_CAPTURE: Final[int] = 99  # not sure this exists
BI_CAMERA_TYPE_USB_FIREWIRE_ANALOG: Final[int] = 99  # not sure this exists

# Camera type labels (required by CAMERA_TYPE_MAPPING)
BI_CAMERA_TYPE_GENERIC_LABEL: Final[str] = "Generic"
BI_CAMERA_TYPE_SYSTEM_LABEL: Final[str] = "System"
BI_CAMERA_TYPE_GROUP_LABEL: Final[str] = "Group"
BI_CAMERA_TYPE_NETWORK_IP_LABEL: Final[str] = "Network IP Camera"
BI_CAMERA_TYPE_BROADCAST_LABEL: Final[str] = "Broadcast Camera"
BI_CAMERA_TYPE_SCREEN_CAPTURE_LABEL: Final[str] = "Screen Capture"
BI_CAMERA_TYPE_USB_FIREWIRE_ANALOG_LABEL: Final[str] = "USB/Firewire/Analog Camera"

# This is imported/used elsewhere AND depends on the label constants above
CAMERA_TYPE_MAPPING: Final[dict[int, str]] = {
    BI_CAMERA_TYPE_GENERIC: BI_CAMERA_TYPE_GENERIC_LABEL,
    BI_CAMERA_TYPE_SYSTEM: BI_CAMERA_TYPE_SYSTEM_LABEL,
    BI_CAMERA_TYPE_GROUP: BI_CAMERA_TYPE_GROUP_LABEL,
    BI_CAMERA_TYPE_NETWORK_IP: BI_CAMERA_TYPE_NETWORK_IP_LABEL,
    BI_CAMERA_TYPE_BROADCAST: BI_CAMERA_TYPE_BROADCAST_LABEL,
    BI_CAMERA_TYPE_SCREEN_CAPTURE: BI_CAMERA_TYPE_SCREEN_CAPTURE_LABEL,
    BI_CAMERA_TYPE_USB_FIREWIRE_ANALOG: BI_CAMERA_TYPE_USB_FIREWIRE_ANALOG_LABEL,
}

# Sensor names / types
SENSOR_CONNECTIVITY_NAME: Final[str] = "Connectivity"
SENSOR_MOTION_NAME: Final[str] = "Motion"
SENSOR_EXTERNAL_NAME: Final[str] = "External"
SENSOR_DIO_NAME: Final[str] = "DIO"
SENSOR_AUDIO_NAME: Final[str] = "Audio"

NEGATIVE_SENSOR_STATE: Final[list[str]] = [SENSOR_CONNECTIVITY_NAME]

# AI motion types
AI_PERSON_MOTION: Final[str] = "motion_person"
AI_VEHICLE_MOTION: Final[str] = "motion_vehicle"
AI_ANIMAL_MOTION: Final[str] = "motion_animal"
AI_MOTION_TYPES: Final[tuple[str, str, str]] = (AI_PERSON_MOTION, AI_VEHICLE_MOTION, AI_ANIMAL_MOTION)

# AI label defaults
DEFAULT_PERSON_LABELS: list[str] = [
    "person",
]
DEFAULT_VEHICLE_LABELS: list[str] = [
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "train",
    "truck",
    "boat",
    "airplane",
]
DEFAULT_ANIMAL_LABELS: list[str] = [
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
]

AI_LABELS_HELP = (
    "Map Blue Iris AI memo labels into the Person/Vehicle/Animal motion sensors.\n\n"
    "Enter one or more labels per category. Matching is case-insensitive but not wildcard."
)


CAMERA_SENSORS: Final[dict[str, BinarySensorDeviceClass]] = {
    SENSOR_MOTION_NAME: BinarySensorDeviceClass.MOTION,
    AI_PERSON_MOTION: BinarySensorDeviceClass.MOTION,
    AI_VEHICLE_MOTION: BinarySensorDeviceClass.MOTION,
    AI_ANIMAL_MOTION: BinarySensorDeviceClass.MOTION,
    SENSOR_CONNECTIVITY_NAME: BinarySensorDeviceClass.CONNECTIVITY,
    SENSOR_EXTERNAL_NAME: BinarySensorDeviceClass.PRESENCE,
    SENSOR_DIO_NAME: BinarySensorDeviceClass.PLUG,
    SENSOR_AUDIO_NAME: BinarySensorDeviceClass.SOUND,
}

# MQTT (native BI MQTT topic parsing)
MQTT_MESSAGE_TRIGGER: Final[str] = "trigger"
MQTT_MESSAGE_TYPE: Final[str] = "type"
MQTT_MESSAGE_VALUE_UNKNOWN: Final[str] = "unknown"
MQTT_ROOT_DEFAULT: Final[str] = "BlueIris"
MQTT_TOPIC_STATUS_SUFFIX = "Status"
MQTT_TOPIC_SYSTEM_SEGMENT = "System"

# BI payload "type" -> your internal sensor key
MQTT_TYPE_TO_SENSOR_KEY = {
    "motion": SENSOR_MOTION_NAME,
    "audio": SENSOR_AUDIO_NAME,
    "connectivity": SENSOR_CONNECTIVITY_NAME,
    "dio": SENSOR_DIO_NAME,
    "external": SENSOR_EXTERNAL_NAME,
}

PLATFORMS: Final[tuple[Platform, ...]] = (Platform.BINARY_SENSOR, Platform.CAMERA, Platform.SWITCH, Platform.SENSOR, Platform.UPDATE,)
