"""Number entities for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    OPT_FREE_SOC_THRESHOLD,
    OPT_INTERVAL,
    OPT_KD,
    OPT_KI,
    OPT_KP,
    OPT_LOW_SOC_OUTPUT,
    OPT_LOW_SOC_THRESHOLD,
    OPT_MIN_SOC_SHUTDOWN,
    OPT_RESERVE_HOURS,
    OPT_SAFE_OUTPUT,
    OPT_TARGET_IMPORT,
    OPT_UNAVAILABLE_TIMEOUT,
)
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry


@dataclass(frozen=True, kw_only=True)
class Description:
    key: str
    minimum: float
    maximum: float
    step: float
    unit: str | None = None


DESCRIPTIONS = (
    Description(key=OPT_KP, minimum=0, maximum=5, step=0.01),
    Description(key=OPT_KI, minimum=0, maximum=2, step=0.01),
    Description(key=OPT_KD, minimum=0, maximum=5, step=0.01),
    Description(key=OPT_TARGET_IMPORT, minimum=0, maximum=1000, step=1, unit=UnitOfPower.WATT),
    Description(key=OPT_RESERVE_HOURS, minimum=0, maximum=24, step=0.1, unit=UnitOfTime.HOURS),
    Description(key=OPT_FREE_SOC_THRESHOLD, minimum=1, maximum=100, step=1, unit=PERCENTAGE),
    Description(key=OPT_LOW_SOC_OUTPUT, minimum=0, maximum=1000, step=20, unit=UnitOfPower.WATT),
    Description(key=OPT_LOW_SOC_THRESHOLD, minimum=0, maximum=99, step=1, unit=PERCENTAGE),
    Description(key=OPT_MIN_SOC_SHUTDOWN, minimum=0, maximum=50, step=1, unit=PERCENTAGE),
    Description(key=OPT_INTERVAL, minimum=5, maximum=300, step=1, unit=UnitOfTime.SECONDS),
    Description(key=OPT_SAFE_OUTPUT, minimum=0, maximum=1000, step=20, unit=UnitOfPower.WATT),
    Description(
        key=OPT_UNAVAILABLE_TIMEOUT, minimum=0, maximum=3600, step=5, unit=UnitOfTime.SECONDS
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarFlowZeroExportConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(SolarFlowOptionNumber(entry.runtime_data, desc) for desc in DESCRIPTIONS)


class SolarFlowOptionNumber(SolarFlowZeroExportEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, controller, description: Description) -> None:
        super().__init__(controller, description.key)
        self.description = description
        self._attr_translation_key = description.key
        self._attr_native_min_value = description.minimum
        self._attr_native_max_value = description.maximum
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.unit

    @property
    def native_value(self) -> float:
        return float(self.controller.option[self.description.key])

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.async_set_option(self.description.key, value)
