from __future__ import annotations

from functools import partial

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .coordinator import BlueIrisDataUpdateCoordinator
from .helpers.device import server_device_name
from .helpers.const import (
    CONF_LOG_LEVEL,
    LOG_LEVEL_DEFAULT,
    DEFAULT_NAME,
    DOMAIN,
    DOMAIN_LOGGER,
    PLATFORMS,
    SERVICE_MOVE_TO_PRESET,
    SERVICE_SET_LEVEL,
    SERVICE_TRIGGER_CAMERA,
    SERVICE_RELOAD,
    SERVICE_RELOAD_ENTRY_ID,
    SERVICE_LATEST_MOTION_EVENT_SNAPSHOT,
    SERVICE_SNAPSHOT_FILENAME,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
TRIGGER_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_ids})
PRESET_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("preset"): cv.positive_int,
    }
)
RELOAD_SCHEMA = vol.Schema({vol.Optional(SERVICE_RELOAD_ENTRY_ID): cv.string})
LATEST_MOTION_EVENT_SNAPSHOT_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): vol.Any(cv.entity_id, [cv.entity_id]),
        vol.Optional(SERVICE_SNAPSHOT_FILENAME): cv.string,
    }
)


def _coordinator_and_camera_id_from_entity_id(
    hass: HomeAssistant,
    entity_id: str,
) -> tuple[BlueIrisDataUpdateCoordinator, str]:
    """Resolve the owning coordinator and camera_id for a camera entity_id."""
    state = hass.states.get(entity_id)
    if state is None:
        raise ServiceValidationError(f"Unknown entity_id: {entity_id}")

    camera_id = state.attributes.get("camera_id")
    if not camera_id:
        raise ServiceValidationError(f"{entity_id} has no 'camera_id' attribute")

    camera_id = str(camera_id)

    # Find which config entry/coordinator owns this camera_id.
    for coordinator in hass.data.get(DOMAIN, {}).values():
        data = getattr(coordinator, "data", None)
        if data and camera_id in data.cameras:
            return coordinator, camera_id

    raise ServiceValidationError(
        f"Could not find a {DOMAIN} config entry that owns camera_id={camera_id} from {entity_id}"
    )


def _expand_targets(coordinator: BlueIrisDataUpdateCoordinator, camera_id: str) -> list[str]:
    """Expand group cameras into individual targets (preserves existing behavior)."""
    data = coordinator.data
    if not data:
        return [camera_id]

    cam = data.cameras.get(camera_id)
    if cam and cam.group_cameras:
        return [str(c) for c in cam.group_cameras if c] or [camera_id]

    return [camera_id]


def _normalize_system_name(value: object) -> str | None:
    """Normalize a possible system name value from the API into a non-empty string."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


async def _ensure_server_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: BlueIrisDataUpdateCoordinator,
) -> None:
    """Ensure a "server" device exists for linking entities via_device."""
    device_reg = dr.async_get(hass)

    version = coordinator.data.server_version if coordinator.data else None

    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_server")},
        name=server_device_name(coordinator),
        manufacturer="Blue Iris",
        model="Server",
        sw_version=version,
    )


async def _async_handle_reload(hass: HomeAssistant, call: ServiceCall) -> None:
    """Reload this integration's config entries.

    If entry_id is provided, reload only that entry; otherwise reload all Blue Iris entries.
    """
    entry_id = call.data.get(SERVICE_RELOAD_ENTRY_ID)
    entries = hass.config_entries.async_entries(DOMAIN)

    if entry_id is not None:
        target = [e for e in entries if e.entry_id == entry_id]
    else:
        target = list(entries)

    for ent in target:
        await hass.config_entries.async_reload(ent.entry_id)


async def _async_handle_trigger_camera(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the trigger_camera service for one or more camera entities."""
    entity_ids = list(call.data["entity_id"])

    async def _action(c: BlueIrisDataUpdateCoordinator, cam_id: str):
        return await c.api.trigger_camera(cam_id)

    await _async_run_camera_action(hass, entity_ids, _action)


