"""MQTT helpers for the Blue Iris integration.

Centralizes topic parsing / construction and the canonical key used for MQTT-derived states.

Pure refactor helper (no behavior change intended).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ParsedTopic:
    """Parsed Blue Iris MQTT topic.

    Expected shape: <root>/<server>/<camera_id>/<suffix>
    """

    root: str
    server: str
    camera_id: str
    suffix: str

    @property
    def is_system(self) -> bool:
        """Return True when the parsed topic targets the Blue Iris system channel."""
        return self.camera_id.lower() == "system"


def parse_topic(topic: str) -> Optional[ParsedTopic]:
    """Parse a BI MQTT topic.

    Returns None when the topic does not match the expected 4-segment format.
    """
    parts = topic.split("/")
    if len(parts) != 4:
        return None
    return ParsedTopic(root=parts[0], server=parts[1], camera_id=parts[2], suffix=parts[3])


def mqtt_key(topic: str, event_type: str) -> str:
    """Canonical key for MQTT-derived states."""
    return f"{topic}::{event_type}".lower()


def topic_for_camera(mqtt_root: str, system_name: str, camera_id: str, *, suffix: str) -> str:
    """Build the per-camera BI MQTT topic."""
    server = (system_name or "").strip()
    return f"{mqtt_root}/{server}/{camera_id}/{suffix}"


def subscription_topic(mqtt_root: str, system_name: str, *, suffix: str) -> str:
    """Build the subscription topic (wildcard camera segment)."""
    server = (system_name or "").strip()
    return f"{mqtt_root}/{server}/+/{suffix}"
