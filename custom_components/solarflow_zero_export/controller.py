"""Runtime controller for SolarFlow Nulleinspeisung."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from math import isfinite
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .calculation import Parameters, calculate
from .const import (
    CONF_BATTERY_SOC, CONF_GRID_POWER, CONF_OUTPUT_LIMIT, DEFAULTS, DOMAIN,
    MODE_DISABLED, MODE_INVALID_INPUT, MODE_WRITE_ERROR, OPT_ENABLED,
    OPT_FREE_SOC_THRESHOLD, OPT_INTERVAL, OPT_KD, OPT_KI, OPT_KP,
    OPT_LOW_SOC_OUTPUT, OPT_LOW_SOC_THRESHOLD, OPT_MIN_SOC_SHUTDOWN,
    OPT_MORNING_END, OPT_MORNING_START, OPT_RESERVE_HOURS, OPT_SAFE_OUTPUT,
    OPT_TARGET_IMPORT, OPT_UNAVAILABLE_TIMEOUT,
)
from .models import ControllerSnapshot, SolarFlowZeroExportConfigEntry

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


class SolarFlowZeroExportController:
    """Run the PID controller independently of source integrations."""

    def __init__(self, hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.snapshot = ControllerSnapshot()
        self.integral = 0.0
        self.last_error = 0.0
        self._listeners: list[callable] = []
        self._remove_interval: callable | None = None
        self._running = False
        self._unavailable_since: datetime | None = None
        self._safe_output_written = False
        self._store: Store[dict[str, float]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    @property
    def option(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.entry.options}

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self.integral = float(stored.get("integral", 0.0))
        self.last_error = float(stored.get("last_error", 0.0))
        self.snapshot.integral = self.integral
        interval = int(self.option[OPT_INTERVAL])
        self._remove_interval = async_track_time_interval(
            self.hass, self._async_interval, timedelta(seconds=interval)
        )
        await self.async_update()

    async def async_stop(self) -> None:
        if self._remove_interval is not None:
            self._remove_interval()
            self._remove_interval = None
        await self._async_save_state()

    def async_add_listener(self, listener: callable) -> callable:
        self._listeners.append(listener)
        @callback
        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)
        return remove

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def _async_interval(self, _now: datetime) -> None:
        await self.async_update()

    def _read_float(self, entity_id: str) -> float:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            raise ValueError(f"{entity_id} is unavailable")
        value = float(state.state)
        if not isfinite(value):
            raise ValueError(f"{entity_id} is not finite")
        return value

    async def async_update(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            await self._async_update_impl()
        finally:
            self._running = False
            self._notify()

    async def _async_update_impl(self) -> None:
        if not bool(self.option[OPT_ENABLED]):
            self.snapshot.mode = MODE_DISABLED
            self.snapshot.available = True
            return

        try:
            grid = self._read_float(self.entry.data[CONF_GRID_POWER])
            output = self._read_float(self.entry.data[CONF_OUTPUT_LIMIT])
            soc = self._read_float(self.entry.data[CONF_BATTERY_SOC])
        except (TypeError, ValueError) as err:
            await self._handle_invalid_input(str(err))
            return

        self._unavailable_since = None
        self._safe_output_written = False
        params = Parameters(
            kp=float(self.option[OPT_KP]), ki=float(self.option[OPT_KI]), kd=float(self.option[OPT_KD]),
            target_import=float(self.option[OPT_TARGET_IMPORT]),
            reserve_hours=float(self.option[OPT_RESERVE_HOURS]),
            free_soc_threshold=float(self.option[OPT_FREE_SOC_THRESHOLD]),
            low_soc_output=float(self.option[OPT_LOW_SOC_OUTPUT]),
            low_soc_threshold=float(self.option[OPT_LOW_SOC_THRESHOLD]),
            min_soc_shutdown=float(self.option[OPT_MIN_SOC_SHUTDOWN]),
            morning_start=time.fromisoformat(str(self.option[OPT_MORNING_START])),
            morning_end=time.fromisoformat(str(self.option[OPT_MORNING_END])),
        )
        if params.free_soc_threshold <= params.low_soc_threshold:
            await self._handle_invalid_input("Free-SOC threshold must be greater than Low-SOC threshold")
            return

        result = calculate(
            grid_power=grid, current_output=output, battery_soc=soc,
            integral_old=self.integral, last_error=self.last_error,
            now=dt_util.now().time(), params=params,
        )
        self.integral = result.integral
        self.last_error = result.error
        self.snapshot = ControllerSnapshot(
            mode=result.mode, available=True, grid_power=grid, current_output=output,
            battery_soc=soc, final_output=result.final_output, error=result.error,
            integral=result.integral, derivative=result.derivative,
            correction=result.correction, feed_in_limit=result.feed_in_limit,
            sustainable_output=result.sustainable_output,
            linear_soc_output=result.linear_soc_output,
            morning_output=result.morning_output, morning_active=result.morning_active,
            last_write_success=self.snapshot.last_write_success,
            last_error_message=None, write_count=self.snapshot.write_count,
            skipped_write_count=self.snapshot.skipped_write_count,
        )

        if abs(result.final_output - output) < 0.01:
            self.snapshot.skipped_write_count += 1
        else:
            await self._async_write_output(result.final_output)
        await self._async_save_state()

    async def _handle_invalid_input(self, message: str) -> None:
        now = dt_util.utcnow()
        if self._unavailable_since is None:
            self._unavailable_since = now
        self.snapshot.mode = MODE_INVALID_INPUT
        self.snapshot.available = False
        self.snapshot.last_error_message = message
        timeout = int(self.option[OPT_UNAVAILABLE_TIMEOUT])
        if timeout > 0 and (now - self._unavailable_since).total_seconds() >= timeout and not self._safe_output_written:
            await self._async_write_output(float(self.option[OPT_SAFE_OUTPUT]))
            self._safe_output_written = self.snapshot.last_write_success

    async def _async_write_output(self, value: float) -> None:
        try:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": self.entry.data[CONF_OUTPUT_LIMIT], "value": value},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.error("Failed to set SolarFlow output to %s W: %s", value, err)
            self.snapshot.mode = MODE_WRITE_ERROR
            self.snapshot.last_write_success = False
            self.snapshot.last_error_message = str(err)
            return
        self.snapshot.last_write_success = True
        self.snapshot.write_count += 1

    async def async_reset_pid(self) -> None:
        self.integral = 0.0
        self.last_error = 0.0
        self.snapshot.integral = 0.0
        self.snapshot.error = 0.0
        await self._async_save_state()
        self._notify()

    async def async_set_option(self, key: str, value: Any) -> None:
        options = {**self.entry.options, key: value}
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        if key == OPT_INTERVAL:
            if self._remove_interval is not None:
                self._remove_interval()
            self._remove_interval = async_track_time_interval(
                self.hass, self._async_interval, timedelta(seconds=int(value))
            )
        await self.async_update()

    async def _async_save_state(self) -> None:
        await self._store.async_save({"integral": self.integral, "last_error": self.last_error})
