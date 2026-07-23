"""Button entities for SolarFlow Nulleinspeisung."""
from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry

async def async_setup_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([SolarFlowResetButton(entry.runtime_data)])

class SolarFlowResetButton(SolarFlowZeroExportEntity, ButtonEntity):
    _attr_translation_key = "reset_pid"
    def __init__(self, controller) -> None: super().__init__(controller, "reset_pid")
    async def async_press(self) -> None: await self.controller.async_reset_pid()
