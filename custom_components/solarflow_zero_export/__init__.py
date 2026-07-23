"""SolarFlow Nulleinspeisung integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .controller import SolarFlowZeroExportController
from .models import SolarFlowZeroExportConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> bool:
    controller = SolarFlowZeroExportController(hass, entry)
    entry.runtime_data = controller
    await controller.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
