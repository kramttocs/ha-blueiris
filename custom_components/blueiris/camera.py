"""Camera platform for Blue Iris."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

import aiohttp

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator
from .helpers.device import camera_device_info, camera_model
from .helpers.entity import base_name, is_allowed, unique_id_camera
from .helpers.const import (
    DOMAIN,
    DOMAIN_STREAM,
    STREAM_VIDEO,
    DEFAULT_CONTENT_TYPE,
    CAMERA_TYPE_MAPPING,
)

_LOGGER = logging.getLogger(__name__)
ALLOWED_COMPLEX_KEYS: Final[set[str]] = {"group", "rects"}


def _ssl_param(cfg) -> bool | None:
    """Return aiohttp ssl parameter based on integration config."""
    return False if cfg.ssl and not cfg.verify_ssl else None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Create camera entities for the cameras allowed by the current options."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    cfg = coordinator.api.config
    entities: list[BlueIrisCamera] = []
    data = coordinator.data
    if data is not None:
        for cam_id in data.cameras:
            if is_allowed(cfg.allowed_camera, cam_id):
                entities.append(BlueIrisCamera(coordinator, cam_id))

    async_add_entities(entities)


class BlueIrisCamera(CoordinatorEntity[BlueIrisData], Camera):
    """Blue Iris camera entity backed by the coordinator."""

    _attr_content_type = DEFAULT_CONTENT_TYPE
    _attr_has_entity_name = True

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator, camera_id: str) -> None:
        """Initialize the camera entity and its authentication/feature state."""
        Camera.__init__(self)
        CoordinatorEntity.__init__(self, coordinator)
        self.camera_id = camera_id
        self._attr_unique_id = unique_id_camera(coordinator.entry.entry_id, camera_id)

        self._attr_extra_state_attributes = {"camera_id": self.camera_id}
        # Supported features
        self._attr_supported_features = (
            CameraEntityFeature.STREAM
            if coordinator.api.config.support_stream and DOMAIN_STREAM in coordinator.hass.data
            else CameraEntityFeature(0)
        )

        # Basic auth for still images/streams if configured
        u = coordinator.api.config.username
        p = coordinator.api.config.password
        self._auth = aiohttp.BasicAuth(u, password=p) if (u and p) else None

    @property
    def _camera(self):
        """Return the latest camera snapshot from the coordinator, if available."""
        data = self.coordinator.data
        if not data:
            return None
        return data.cameras.get(self.camera_id)

    @property
    def name(self) -> str | None:
        """Defer naming to the device so Home Assistant uses modern entity naming."""
        # Use device name as the primary display name (modern HA naming)
        return None

    @property
    def _camera_name(self) -> str:
        """Return the device display name for this camera."""
        cam = self._camera
        return f"{base_name(self.coordinator)} {cam.name if cam else self.camera_id}"

    @property
    def available(self) -> bool:
        """Return True when the camera is known, online, and coordinator updates succeed."""
        cam = self._camera
        return cam is not None and bool(cam.is_online) and self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        cam = self._camera  # CameraData | None

        model = camera_model(cam.type if cam else None)

        return camera_device_info(
            self.coordinator.entry.entry_id,
            self.camera_id,
            name=self._camera_name,
            model=model,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh extra state attributes from the latest coordinator snapshot."""
        cam = self._camera
        attrs: dict[str, Any] = {"camera_id": self.camera_id}

        if cam is not None:
            for k, v in (cam.data or {}).items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    attrs[k] = v
                elif k in ALLOWED_COMPLEX_KEYS:
                    attrs[k] = v

        self._attr_extra_state_attributes = attrs
        super()._handle_coordinator_update()

    def _still_image_url(self) -> str:
        """Build the Blue Iris still-image URL for this camera."""
        data = self.coordinator.data
        if not data:
            return ""
        base = data.base_url
        session = data.session_id
        if session:
            return f"{base}/image/{self.camera_id}?session={session}"
        return f"{base}/image/{self.camera_id}"

    async def stream_source(self) -> str | None:
        """Build the stream URL that Home Assistant should use for this camera."""
        cfg = self.coordinator.api.config
        stream_config = STREAM_VIDEO.get(getattr(cfg, "stream_type", None), {})
        stream_name = stream_config.get("stream_name") or "mjpg"
        file_name = stream_config.get("file_name") or ""
        data = self.coordinator.data
        if not data:
            return None
        base = data.base_url
        session = data.session_id
        url = f"{base}/{stream_name}/{self.camera_id}/{file_name}"
        if session:
            url = f"{url}?session={session}"
        return url

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return a still image response"""
        url = self._still_image_url()
        if not url:
            return None

        session = async_get_clientsession(self.hass)

        cfg = self.coordinator.api.config
        ssl = _ssl_param(cfg)

        for attempt in (0, 1):  # allow one re-auth retry
            try:
                async with session.get(url, auth=self._auth, ssl=ssl) as resp:
                    if resp.status in (401, 403):
                        if attempt == 1:
                            return None
                        _LOGGER.debug(
                            "Camera image auth error (%s) for %s; re-authenticating once.",
                            resp.status,
                            self.entity_id,
                        )
                        try:
                            await self.coordinator.api.login()
                        except Exception:  # noqa: BLE001
                            _LOGGER.debug("Re-authentication failed for %s", self.entity_id, exc_info=True)
                            return None
                        continue  # retry once

                    if resp.status in (502, 503, 504):
                        _LOGGER.debug(
                            "Transient camera image error (%s) for %s; returning None.",
                            resp.status,
                            self.entity_id,
                        )
                        return None

                    resp.raise_for_status()
                    return await resp.read()

            except asyncio.TimeoutError:
                _LOGGER.debug("Timeout fetching camera image for %s", self.entity_id)
                return None

            except aiohttp.ClientError as err:
                _LOGGER.debug("Transport error fetching camera image for %s: %s", self.entity_id, err)
                return None

            except Exception:  # noqa: BLE001
                _LOGGER.debug("Unexpected error fetching camera image for %s", self.entity_id, exc_info=True)
                return None

        return None
