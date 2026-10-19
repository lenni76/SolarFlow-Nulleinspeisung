"""Diagnostics support for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from homeassistant.core import HomeAssistant

from .models import SolarFlowZeroExportConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry
) -> dict:
    return {
        "entry": {"title": entry.title, "data": dict(entry.data), "options": dict(entry.options)},
        "snapshot": {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in asdict(entry.runtime_data.snapshot).items()
        },
    }
