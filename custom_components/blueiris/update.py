"""Update entity platform for Blue Iris."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from homeassistant.components.update import UpdateEntity, UpdateEntityDescription, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator
from .helpers.device import server_device_info
from .helpers.const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class BlueIrisUpdateEntityDescription(UpdateEntityDescription):
    """Describes a Blue Iris update entity."""


UPDATE_DESCRIPTION: Final = BlueIrisUpdateEntityDescription(
    key="server_update",
    name="Software Update",
    icon="mdi:update",
)


def _parse_version(v: str | None) -> tuple[int, ...] | None:
    """Parse dotted version '6.0.3.8' -> (6,0,3,8). Return None if invalid."""
    if not v or not isinstance(v, str):
        return None
    v = v.strip()
    if not v:
        return None
    parts = v.split(".")
    out: list[int] = []
    for p in parts:
        p = p.strip()
        if not p.isdigit():
            return None
        out.append(int(p))
    return tuple(out)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Create the server update entity for the config entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BlueIrisServerUpdateEntity(coordinator, entry)])


class BlueIrisServerUpdateEntity(CoordinatorEntity[BlueIrisData], UpdateEntity):
    """Exposes update availability for the Blue Iris server."""

    entity_description = UPDATE_DESCRIPTION
    _attr_has_entity_name = True
    _attr_supported_features = UpdateEntityFeature.INSTALL

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the Blue Iris server update entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_server_update"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the integration 'Server/System' device."""
        data = self.coordinator.data
        name = ((data.system_name if data else None) or self._entry.title or "BlueIris").strip()

        return server_device_info(
            self._entry.entry_id,
            name=f"{name} Server",
            sw_version=(data.server_version if data else None),
        )

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed Blue Iris version."""
        data = self.coordinator.data
        return data.server_version if data else None

    @property
    def latest_version(self) -> str | None:
        """Return the newest version reported as available by Blue Iris."""
        data = self.coordinator.data
        if not data:
            return None

        # If BI reports a new version, use it
        if data.new_version:
            return data.new_version

        # Otherwise, assume installed is latest
        return data.server_version

    @property
    def update_available(self) -> bool:
        """True if latest_version is newer than installed_version."""
        installed = _parse_version(self.installed_version)
        latest = _parse_version(self.latest_version)

        if installed is None or latest is None:
            return False
        return latest > installed
        
    async def async_install(self, version: str | None, backup: bool, **kwargs) -> None:
        """Install the available Blue Iris update."""
        target_version = version or self.latest_version
        if not target_version:
            raise ValueError("No target Blue Iris version available for install")

        await self.coordinator.api.install_update(target_version)
        await self.coordinator.async_request_refresh()
