"""Switch platform for Blue Iris (profiles and schedules)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Awaitable, Callable, Generic, TypeVar

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BlueIrisData, BlueIrisDataUpdateCoordinator
from .helpers.const import (
    ATTR_ADMIN_PROFILE,
    ATTR_ADMIN_SCHEDULE,
    DEFAULT_VERSION,
    DOMAIN,
    PROFILE_ICON,
    SCHEDULE_ICON,
)
from .helpers.device import server_device_info, server_device_name
from .helpers.entity import is_allowed, unique_id_profile, unique_id_schedule


PROFILE_DESCRIPTION = SwitchEntityDescription(
    key="profile",
    icon=PROFILE_ICON,
)

SCHEDULE_DESCRIPTION = SwitchEntityDescription(
    key="schedule",
    icon=SCHEDULE_ICON,
)

_T = TypeVar("_T")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Create admin-only profile and schedule switches for this entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    data = coordinator.data
    if data is None:
        return

    cfg = coordinator.api.config
    is_admin = bool(data.data.get("admin", False))

    entities: list[SwitchEntity] = []

    if is_admin:
        profiles = data.data.get("profiles", []) or []
        schedules = data.data.get("schedules", []) or []

        for profile_id, profile_name in enumerate(profiles):
            if is_allowed(cfg.allowed_profile, str(profile_id)):
                entities.append(BlueIrisProfileSwitch(coordinator, profile_id, str(profile_name)))

        for schedule_id, schedule_name in enumerate(schedules):
            # Keep existing behavior: schedule allow-list is based on index, entity uses schedule name.
            if is_allowed(cfg.allowed_schedule, str(schedule_id)):
                entities.append(BlueIrisScheduleSwitch(coordinator, str(schedule_name)))

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


class _AdminStatusSwitch(_BaseBISwitch, Generic[_T]):
    """Base class for admin-controlled switches backed by status[...] and a setter call.

    This consolidates shared logic while preserving entity naming/unique_id patterns in subclasses.
    """

    # Subclasses must set these:
    _status_key: str
    _admin_label: str

    def __init__(
        self,
        coordinator: BlueIrisDataUpdateCoordinator,
        *,
        option_value: _T,
        option_display: str,
        unique_id: str,
        set_on: Callable[[], Awaitable[Any]],
    ) -> None:
        """Initialize common state for an admin-controlled profile or schedule switch."""
        super().__init__(coordinator)
        self._option_value = option_value
        self._option_display = option_display
        self._set_on = set_on

        # Preserve existing unique_id behavior exactly
        self._attr_unique_id = unique_id

        # NOTE: We intentionally do NOT set _attr_icon here.
        # The icon comes from entity_description.icon.

    @property
    def is_on(self) -> bool:
        """Generic 'status key equals option value'."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.status.get(self._status_key, 0) == self._option_value

    @property
    def name(self) -> str | None:
        """Return the display name used for this admin-controlled switch."""
        return f"{self._admin_label} {self._option_display}"

    async def _push_status_immediately(self) -> None:
        """Push updated status immediately using the API's current cached status."""
        if self.coordinator.data is None:
            return

        self.coordinator.async_set_updated_data(
            replace(
                self.coordinator.data,
                status=dict(self.coordinator.api.status),
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Apply the represented option and schedule a follow-up refresh."""
        await self.coordinator.async_write_and_refresh(self._set_on())
        await self._push_status_immediately()


class BlueIrisProfileSwitch(_AdminStatusSwitch[int]):
    """A switch representing a Blue Iris profile."""

    entity_description = PROFILE_DESCRIPTION
    _status_key = "profile"
    _admin_label = ATTR_ADMIN_PROFILE

    def __init__(
        self,
        coordinator: BlueIrisDataUpdateCoordinator,
        profile_id: int,
        profile_name: str,
    ) -> None:
        """Initialize a switch representing one Blue Iris profile."""
        self.profile_id = int(profile_id)
        self.profile_name = profile_name

        super().__init__(
            coordinator,
            option_value=self.profile_id,
            option_display=self.profile_name,
            unique_id=unique_id_profile(coordinator.entry.entry_id, self.profile_id),
            set_on=lambda: coordinator.api.set_profile(self.profile_id),
        )

    @property
    def is_on(self) -> bool:
        """Preserve original behavior: treat missing data as profile=0."""
        current_profile = self.coordinator.data.status.get(self._status_key, 0) if self.coordinator.data else 0
        return current_profile == self.profile_id

    async def async_turn_off(self, **kwargs: Any) -> None:
        # Preserve current behavior: toggle between 0 and 1 when turning off a profile.
        to_profile_id = 1
        if self.profile_id == 1:
            to_profile_id = 0

        # Recommended change: use async_write_and_refresh for off-write as well.
        await self.coordinator.async_write_and_refresh(self.coordinator.api.set_profile(to_profile_id))

        # Preserve existing "immediate push" behavior.
        await self._push_status_immediately()


class BlueIrisScheduleSwitch(_AdminStatusSwitch[str]):
    """A switch representing a Blue Iris schedule."""

    entity_description = SCHEDULE_DESCRIPTION
    _status_key = "schedule"
    _admin_label = ATTR_ADMIN_SCHEDULE

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator, schedule_name: str) -> None:
        """Initialize a switch representing one Blue Iris schedule."""
        self.schedule_name = schedule_name

        super().__init__(
            coordinator,
            option_value=self.schedule_name,
            option_display=self.schedule_name,
            unique_id=unique_id_schedule(coordinator.entry.entry_id, self.schedule_name),
            set_on=lambda: coordinator.api.set_schedule(self.schedule_name),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        # No-op in current behavior
        return