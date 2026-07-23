"""Binary sensor entities for SolarFlow Nulleinspeisung."""
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry

async def async_setup_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([SolarFlowHealthy(entry.runtime_data), SolarFlowMorning(entry.runtime_data)])

class SolarFlowHealthy(SolarFlowZeroExportEntity, BinarySensorEntity):
    _attr_translation_key = "healthy"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    def __init__(self, controller) -> None: super().__init__(controller, "healthy")
    @property
    def is_on(self) -> bool: return not self.controller.snapshot.available or not self.controller.snapshot.last_write_success

class SolarFlowMorning(SolarFlowZeroExportEntity, BinarySensorEntity):
    _attr_translation_key = "morning_active"
    def __init__(self, controller) -> None: super().__init__(controller, "morning_active")
    @property
    def is_on(self) -> bool: return self.controller.snapshot.morning_active
