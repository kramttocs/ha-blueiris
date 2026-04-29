"""Diagnostics support for the Blue Iris integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .helpers.const import DOMAIN


def _iso(dt: Any) -> str | None:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    device_reg = dr.async_get(hass)
    devices = [
        {
            "id": device.id,
            "name": device.name,
            "model": device.model,
            "manufacturer": device.manufacturer,
        }
        for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    ]

    api = getattr(coordinator, "api", None)

    # Sanitized runtime snapshot (no credentials, no raw BI payloads)
    snapshot: dict[str, Any] = {}
    if coordinator is not None and getattr(coordinator, "data", None) is not None:
        data = coordinator.data
        snapshot = {
            "counts": {
                "cameras": len(getattr(data, "cameras", {}) or {}),
                "mqtt_states": len(getattr(data, "mqtt", {}) or {}),
            },
            "last_refresh_success": _iso(getattr(coordinator, "last_update_success_time", None)),
            "last_exception": str(getattr(coordinator, "last_exception", "") or "") or None,
            "camlist_refresh_interval_seconds": int(getattr(coordinator, "update_interval", 0).total_seconds()) if getattr(coordinator, "update_interval", None) else None,
            "last_camlist_refresh": _iso(getattr(coordinator, "_last_camlist_refresh", None)),
        }

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "domain": entry.domain,
            "version": entry.version,
        },
        "devices": devices,
        "api": {
            "base_url": "<redacted>",
            "is_logged_in": getattr(api, "is_logged_in", None),
            "last_status_update": _iso(getattr(api, "_last_status_update", None)),
            "last_camlist_update": _iso(getattr(api, "_last_camlist_update", None)),
        },
        "snapshot": snapshot,
    }
