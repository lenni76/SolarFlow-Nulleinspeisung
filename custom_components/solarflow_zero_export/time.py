"""Time entities for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import OPT_MORNING_END, OPT_MORNING_START
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarFlowZeroExportConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            SolarFlowOptionTime(entry.runtime_data, OPT_MORNING_START),
            SolarFlowOptionTime(entry.runtime_data, OPT_MORNING_END),
        ]
    )


class SolarFlowOptionTime(SolarFlowZeroExportEntity, TimeEntity):
    def __init__(self, controller, key: str) -> None:
        super().__init__(controller, key)
        self.key = key
        self._attr_translation_key = key

    @property
    def native_value(self) -> time:
        return time.fromisoformat(str(self.controller.option[self.key]))

    async def async_set_value(self, value: time) -> None:
        await self.controller.async_set_option(self.key, value.isoformat())
