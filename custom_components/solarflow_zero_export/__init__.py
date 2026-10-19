"""SolarFlow Nulleinspeisung integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .controller import SolarFlowZeroExportController
from .models import SolarFlowZeroExportConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> bool:
    controller = SolarFlowZeroExportController(hass, entry)
    entry.runtime_data = controller
    try:
        await controller.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # Do not leave a writing timer alive after failed/cancelled HA setup.
        await controller.async_stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        await entry.runtime_data.async_resume()
    return unload_ok
