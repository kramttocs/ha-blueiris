"""
Support for Blue Iris.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/camera.blueiris/
"""
import sys
import logging
from abc import ABC
from typing import Optional

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import device_registry as dr

from .home_assistant import _get_ha
from .const import *
from homeassistant.components.generic.camera import GenericCamera

DEPENDENCIES = [DOMAIN]

_LOGGER = logging.getLogger(__name__)

CURRENT_DOMAIN = DOMAIN_CAMERA


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up the EdgeOS Binary Sensor."""
    _LOGGER.debug(f"Starting async_setup_entry {CURRENT_DOMAIN}")

    try:
        entry_data = config_entry.data
        host = entry_data.get(CONF_HOST)
        entities = []

        ha = _get_ha(hass, host)

        if ha is not None:
            entities_data = ha.get_entities(CURRENT_DOMAIN)
            for entity_name in entities_data:
                entity = entities_data[entity_name]

                camera = BlueIrisCamera(hass, ha, entity)

                _LOGGER.debug(f"Setup {CURRENT_DOMAIN}: {camera.name} | {camera.unique_id}")

                entities.append(camera)

                ha.set_domain_entities_state(CURRENT_DOMAIN, True)

        async_add_devices(entities, True)
    except Exception as ex:
        exc_type, exc_obj, tb = sys.exc_info()
        line_number = tb.tb_lineno

        _LOGGER.error(f"Failed to load {CURRENT_DOMAIN}, error: {ex}, line: {line_number}")


async def async_unload_entry(hass, config_entry):
    _LOGGER.info(f"async_unload_entry {CURRENT_DOMAIN}: {config_entry}")

    entry_data = config_entry.data
    name = entry_data.get(CONF_NAME)

    ha = _get_ha(hass, name)

    if ha is not None:
        ha.set_domain_entities_state(CURRENT_DOMAIN, False)

    return True


class BlueIrisCamera(GenericCamera, ABC):
    def __init__(self, hass, ha, entity):
        """Initialize the MQTT binary sensor."""
        self._hass = hass
        self._ha = ha
        self._entity = entity
        self._remove_dispatcher = None

        device_info = self._entity.get(ENTITY_CAMERA_DETAILS)

        super().__init__(hass, device_info)

    @property
    def unique_id(self) -> Optional[str]:
        """Return the name of the node."""
        return self._entity.get(ENTITY_UNIQUE_ID)

    @property
    def device_info(self):
        return self._entity.get(ENTITY_DEVICE_INFO)

    @property
    def state_attributes(self):
        """Return the camera state attributes."""
        attrs = super().state_attributes
        attributes = self._entity.get(ENTITY_ATTRIBUTES, {})

        for key in attributes:
            attrs[key] = attributes[key]

        return attrs

    async def async_added_to_hass(self):
        """Register callbacks."""
        self._remove_dispatcher = async_dispatcher_connect(self.hass, SIGNALS[CURRENT_DOMAIN], self.update_data)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_dispatcher is not None:
            self._remove_dispatcher()

    @callback
    def update_data(self):
        self.hass.async_add_job(self.async_update_data)

    async def async_update_data(self):
        if self._ha is None:
            _LOGGER.debug(f"Cannot update {CURRENT_DOMAIN} - HA is None | {self.name}")
        else:
            self._entity = self._ha.get_entity(CURRENT_DOMAIN, self.name)

            if self._entity is None:
                _LOGGER.debug(f"Cannot update {CURRENT_DOMAIN} - entity is None | {self.name}")

                self._entity = {}
                await self.async_remove()

                dev_id = self.device_info.get("id")
                device_reg = await dr.async_get_registry(self._hass)

                device_reg.async_remove_device(dev_id)
            else:
                self.async_schedule_update_ha_state(True)
