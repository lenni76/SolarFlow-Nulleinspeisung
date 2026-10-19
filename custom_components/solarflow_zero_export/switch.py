"""Switch entities for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import OPT_ENABLED
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarFlowZeroExportConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SolarFlowEnabledSwitch(entry.runtime_data, OPT_ENABLED)])


class SolarFlowEnabledSwitch(SolarFlowZeroExportEntity, SwitchEntity):
    _attr_translation_key = "enabled"

    @property
    def is_on(self) -> bool:
        return bool(self.controller.option[OPT_ENABLED])

    async def async_turn_on(self, **kwargs) -> None:
        await self.controller.async_set_option(OPT_ENABLED, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.controller.async_set_option(OPT_ENABLED, False)
