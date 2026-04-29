"""Select platform for Blue Iris profile and schedule selection."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
from .helpers.entity import (
    is_allowed,
    unique_id_profile,
    unique_id_schedule,
)


PROFILE_DESCRIPTION = SelectEntityDescription(
    key="profile",
    icon=PROFILE_ICON,
)

SCHEDULE_DESCRIPTION = SelectEntityDescription(
    key="schedule",
    icon=SCHEDULE_ICON,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Create admin-only profile and schedule select entities for this entry."""
    coordinator: BlueIrisDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    data = coordinator.data
    if data is None:
        return

    cfg = coordinator.api.config
    is_admin = bool(data.data.get("admin", False))

    entities: list[SelectEntity] = []

    if is_admin:
        profiles = data.data.get("profiles", []) or []
        allowed_profiles = [
            (profile_id, str(profile_name))
            for profile_id, profile_name in enumerate(profiles)
            if is_allowed(cfg.allowed_profile, str(profile_id))
        ]

        if allowed_profiles:
            entities.append(BlueIrisProfileSelect(coordinator, allowed_profiles))

        schedules = data.data.get("schedules", []) or []
        allowed_schedules = [
            (schedule_id, str(schedule_name))
            for schedule_id, schedule_name in enumerate(schedules)
            if is_allowed(cfg.allowed_schedule, str(schedule_id))
        ]

        if allowed_schedules:
            entities.append(BlueIrisScheduleSelect(coordinator, allowed_schedules))

    async_add_entities(entities)


def _build_unique_option_labels(indexed_names: list[tuple[int, str]]) -> dict[int, str]:
    """Build stable display labels, prefixing ids only when names are duplicated."""
    clean_names = {
        idx: (str(name).strip() or str(idx))
        for idx, name in indexed_names
    }
    counts = Counter(clean_names.values())

    labels: dict[int, str] = {}
    for idx, name in clean_names.items():
        labels[idx] = f"{idx} - {name}" if counts[name] > 1 else name

    return labels


class _BaseBISelect(CoordinatorEntity[BlueIrisData], SelectEntity):
    """Shared CoordinatorEntity base for Blue Iris select entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BlueIrisDataUpdateCoordinator) -> None:
        """Initialize the shared Blue Iris select base class."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the select to the Blue Iris server device in Home Assistant."""
        data = self.coordinator.data
        version = data.server_version if (data and data.server_version) else DEFAULT_VERSION

        return server_device_info(
            self.coordinator.entry.entry_id,
            name=server_device_name(self.coordinator),
            sw_version=version,
        )

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


class BlueIrisProfileSelect(_BaseBISelect):
    """Select entity for the active Blue Iris profile."""

    entity_description = PROFILE_DESCRIPTION

    def __init__(
        self,
        coordinator: BlueIrisDataUpdateCoordinator,
        profiles: list[tuple[int, str]],
    ) -> None:
        """Initialize the Blue Iris profile select."""
        super().__init__(coordinator)

        labels_by_id = _build_unique_option_labels(profiles)

        self._profile_id_to_option: dict[int, str] = {}
        self._option_to_profile_id: dict[str, int] = {}

        for profile_id, _profile_name in profiles:
            option = labels_by_id[profile_id]
            self._profile_id_to_option[profile_id] = option
            self._option_to_profile_id[option] = profile_id

        self._attr_unique_id = unique_id_profile(coordinator.entry.entry_id)
        self._attr_options = list(self._option_to_profile_id)

    @property
    def name(self) -> str | None:
        """Return the select display name."""
        return ATTR_ADMIN_PROFILE

    @property
    def current_option(self) -> str | None:
        """Return the currently active profile option."""
        data = self.coordinator.data
        if data is None:
            return None

        try:
            current_profile = int(data.status.get("profile", 0))
        except (TypeError, ValueError):
            return None

        return self._profile_id_to_option.get(current_profile)

    async def async_select_option(self, option: str) -> None:
        """Select a Blue Iris profile."""
        profile_id = self._option_to_profile_id.get(option)
        if profile_id is None:
            raise HomeAssistantError(f"Unknown Blue Iris profile option: {option}")

        await self.coordinator.async_write_and_refresh(
            self.coordinator.api.set_profile(profile_id)
        )
        await self._push_status_immediately()


class BlueIrisScheduleSelect(_BaseBISelect):
    """Select entity for the active Blue Iris schedule."""

    entity_description = SCHEDULE_DESCRIPTION

    def __init__(
        self,
        coordinator: BlueIrisDataUpdateCoordinator,
        schedules: list[tuple[int, str]],
    ) -> None:
        """Initialize the Blue Iris schedule select."""
        super().__init__(coordinator)

        labels_by_id = _build_unique_option_labels(schedules)

        self._schedule_name_to_option: dict[str, str] = {}
        self._option_to_schedule_name: dict[str, str] = {}

        for schedule_id, schedule_name in schedules:
            option = labels_by_id[schedule_id]
            self._schedule_name_to_option[schedule_name] = option
            self._option_to_schedule_name[option] = schedule_name

        self._attr_unique_id = unique_id_schedule(coordinator.entry.entry_id)
        self._attr_options = list(self._option_to_schedule_name)

    @property
    def name(self) -> str | None:
        """Return the select display name."""
        return ATTR_ADMIN_SCHEDULE

    @property
    def current_option(self) -> str | None:
        """Return the currently active schedule option."""
        data = self.coordinator.data
        if data is None:
            return None

        current_schedule = data.status.get("schedule")
        if current_schedule is None:
            return None

        return self._schedule_name_to_option.get(str(current_schedule))

    async def async_select_option(self, option: str) -> None:
        """Select a Blue Iris schedule."""
        schedule_name = self._option_to_schedule_name.get(option)
        if schedule_name is None:
            raise HomeAssistantError(f"Unknown Blue Iris schedule option: {option}")

        await self.coordinator.async_write_and_refresh(
            self.coordinator.api.set_schedule(schedule_name)
        )
        await self._push_status_immediately()