"""Sensor entities for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import SolarFlowZeroExportEntity
from .models import SolarFlowZeroExportConfigEntry


@dataclass(frozen=True, kw_only=True)
class Desc(SensorEntityDescription):
    attribute: str
    always_available: bool = False


DESCRIPTIONS = (
    Desc(key="mode", translation_key="mode", attribute="mode", always_available=True),
    Desc(
        key="calculated_output",
        translation_key="calculated_output",
        attribute="final_output",
        always_available=True,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Desc(
        key="pid_error",
        translation_key="pid_error",
        attribute="error",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Desc(key="pid_integral", translation_key="pid_integral", attribute="integral"),
    Desc(key="pid_derivative", translation_key="pid_derivative", attribute="derivative"),
    Desc(
        key="feed_in_limit",
        translation_key="feed_in_limit",
        attribute="feed_in_limit",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Desc(
        key="sustainable_output",
        translation_key="sustainable_output",
        attribute="sustainable_output",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    Desc(
        key="linear_soc_output",
        translation_key="linear_soc_output",
        attribute="linear_soc_output",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


# Additional entities; all existing keys and unique IDs stay unchanged.
DESCRIPTIONS += tuple(
    Desc(
        key=key,
        translation_key=key,
        attribute=attribute,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    )
    for key, attribute in (
        ("actual_output", "actual_output"),
        ("reported_output_limit", "current_output"),
        ("corrected_output", "corrected_output"),
        ("legacy_output", "legacy_output"),
        ("comparison_difference", "comparison_difference"),
        ("last_confirmed_output", "last_confirmed_output"),
    )
)
DESCRIPTIONS += (
    Desc(
        key="steering_logic",
        translation_key="steering_logic",
        attribute="steering_logic",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "starting",
            "corrected",
            "legacy",
            "disabled",
            "invalid_input",
            "target_conflict",
            "stopping",
            "safety",
        ],
        always_available=True,
    ),
    Desc(
        key="limiting_reason",
        translation_key="limiting_reason",
        attribute="limiting_reason",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "starting",
            "pid",
            "target_import",
            "low_soc",
            "soc_reserve",
            "min_soc",
            "device_max",
            "device_step",
            "safety_output",
            "invalid_input",
            "write_error",
            "legacy_rule",
            "target_conflict",
            "disabled",
            "stopping",
        ],
        always_available=True,
    ),
    Desc(
        key="last_confirmed_at",
        translation_key="last_confirmed_at",
        attribute="last_confirmed_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        always_available=True,
    ),
    Desc(
        key="last_write_error_at",
        translation_key="last_write_error_at",
        attribute="last_write_error_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        always_available=True,
    ),
    Desc(
        key="last_write_error",
        translation_key="last_write_error",
        attribute="last_write_error",
        always_available=True,
    ),
    Desc(
        key="write_count",
        translation_key="write_count",
        attribute="write_count",
        always_available=True,
    ),
    Desc(
        key="failed_write_count",
        translation_key="failed_write_count",
        attribute="failed_write_count",
        always_available=True,
    ),
    Desc(
        key="skipped_write_count",
        translation_key="skipped_write_count",
        attribute="skipped_write_count",
        always_available=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarFlowZeroExportConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(SolarFlowDiagnosticSensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class SolarFlowDiagnosticSensor(SolarFlowZeroExportEntity, SensorEntity):
    entity_description: Desc

    def __init__(self, controller, description: Desc) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        value = getattr(self.controller.snapshot, self.entity_description.attribute)
        if self.entity_description.key == "last_write_error":
            return value[:255] if value else "none"
        return value

    @property
    def extra_state_attributes(self):
        if self.entity_description.key == "last_write_error":
            return {"message": self.controller.snapshot.last_write_error}
        return None

    @property
    def available(self) -> bool:
        return (
            self.entity_description.always_available
            or self.entity_description.key in ("last_confirmed_output", "reported_output_limit")
            or self.controller.snapshot.available
        )