async def _async_handle_move_to_preset(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the move_to_preset service for one or more camera entities."""
    entity_ids = list(call.data["entity_id"])
    preset = int(call.data["preset"])

    async def _action(c: BlueIrisDataUpdateCoordinator, cam_id: str):
        return await c.api.move_to_preset(cam_id, preset)

    await _async_run_camera_action(hass, entity_ids, _action)




def _latest_motion_event_payload(
    coordinator: BlueIrisDataUpdateCoordinator,
    camera_id: str,
    *,
    filename: str | None = None,
) -> dict[str, Any]:
    """Build a response payload for the latest motion event snapshot service."""
    data = coordinator.data
    event = coordinator.get_last_motion_event(camera_id)
    camera = data.cameras.get(camera_id) if data else None

    return {
        "camera_id": camera_id,
        "camera_name": camera.name if camera is not None else camera_id,
        "event": event.state if event is not None else None,
        "event_type": event.event_type if event is not None else None,
        "event_time": event.last_detection if event is not None else None,
        "snapshot_url": event.snapshot_url if event is not None else coordinator._still_image_url(camera_id),
        "memo": event.memo if event is not None else None,
        "labels": event.labels if event is not None else None,
        "matched_labels": event.matched_labels if event is not None else None,
        "stored_path": filename or (event.stored_path if event is not None else None),
        "generated_at": dt_util.utcnow().isoformat(),
    }


async def _async_handle_latest_motion_event_snapshot(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Return latest motion event metadata and optionally save a current still image."""
    entity_id = call.data.get("entity_id")
    if entity_id is None:
        entity_id = call.target.get("entity_id")

    if isinstance(entity_id, list):
        if len(entity_id) != 1:
            raise ServiceValidationError("Exactly one entity_id is required")
        entity_id = entity_id[0]

    if not isinstance(entity_id, str):
        raise ServiceValidationError(
            "entity_id must be a single camera entity_id string"
        )

    coordinator, camera_id = _coordinator_and_camera_id_from_entity_id(
        hass, entity_id
    )

    base_snapshot_dir = Path("/config/www/blueiris")

    filename = call.data.get(SERVICE_SNAPSHOT_FILENAME)
    if filename:
        filename = Path(filename).name
    else:
        filename = f"{camera_id.lower()}_latest_motion.jpg"

    image = await coordinator.async_fetch_camera_snapshot(camera_id)
    if image is None:
        raise ServiceValidationError(
            f"Unable to fetch snapshot for {entity_id}"
        )

    path = base_snapshot_dir / filename

    # Ensure directory exists
    await hass.async_add_executor_job(
        partial(path.parent.mkdir, parents=True, exist_ok=True)
    )

    # Write snapshot
    await hass.async_add_executor_job(path.write_bytes, image)

    _LOGGER.debug("Saved Blue Iris snapshot for %s to %s", entity_id, path)
    coordinator.set_last_motion_event_stored_path(camera_id, str(path))

    local_url = f"/local/blueiris/{filename}"

    payload = _latest_motion_event_payload(coordinator, camera_id, filename=filename)
    payload["saved_filename"] = filename
    payload["saved_path"] = str(path)
    payload["local_snapshot_url"] = local_url

    return payload

async def async_setup(_hass: HomeAssistant, _config: dict) -> bool:
    """Set up via YAML (not used)."""
    return True


async def _async_run_camera_action(
    hass: HomeAssistant,
    entity_ids: list[str],
    action_factory,
) -> None:
    """Run a coroutine per expanded camera target and refresh coordinator.

    Pure refactor helper to reduce duplication between service handlers.
    """
    for entity_id in entity_ids:
        target_coordinator, camera_id = _coordinator_and_camera_id_from_entity_id(hass, entity_id)
        targets = _expand_targets(target_coordinator, camera_id)

        results = await asyncio.gather(
            *(action_factory(target_coordinator, cam_id) for cam_id in targets),
            return_exceptions=True,
        )

        for cam_id, res in zip(targets, results, strict=False):
            if isinstance(res, Exception):
                _LOGGER.debug("Service action failed for %s", cam_id, exc_info=res)

        await target_coordinator.async_schedule_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Blue Iris from a config entry."""
    await _handle_log_level(hass, entry)

    coordinator = BlueIrisDataUpdateCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    # Ensure coordinator has data before platforms/entities are created.
    await coordinator.async_config_entry_first_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_TRIGGER_CAMERA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TRIGGER_CAMERA,
            partial(_async_handle_trigger_camera, hass),
            schema=TRIGGER_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_MOVE_TO_PRESET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_MOVE_TO_PRESET,
            partial(_async_handle_move_to_preset, hass),
            schema=PRESET_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RELOAD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RELOAD,
            partial(_async_handle_reload, hass),
            schema=RELOAD_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_LATEST_MOTION_EVENT_SNAPSHOT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LATEST_MOTION_EVENT_SNAPSHOT,
            partial(_async_handle_latest_motion_event_snapshot, hass),
            schema=LATEST_MOTION_EVENT_SNAPSHOT_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    # Optionally rename integration to BI system name (only if still default).
    system_name = _normalize_system_name(coordinator.data.system_name if coordinator.data else None)
    if system_name and entry.title == DEFAULT_NAME:
        _LOGGER.debug("Renaming entry from %r to %r", entry.title, system_name)
        hass.config_entries.async_update_entry(entry, title=system_name)

    # Ensure the system device exists even if no switch entities are created.
    await _ensure_server_device(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and clean up coordinator resources."""
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    coordinator: BlueIrisDataUpdateCoordinator | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if coordinator is not None:
        await coordinator.async_shutdown()

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)

    return unload_ok


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after options are changed through the UI."""
    """Handle options updates."""
    await _handle_log_level(hass, entry)
    await hass.config_entries.async_reload(entry.entry_id)


async def _handle_log_level(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply the configured log level to the integration logger hierarchy."""
    log_level = entry.options.get(CONF_LOG_LEVEL, LOG_LEVEL_DEFAULT)
    if log_level == LOG_LEVEL_DEFAULT:
        return

    try:
        await hass.services.async_call(
            DOMAIN_LOGGER,
            SERVICE_SET_LEVEL,
            {f"custom_components.{DOMAIN}": str(log_level).lower()},
        )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Failed to set log level. Ensure logger integration is configured.")
