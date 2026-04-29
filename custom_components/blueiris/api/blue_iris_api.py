from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from ..models.camera_data import CameraData

from ..helpers.const import (
    BI_ATTR_AUDIO,
    BI_ATTR_GROUP,
    BI_ATTR_ID,
    BI_ATTR_IS_ONLINE,
    BI_ATTR_NAME,
    BI_ATTR_TYPE,
    BI_CAMERA_TYPE_GENERIC,
    BI_CAMERA_TYPE_GROUP,
    BI_CAMERA_TYPE_SYSTEM,
    BI_CAMERA_TYPE_GROUP_LABEL,
    SYSTEM_CAMERA_ID,
    BI_ATTR_SYSTEM_NAME,
    BI_ATTR_IS_ENABLED,
    BI_ATTR_IS_ACTIVE,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = ClientTimeout(total=10)
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


@dataclass(slots=True)
class BlueIrisConfig:
    """Runtime configuration used by the Blue Iris API client and entity setup."""
    host: str
    port: int
    ssl: bool
    verify_ssl: bool
    username: str
    password: str

    # options used by entity setup (kept here for convenience)
    stream_type: str = "H264"
    support_stream: bool = False
    hold_profile_changes: bool = True
    allowed_camera: Optional[list[str]] = None
    allowed_profile: Optional[list[str]] = None
    allowed_schedule: Optional[list[str]] = None
    allowed_motion_sensor: Optional[list[str]] = None
    allowed_audio_sensor: Optional[list[str]] = None
    allowed_connectivity_sensor: Optional[list[str]] = None
    allowed_dio_sensor: Optional[list[str]] = None
    allowed_external_sensor: Optional[list[str]] = None

    # AI label customization (normalized, lowercase)
    ai_person_labels: Optional[list[str]] = None
    ai_vehicle_labels: Optional[list[str]] = None
    ai_animal_labels: Optional[list[str]] = None

    # Debug logging
    mqtt_debug: bool = False


class BlueIrisApi:
    """Handles Blue Iris data retrieval and control."""

    def __init__(self, hass: HomeAssistant, config: BlueIrisConfig) -> None:
        """Initialize the API client, caches, and session-management state."""
        self.hass = hass
        self._config = config

        self.session: Optional[ClientSession] = None
        self.session_id: Optional[str] = None
        self.is_logged_in: bool = False
        self.system_name: str | None = None

        # Prevent concurrent login/session churn (important with short session timeouts)
        self._login_lock = asyncio.Lock()

        # Cached server metadata from login (version, license, etc.)
        self._login_data: dict[str, Any] = {}
        # Cached results from fetchers (used by config flow and as a fallback)
        self._last_status: dict[str, Any] = {}
        self._last_camlist: list[CameraData] = []

        self._last_update = datetime.min
        self._last_status_update = datetime.min
        self._last_camlist_update = datetime.min

    @staticmethod
    def _normalize_cam_id(c: dict[str, Any]) -> str | None:
        """Return a normalized camera id from a raw camlist payload entry."""
        cam_id = c.get(BI_ATTR_ID)  # BI_ATTR_ID == "optionValue"
        if not cam_id:
            return None
        cam_id = str(cam_id).strip()
        return cam_id or None

    @staticmethod
    def _group_list(c: dict[str, Any]) -> list[Any] | None:
        """Return the raw group member list when the camlist entry represents a group."""
        group_list = c.get(BI_ATTR_GROUP)
        return group_list if isinstance(group_list, list) else None

    @staticmethod
    def _determine_cam_type(c: dict[str, Any], *, is_group_payload: bool) -> int:
        """Determine the effective Blue Iris camera type for a camlist entry."""
        if is_group_payload:
            return BI_CAMERA_TYPE_GROUP
        raw_type = c.get(BI_ATTR_TYPE)
        return raw_type if isinstance(raw_type, int) else BI_CAMERA_TYPE_GENERIC

    @staticmethod
    def _is_system_camera(cam_id: str) -> bool:
        """Return True when the identifier represents one of the Blue Iris system cameras."""
        return cam_id in SYSTEM_CAMERA_ID

    @staticmethod
    def _clean_display_name(c: dict[str, Any], cam_id: str) -> str:
        """Normalize the display name used for entities and devices."""
        raw_name = c.get(BI_ATTR_NAME) or cam_id
        return str(raw_name).lstrip("+").strip()

    @staticmethod
    def _camera_name(cleaned: str, cam_type: int) -> str:
        """Build the final user-facing camera name from normalized data."""
        if cam_type == BI_CAMERA_TYPE_GROUP:
            return f"{BI_CAMERA_TYPE_GROUP_LABEL}: {cleaned}"
        return cleaned

    @staticmethod
    def _is_online(c: dict[str, Any], cam_type: int) -> bool:
        """Derive online state using the payload field appropriate for the camera type."""
        # Groups/system/special views often don't have isOnline
        if cam_type in (BI_CAMERA_TYPE_GROUP, BI_CAMERA_TYPE_SYSTEM):
            return bool(c.get(BI_ATTR_IS_ENABLED, False))
        return bool(c.get(BI_ATTR_IS_ONLINE, False))

    @staticmethod
    def _group_members(cam_type: int, group_list: list[Any] | None) -> list[str] | None:
        """Return normalized member camera ids for group cameras."""
        if cam_type != BI_CAMERA_TYPE_GROUP:
            return None
        members: list[str] = []
        if group_list:
            for item in group_list:
                if item:
                    members.append(str(item).strip())
        return members
        
    @staticmethod
    def _version_to_bi_update_value(version: str) -> int:
        """Convert dotted version like '5.3.9.6' to BI's decimal update value.

        BI expects the version as a HEX-formatted number converted to decimal.
        Example:
            5.3.9.6 -> 0x05030906 -> 84084998
        """
        parts = [int(p.strip()) for p in version.split(".")]
        if len(parts) != 4:
            raise ValueError(f"Invalid Blue Iris version for update: {version!r}")

        major, minor, patch, build = parts
        hex_string = f"{major:02x}{minor:02x}{patch:02x}{build:02x}"
        return int(hex_string, 16)

    def _camera_data_from_camlist(self, c: dict[str, Any]) -> CameraData | None:
        """Convert a single camlist entry into CameraData."""

        cam_id = self._normalize_cam_id(c)
        if not cam_id:
            return None

        group_list = self._group_list(c)
        is_group_payload = group_list is not None

        # Determine camera type. Keep the same precedence:
        # - Group payload implies Group type
        # - System camera ids override group/type detection
        cam_type = self._determine_cam_type(c, is_group_payload=is_group_payload)

        is_system = self._is_system_camera(cam_id)
        if is_system:
            cam_type = BI_CAMERA_TYPE_SYSTEM

        cleaned = self._clean_display_name(c, cam_id)
        cam_name = self._camera_name(cleaned, cam_type)

        is_online = self._is_online(c, cam_type)

        has_audio = bool(c.get(BI_ATTR_AUDIO, False))
        is_active = bool(c.get(BI_ATTR_IS_ACTIVE, False))
        is_enabled = bool(c.get(BI_ATTR_IS_ENABLED, False))

        group_cameras = self._group_members(cam_type, group_list)

        return CameraData(
            data=dict(c),  # snapshot copy
            id=cam_id,
            name=cam_name,
            has_audio=has_audio,
            is_online=is_online,
            is_active=is_active,
            is_enabled=is_enabled,
            group_cameras=group_cameras,
            is_system=is_system,
            type=cam_type,
        )

    def update_config(self, config: BlueIrisConfig) -> None:
        """Replace the active API configuration with a new config snapshot."""
        self._config = config

    @property
    def config(self) -> BlueIrisConfig:
        """Public integration config (do not mutate)."""
        return self._config

    @property
    def base_url(self) -> str:
        scheme = "https" if self._config.ssl else "http"
        return f"{scheme}://{self._config.host}:{self._config.port}"

    @property
    def url(self) -> str:
        """Return the JSON API endpoint URL for the configured Blue Iris server."""
        return f"{self.base_url}/json"


    # --- Cached compatibility properties (read-only) ---
    @property
    def data(self) -> dict[str, Any]:
        """Return cached login metadata from the most recent successful login."""
        """Last login metadata payload (compatibility)."""
        return self._login_data

    @property
    def status(self) -> dict[str, Any]:
        """Return cached server status from the most recent status request."""
        """Last fetched status payload (compatibility)."""
        return self._last_status

    @property
    def camera_list(self) -> list[CameraData]:
        """Return the cached normalized camera list from the most recent camlist request."""
        """Last fetched camera list (compatibility)."""
        return self._last_camlist


    async def ensure_session(self) -> None:
        """Create the shared aiohttp session on first use."""
        if self.session is None or self.session.closed:
            # Use HA managed session so proxies/SSL settings match HA conventions.
            self.session = async_create_clientsession(self.hass, timeout=DEFAULT_TIMEOUT)

    def _ssl_param(self):
        # aiohttp "ssl" parameter:
        # - None => default verification behavior
        # - False => disable verification
        if self._config.ssl and not self._config.verify_ssl:
            return False
        return None

    def _is_auth_failure(self, reason: str) -> bool:
        r = (reason or "").lower()
        return (
            "invalid session" in r
            or "access denied" in r
            or "authorization" in r
            or "unauthorized" in r
            or "login" in r
            or "auth" in r
        )

    async def _post_with_session(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Post including the current session id (pure refactor helper)."""
        payload = dict(payload)
        payload["session"] = self.session_id
        return await self.async_post(payload)

    async def async_post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        await self.ensure_session()

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.post(
                    self.url,
                    json = payload,
                    ssl=self._ssl_param(),
                ) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as ex:
                _LOGGER.warning("Blue Iris request failed (attempt %s/%s): %s", attempt, MAX_RETRIES, ex)
                await asyncio.sleep(RETRY_DELAY)
            except Exception:
                _LOGGER.exception("Unexpected error talking to Blue Iris (attempt %s/%s)", attempt, MAX_RETRIES)
                await asyncio.sleep(RETRY_DELAY)

        return None

    async def login(self) -> None:
        """Log into Blue Iris and set session_id."""
        async with self._login_lock:
            # Another coroutine may have logged in while we waited.
            if self.is_logged_in and self.session_id:
                return

            resp = await self.async_post({"cmd": "login"})
            if not resp or resp.get("result") != "fail" or "session" not in resp:
                raise RuntimeError("Blue Iris login failed")

            session = resp["session"]
            user = self._config.username or ""
            pwd = self._config.password or ""

            token = hashlib.md5(f"{user}:{session}:{pwd}".encode("utf-8")).hexdigest()

            resp2 = await self.async_post({"cmd": "login", "session": session, "response": token})
            if not resp2 or resp2.get("result") == "fail":
                raise RuntimeError(f"Blue Iris login verification failed: {resp2}")

            self.session_id = resp2.get("session", session)
            self.is_logged_in = True

            data = resp2.get("data")
            if isinstance(data, dict):
                self._login_data = data

            system_name = self._login_data.get(BI_ATTR_SYSTEM_NAME)
            if isinstance(system_name, str):
                system_name = system_name.strip()
            else:
                system_name = None
            self.system_name = system_name

    async def verified_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a command, retrying once after re-authentication if the session is stale."""
        """Post and ensure we are logged in; retry once after re-login on auth failure."""
        payload = dict(payload)

        if not self.is_logged_in or not self.session_id:
            _LOGGER.debug("Not logged in; logging in")
            await self.login()

        result = await self._post_with_session(payload)
        if not result:
            _LOGGER.debug("Blue Iris cmd=%s no response", payload.get("cmd"))
            raise RuntimeError("Blue Iris request failed (no response)")

        cmd = payload.get("cmd")
        res = result.get("result")
        _LOGGER.debug(
            "Blue Iris cmd=%s result=%s session_id=%r",
            cmd,
            res,
            self.session_id,
        )

        if res != "fail":
            return result

        data = result.get("data") or {}
        raw_reason = data.get("reason") or data.get("error") or data.get("message") or ""
        reason_l = str(raw_reason).lower()

        _LOGGER.warning(
            "Blue Iris cmd=%s returned fail. reason=%r session_id=%r",
            cmd,
            raw_reason,
            self.session_id,
        )

        auth_fail = self._is_auth_failure(reason_l)
        if not auth_fail:
            raise RuntimeError(f"Blue Iris request failed for cmd={cmd} reason={raw_reason!r}")

        _LOGGER.debug("Auth failure (%s). Re-authenticating and retrying once.", raw_reason)

        self.is_logged_in = False
        self.session_id = None
        await self.login()

        result = await self._post_with_session(payload)
        if not result:
            raise RuntimeError("Blue Iris request failed after reauth (no response)")

        if result.get("result") == "fail":
            data = result.get("data") or {}
            raw_reason2 = data.get("reason") or data.get("error") or data.get("message")
            raise RuntimeError(f"Blue Iris request failed after reauth for cmd={cmd} reason={raw_reason2!r}")

        return result

    async def fetch_status(self) -> dict[str, Any]:
        """Fetch raw server status from Blue Iris and update the local status cache."""
        """Fetch current status data from Blue Iris (stateless return).

        Also updates the internal compatibility cache.
        """
        resp = await self.verified_post({"cmd": "status"})
        data = resp.get("data", {})
        status = data if isinstance(data, dict) else {}
        self._last_status = status
        self._last_status_update = datetime.now()
        return status

    async def fetch_camlist(self) -> list[CameraData]:
        """Fetch the raw camera list, normalize it, and update the local camera cache."""
        """Fetch camera list from Blue Iris (stateless return).

        Also updates the internal compatibility cache.
        """
        resp = await self.verified_post({"cmd": "camlist"})
        cams = resp.get("data", [])
        if not isinstance(cams, list):
            self._last_camlist = []
            self._last_camlist_update = datetime.now()
            return []

        camera_list: list[CameraData] = []
        for c in cams:
            if not isinstance(c, dict):
                continue
            cam = self._camera_data_from_camlist(c)
            if cam:
                camera_list.append(cam)

        self._last_camlist = camera_list
        self._last_camlist_update = datetime.now()
        return camera_list

    async def async_update_camlist(self) -> None:
        """Refresh only the cached camera list."""
        """Refresh the camera list from Blue Iris."""
        await self.fetch_camlist()

    async def async_update_status(self) -> None:
        """Refresh only the cached server status."""
        """Refresh the status payload from Blue Iris."""
        await self.fetch_status()

    async def async_update(self) -> None:
        """Refresh both status and camera list in the preserved update order."""
        """Refresh all API state (status + camlist)."""
        await self.async_update_status()
        await self.async_update_camlist()
        self._last_update = datetime.now()

    # ---- Actions ----
    async def set_profile(self, profile_id: int, hold: bool | None = None) -> None:
        payload = {"cmd": "status", "profile": int(profile_id)}
        resp = await self.verified_post(payload)
        data = resp.get("data") or {}

        if hold is None:
            hold = bool(getattr(self._config, "hold_profile_changes", True))
        if hold and data.get("lock") != 1:
            resp2 = await self.verified_post(payload)
            data = (resp2.get("data") or {}) if resp2 else data
        self._last_status = data

    async def set_schedule(self, schedule_name: str) -> None:
        """Set the active Blue Iris schedule."""
        resp = await self.verified_post({"cmd": "status", "schedule": str(schedule_name)})
        data = resp.get("data") or {}
        self._last_status = data

    async def trigger_camera(self, camera_id: str) -> None:
        await self.verified_post({"cmd": "trigger", "camera": camera_id})

    async def move_to_preset(self, camera_id: str, preset: int) -> None:
        await self.verified_post({"cmd": "ptz", "camera": camera_id, "button": 100 + int(preset)})
        
    async def install_update(self, version: str) -> None:
        """Trigger Blue Iris to install the specified update version."""
        version_value = self._version_to_bi_update_value(version)
        await self.verified_post(
            {
                "cmd": "status",
                "update": f"{version_value}, 0",
            }
        )

    async def async_close(self) -> None:
        """Close the managed HTTP session and clear login state."""
        """Do NOT close HA's shared aiohttp session."""
        # Home Assistant owns the session lifecycle.
        return
