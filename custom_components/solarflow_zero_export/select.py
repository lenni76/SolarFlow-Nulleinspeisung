"""Explicit steering strategy selection; corrected control remains the default."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONTROL_STRATEGIES, OPT_CONTROL_STRATEGY
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarFlowZeroExportConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SolarFlowStrategySelect(entry.runtime_data)])


class SolarFlowStrategySelect(SolarFlowZeroExportEntity, SelectEntity):
    _attr_translation_key = OPT_CONTROL_STRATEGY
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(CONTROL_STRATEGIES)

    def __init__(self, controller) -> None:
        super().__init__(controller, OPT_CONTROL_STRATEGY)

    @property
    def current_option(self) -> str | None:
        value = self.controller.option[OPT_CONTROL_STRATEGY]
        return value if value in CONTROL_STRATEGIES else None

    async def async_select_option(self, option: str) -> None:
        await self.controller.async_set_option(OPT_CONTROL_STRATEGY, option)
