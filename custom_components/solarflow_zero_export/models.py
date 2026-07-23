"""Data models for SolarFlow Nulleinspeisung."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .controller import SolarFlowZeroExportController


@dataclass(slots=True)
class ControllerSnapshot:
    """Calculated controller values exposed to entities and diagnostics."""

    mode: str = "starting"
    available: bool = False
    grid_power: float | None = None
    current_output: float | None = None
    battery_soc: float | None = None
    final_output: float | None = None
    error: float = 0.0
    integral: float = 0.0
    derivative: float = 0.0
    correction: float = 0.0
    feed_in_limit: float = 0.0
    sustainable_output: float = 0.0
    linear_soc_output: float = 0.0
    morning_output: float = 0.0
    morning_active: bool = False
    last_write_success: bool = True
    last_error_message: str | None = None
    write_count: int = 0
    skipped_write_count: int = 0


SolarFlowZeroExportConfigEntry: TypeAlias = "ConfigEntry[SolarFlowZeroExportController]"
