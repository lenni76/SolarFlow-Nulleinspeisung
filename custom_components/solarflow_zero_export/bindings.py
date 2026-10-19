"""Resolve measured power without guessing user-customized entity IDs."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_OUTPUT_POWER
from .targets import async_target_entity


@callback
def async_output_power_entity(hass: HomeAssistant, data: Mapping[str, str]) -> str | None:
    """Honor an explicit selection, or identify the exact API sensor in the registry.

    Existing three-entity configurations remain usable with API 1.2.0/1.2.1.
    A different provider must explicitly select its measured output sensor.
    Missing, disabled or ambiguous matches are not substituted with the setpoint.
    """
    if entity_id := data.get(CONF_OUTPUT_POWER):
        return entity_id
    registry = er.async_get(hass)
    output = registry.async_get(async_target_entity(hass, data))
    if (
        output is None
        or output.platform != "solarflow2400_api"
        or not output.unique_id.endswith("_outputLimit")
        or output.config_entry_id is None
    ):
        return None
    expected = output.unique_id.removesuffix("_outputLimit") + "_outputHomePower"
    matches = [
        item.entity_id
        for item in er.async_entries_for_config_entry(registry, output.config_entry_id)
        if item.platform == output.platform
        and item.domain == "sensor"
        and item.unique_id == expected
        and item.device_id == output.device_id
        and item.disabled_by is None
    ]
    return matches[0] if len(matches) == 1 else None
