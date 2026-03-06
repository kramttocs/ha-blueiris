"""Small helpers shared across entity/platform modules."""

from __future__ import annotations

from typing import Any, Iterable

from .const import DOMAIN


def base_name(coordinator: Any) -> str:
    """Return the best display name for the Blue Iris system.

    This intentionally mirrors the existing per-platform logic:
    - Prefer the system name from coordinator data (if present and non-empty)
    - Otherwise fall back to the config entry title
    - Otherwise use a stable default

    This is a pure refactor helper (no behavior change).
    """
    data = getattr(coordinator, "data", None)
    system_name = getattr(data, "system_name", None) if data else None

    if isinstance(system_name, str) and system_name.strip():
        return system_name.strip()

    entry = getattr(coordinator, "entry", None)
    title = getattr(entry, "title", None) if entry else None
    return title or "BlueIris"


def is_allowed(allowed: Iterable[str] | None, item_id: str) -> bool:
    """Return True if an item is allowed by a user option list.

    - None means "allow all" (preserves existing behavior).
    """
    return allowed is None or item_id in allowed


def is_explicitly_enabled(allowed: Iterable[str] | None, item_id: str) -> bool:
    """Return True only when the option list exists and contains the item."""
    return bool(allowed) and item_id in allowed




def unique_id_camera(entry_id: str, camera_id: str) -> str:
    """Build the stable unique id for a camera entity."""
    return f"{DOMAIN}-{entry_id}-camera-{camera_id}"


def unique_id_binary_sensor(entry_id: str, camera_id: str, sensor_key: str) -> str:
    """Build the stable unique id for a camera binary sensor entity."""
    return f"{DOMAIN}-{entry_id}-bs-{camera_id}-{sensor_key}"


def unique_id_profile(entry_id: str, profile_id: int | str) -> str:
    """Build the stable unique id for a profile switch entity."""
    return f"{DOMAIN}-{entry_id}-profile-{profile_id}"


def unique_id_schedule(entry_id: str, schedule_name: str) -> str:
    """Build the stable unique id for a schedule switch entity."""
    return f"{DOMAIN}-{entry_id}-schedule-{schedule_name}"