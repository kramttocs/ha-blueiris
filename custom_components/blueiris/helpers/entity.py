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


def unique_id_profile(entry_id: str) -> str:
    """Build the stable unique id for the profile select entity."""
    return f"{DOMAIN}-{entry_id}-profile-select"


def unique_id_schedule(entry_id: str) -> str:
    """Build the stable unique id for the schedule select entity."""
    return f"{DOMAIN}-{entry_id}-schedule-select"


def unique_id_hold_profile_changes(entry_id: str) -> str:
    """Build the stable unique id for the hold-profile-changes config switch."""
    return f"{DOMAIN}-{entry_id}-hold-profile-changes"