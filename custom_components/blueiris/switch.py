"""Create server-level Blue Iris config switches for this entry."""

from __future__ import annotations

from typing import Any
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator
from .helpers.const import (   
    DEFAULT_VERSION,
    DOMAIN,    
    CONF_HOLD_PROFILE_CHANGES,
    DEFAULT_HOLD_PROFILE_CHANGES,
    HOLD_PROFILE_CHANGES_ICON,
    DATA_SKIP_OPTIONS_RELOAD
)
from .helpers.device import server_device_info, server_device_name
from .helpers.entity import unique_id_hold_profile_changes



HOLD_PROFILE_CHANGES_DESCRIPTION = SwitchEntityDescription(
    key="hold_profile_changes",
    icon=HOLD_PROFILE_CHANGES_ICON,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Create server-level Blue Iris config switches for this entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    data = coordinator.data
    if data is None:
        return

    is_admin = bool(data.data.get("admin", False))

    entities: list[SwitchEntity] = []

    if is_admin:
        entities.append(BlueIrisHoldProfileChangesSwitch(coordinator))       

    async_add_entities(entities)


class _BaseBISwitch(CoordinatorEntity[BlueIrisData], SwitchEntity):
    """Shared CoordinatorEntity base for Blue Iris switches."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator) -> None:
        """Initialize the shared Blue Iris switch base class."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the switch to the Blue Iris server device in Home Assistant."""
        data = self.coordinator.data
        version = data.server_version if (data and data.server_version) else DEFAULT_VERSION

        # Preserve existing device naming behavior for this platform ("... Server")
        return server_device_info(
            self.coordinator.entry.entry_id,
            name=server_device_name(self.coordinator),
            sw_version=version,  # Shows as Firmware in HA UI
        )


class BlueIrisHoldProfileChangesSwitch(_BaseBISwitch):
    """Server-level config switch controlling whether profile changes are held."""

    entity_description = HOLD_PROFILE_CHANGES_DESCRIPTION
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator) -> None:
        """Initialize the hold-profile-changes config switch."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id_hold_profile_changes(coordinator.entry.entry_id)

    @property
    def name(self) -> str | None:
        """Return the display name used for this server config switch."""
        return "Hold Profile Changes"

    @property
    def is_on(self) -> bool:
        """Return the saved integration setting, not the live BI lock state."""
        return bool(self.coordinator.api.config.hold_profile_changes)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the saved 'hold profile changes' integration option."""
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the saved 'hold profile changes' integration option."""
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        """Persist the hidden option without calling Blue Iris or reloading the entry."""
        current = bool(
            getattr(
                self.coordinator.api.config,
                "hold_profile_changes",
                DEFAULT_HOLD_PROFILE_CHANGES,
            )
        )
        if current == enabled:
            return

        new_options = dict(self.coordinator.entry.options)
        new_options[CONF_HOLD_PROFILE_CHANGES] = enabled

        skip_reload_once = self.hass.data.setdefault(DATA_SKIP_OPTIONS_RELOAD, set())
        skip_reload_once.add(self.coordinator.entry.entry_id)

        self.hass.config_entries.async_update_entry(
            self.coordinator.entry,
            options=new_options,
        )

        # Update the in-memory runtime config immediately so future set_profile()
        # calls use the new value even though we skipped the reload.
        self.coordinator.update_entry(self.coordinator.entry)

        self.async_write_ha_state()