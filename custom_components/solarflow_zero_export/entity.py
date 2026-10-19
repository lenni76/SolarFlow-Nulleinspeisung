"""Base entity for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, MANUFACTURER, NAME
from .controller import SolarFlowZeroExportController


class SolarFlowZeroExportEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, controller: SolarFlowZeroExportController, key: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=NAME,
            manufacturer=MANUFACTURER,
            model="PID zero-export controller",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))
