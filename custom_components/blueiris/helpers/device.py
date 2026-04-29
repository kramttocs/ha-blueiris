"""DeviceInfo helpers shared across platforms.

These helpers centralize DeviceInfo construction to avoid drift across platforms.
They are intentionally minimal and preserve existing identifiers/via_device patterns.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import CAMERA_TYPE_MAPPING, DOMAIN
from .entity import base_name


def server_device_name(coordinator: Any) -> str:
    """Return the standardized server device display name."""
    return f"{base_name(coordinator)} Server"


def server_device_info(
    entry_id: str,
    *,
    name: str,
    sw_version: str | None = None,
    manufacturer: str = "Blue Iris",
    model: str = "Server",
) -> DeviceInfo:
    """Return DeviceInfo for the Blue Iris server/system device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_server")},
        name=name,
        manufacturer=manufacturer,
        model=model,
        sw_version=sw_version,
    )


def camera_device_info(
    entry_id: str,
    camera_id: str,
    *,
    name: str,
    model: str,
    manufacturer: str = "Blue Iris",
) -> DeviceInfo:
    """Return DeviceInfo for a camera, linked via the server/system device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_cam_{camera_id}")},
        name=name,
        manufacturer=manufacturer,
        model=model,
        via_device=(DOMAIN, f"{entry_id}_server"),
    )


def camera_model(camera_type: object) -> str:
    """Map a Blue Iris camera type code to a friendly device model string."""
    if isinstance(camera_type, int):
        return CAMERA_TYPE_MAPPING.get(camera_type, "Camera")
    return "Camera"