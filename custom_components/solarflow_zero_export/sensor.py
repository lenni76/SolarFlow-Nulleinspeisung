"""Sensor entities for SolarFlow Nulleinspeisung."""
from __future__ import annotations

from dataclasses import dataclass
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry

@dataclass(frozen=True, kw_only=True)
class Desc(SensorEntityDescription):
    attribute: str

DESCRIPTIONS = (
    Desc(key="mode", translation_key="mode", attribute="mode"),
    Desc(key="calculated_output", translation_key="calculated_output", attribute="final_output", native_unit_of_measurement=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT),
    Desc(key="pid_error", translation_key="pid_error", attribute="error", native_unit_of_measurement=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT),
    Desc(key="pid_integral", translation_key="pid_integral", attribute="integral"),
    Desc(key="pid_derivative", translation_key="pid_derivative", attribute="derivative"),
    Desc(key="feed_in_limit", translation_key="feed_in_limit", attribute="feed_in_limit", native_unit_of_measurement=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT),
    Desc(key="sustainable_output", translation_key="sustainable_output", attribute="sustainable_output", native_unit_of_measurement=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT),
    Desc(key="linear_soc_output", translation_key="linear_soc_output", attribute="linear_soc_output", native_unit_of_measurement=UnitOfPower.WATT, state_class=SensorStateClass.MEASUREMENT),
)

async def async_setup_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(SolarFlowDiagnosticSensor(entry.runtime_data, d) for d in DESCRIPTIONS)

class SolarFlowDiagnosticSensor(SolarFlowZeroExportEntity, SensorEntity):
    entity_description: Desc
    def __init__(self, controller, description: Desc) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description
    @property
    def native_value(self):
        return getattr(self.controller.snapshot, self.entity_description.attribute)
    @property
    def available(self) -> bool:
        return self.controller.snapshot.available or self.entity_description.key == "mode"
