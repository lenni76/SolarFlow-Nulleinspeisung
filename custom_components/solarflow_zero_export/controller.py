"""Serialized runtime control; measured output and current HA service bounds."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal
from math import isfinite
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .bindings import async_output_power_entity
from .calculation import Parameters, calculate, clamp
from .const import (
    CONF_BATTERY_SOC,
    CONF_GRID_POWER,
    CONF_OUTPUT_TARGET_ID,
    CONTROL_STRATEGIES,
    DEFAULTS,
    DOMAIN,
    ERROR_MAX,
    ERROR_MIN,
    INTEGRAL_MAX,
    INTEGRAL_MIN,
    MAX_OUTPUT,
    MODE_DISABLED,
    MODE_INVALID_INPUT,
    MODE_WRITE_ERROR,
    OPT_CONTROL_STRATEGY,
    OPT_ENABLED,
    OPT_FREE_SOC_THRESHOLD,
    OPT_INTERVAL,
    OPT_KD,
    OPT_KI,
    OPT_KP,
    OPT_LOW_SOC_OUTPUT,
    OPT_LOW_SOC_THRESHOLD,
    OPT_MIN_SOC_SHUTDOWN,
    OPT_MORNING_END,
    OPT_MORNING_START,
    OPT_RESERVE_HOURS,
    OPT_SAFE_OUTPUT,
    OPT_TARGET_IMPORT,
    OPT_UNAVAILABLE_TIMEOUT,
    STRATEGY_COMPARISON,
)
from .legacy_calculation import calculate as calculate_legacy
from .models import ControllerSnapshot, SolarFlowZeroExportConfigEntry
from .targets import (
    async_claim,
    async_release,
    async_target_data,
    async_target_entity,
    async_target_keys,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("A boolean is not a numeric measurement")
    number = float(value)
    if not isfinite(number):
        raise ValueError("A finite number is required")
    return number


def _parameters(options: Mapping[str, Any]) -> Parameters:
    if options[OPT_CONTROL_STRATEGY] not in CONTROL_STRATEGIES:
        raise ValueError("Unknown control strategy")
    params = Parameters(
        kp=_number(options[OPT_KP]),
        ki=_number(options[OPT_KI]),
        kd=_number(options[OPT_KD]),
        target_import=_number(options[OPT_TARGET_IMPORT]),
        reserve_hours=_number(options[OPT_RESERVE_HOURS]),
        free_soc_threshold=_number(options[OPT_FREE_SOC_THRESHOLD]),
        low_soc_output=_number(options[OPT_LOW_SOC_OUTPUT]),
        low_soc_threshold=_number(options[OPT_LOW_SOC_THRESHOLD]),
        min_soc_shutdown=_number(options[OPT_MIN_SOC_SHUTDOWN]),
        morning_start=time.fromisoformat(str(options[OPT_MORNING_START])),
        morning_end=time.fromisoformat(str(options[OPT_MORNING_END])),
    )
    params.validate()
    if params.morning_start.tzinfo is not None or params.morning_end.tzinfo is not None:
        raise ValueError("Morning times must be local times without a timezone suffix")
    interval = _number(options[OPT_INTERVAL])
    timeout = _number(options[OPT_UNAVAILABLE_TIMEOUT])
    safe = _number(options[OPT_SAFE_OUTPUT])
    if not 5 <= interval <= 300 or not interval.is_integer():
        raise ValueError("Interval must be an integer within 5..300 seconds")
    if not 0 <= timeout <= 3600 or not timeout.is_integer():
        raise ValueError("Safety timeout must be an integer within 0..3600 seconds")
    if not 0 <= safe <= MAX_OUTPUT:
        raise ValueError("Safety output must be within 0..1000 W")
    if not isinstance(options[OPT_ENABLED], bool):
        raise ValueError("Enabled must be a boolean")
    return params


class SolarFlowZeroExportController:
    """Run one controller with serialized option changes, resets and shutdown."""

    def __init__(self, hass: HomeAssistant, entry: SolarFlowZeroExportConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.snapshot = ControllerSnapshot()
        self.integral = 0.0
        self.last_error = 0.0
        self.legacy_integral = 0.0
        self.legacy_last_error = 0.0
        self._target_lease: frozenset[str] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._remove_interval: Callable[[], None] | None = None
        self._remove_shutdown: Callable[[], None] | None = None
        self._update_lock = asyncio.Lock()
        self._stopping = False
        self._unavailable_since: datetime | None = None
        self._safe_output_written = False
        self._store: Store[dict[str, float]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    @property
    def option(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.entry.options}

    def _schedule_interval(self) -> None:
        if self._remove_shutdown is None:
            self._remove_shutdown = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._async_shutdown
            )
        if self._remove_interval is not None:
            self._remove_interval()
        # A corrupt stored interval must not prevent the error/safety loop starting.
        try:
            interval = _number(self.option[OPT_INTERVAL])
            if not 5 <= interval <= 300 or not interval.is_integer():
                raise ValueError("Invalid interval")
        except TypeError, ValueError, OverflowError:
            interval = DEFAULTS[OPT_INTERVAL]
        self._remove_interval = async_track_time_interval(
            self.hass,
            self._async_interval,
            timedelta(seconds=interval),
            cancel_on_shutdown=True,
        )

    async def _async_shutdown(self, _event: Event) -> None:
        await self.async_stop()

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        try:
            self.integral = clamp(_number(stored.get("integral", 0)), INTEGRAL_MIN, INTEGRAL_MAX)
            self.last_error = clamp(_number(stored.get("last_error", 0)), ERROR_MIN, ERROR_MAX)
        except AttributeError, TypeError, ValueError, OverflowError:
            _LOGGER.warning("Ignoring invalid persisted PID state")
            self.integral = self.last_error = 0.0
        try:
            self.legacy_integral = clamp(
                _number(stored.get("legacy_integral", self.integral)), INTEGRAL_MIN, INTEGRAL_MAX
            )
            self.legacy_last_error = clamp(
                _number(stored.get("legacy_last_error", self.last_error)), ERROR_MIN, ERROR_MAX
            )
        except AttributeError, TypeError, ValueError, OverflowError:
            self.legacy_integral = self.legacy_last_error = 0.0
        if not self.entry.data.get(CONF_OUTPUT_TARGET_ID):
            data = async_target_data(self.hass, self.entry.data)
            if data.get(CONF_OUTPUT_TARGET_ID):
                self.hass.config_entries.async_update_entry(self.entry, data=data)
        self.snapshot.integral = self.integral
        self._stopping = False
        self._schedule_interval()
        await self.async_update()

    async def async_stop(self) -> None:
        """Stop new work and wait for already issued writes before returning."""
        self._stopping = True
        if self._remove_shutdown is not None:
            self._remove_shutdown()
            self._remove_shutdown = None
        if self._remove_interval is not None:
            self._remove_interval()
            self._remove_interval = None
        async with self._update_lock:
            try:
                await self._async_save_state()
            finally:
                async_release(self.hass, self._target_lease, self)
                self._target_lease = None
                self._inactive("stopping")
                self._notify()

    async def async_resume(self) -> None:
        """Resume after HA could not unload the entity platforms."""
        self._stopping = False
        self._schedule_interval()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
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
        return _number(state.state)

    def _read_power(self, entity_id: str) -> float:
        value = self._read_float(entity_id)
        unit = self.hass.states.get(entity_id).attributes.get("unit_of_measurement")
        if unit == "W":
            return value
        if unit == "kW":
            return value * 1000
        raise ValueError(f"{entity_id} must report W or kW")

    def _bounded_output(self, value: float, entity_id: str | None = None) -> float:
        """Validate the actual service contract, then floor into its valid range."""
        entity_id = entity_id or async_target_entity(self.hass, self.entry.data)
        self._read_float(entity_id)
        attrs = self.hass.states.get(entity_id).attributes
        if attrs.get("unit_of_measurement") != "W":
            raise ValueError("The output limit must be a number entity in W")
        lower = _number(attrs.get("min"))
        upper = min(MAX_OUTPUT, _number(attrs.get("max")))
        step = _number(attrs.get("step"))
        if lower != 0 or upper < 0 or step <= 0:
            raise ValueError("Output limit must support 0 W and have valid max/step")
        desired = Decimal(str(clamp(_number(value), 0, upper)))
        quantum = Decimal(str(step))
        return float((desired / quantum).to_integral_value(rounding=ROUND_FLOOR) * quantum)

    async def async_update(self) -> None:
        # Time callbacks do not queue obsolete samples behind a slow device write.
        if self._stopping or self._update_lock.locked():
            return
        async with self._update_lock:
            if self._stopping:
                return
            try:
                await self._async_update_impl()
            finally:
                self._notify()

    def _inactive(self, reason: str) -> None:
        self.snapshot.mode = reason
        self.snapshot.steering_logic = reason
        self.snapshot.limiting_reason = reason
        self.snapshot.available = reason == MODE_DISABLED
        self.snapshot.final_output = None
        self.snapshot.corrected_output = None
        self.snapshot.legacy_output = None
        self.snapshot.comparison_difference = None
        self.snapshot.actual_output = None
        self.snapshot.current_output = None
        self.snapshot.morning_active = False

    def _ensure_target(self) -> bool:
        if not self.entry.data.get(CONF_OUTPUT_TARGET_ID):
            data = async_target_data(self.hass, self.entry.data)
            if data.get(CONF_OUTPUT_TARGET_ID):
                self.hass.config_entries.async_update_entry(self.entry, data=data)
        key = async_target_keys(self.hass, self.entry.data)
        if self._target_lease != key:
            async_release(self.hass, self._target_lease, self)
            self._target_lease = None
        if not async_claim(self.hass, key, self):
            self._inactive("target_conflict")
            self.snapshot.last_error_message = "Another controller owns this output limit"
            # A blocked controller must never issue even a safety command.
            self._unavailable_since = None
            self._safe_output_written = False
            return False
        self._target_lease = key
        return True

    async def _async_update_impl(self) -> None:
        if not self._ensure_target():
            return
        if self.option[OPT_ENABLED] is False:
            self._inactive(MODE_DISABLED)
            return

        try:
            params = _parameters(self.option)
            grid = self._read_power(self.entry.data[CONF_GRID_POWER])
            output = self._read_float(async_target_entity(self.hass, self.entry.data))
            soc_id = self.entry.data[CONF_BATTERY_SOC]
            soc = self._read_float(soc_id)
            if self.hass.states.get(soc_id).attributes.get("unit_of_measurement") != "%":
                raise ValueError("Battery SOC must be reported in percent")
            power_id = async_output_power_entity(self.hass, self.entry.data)
            if power_id is None:
                raise ValueError("Select the measured SolarFlow output power in reconfigure")
            actual = self._read_power(power_id)
            result = calculate(
                grid_power=grid,
                current_output=output,
                actual_output=actual,
                battery_soc=soc,
                integral_old=self.integral,
                last_error=self.last_error,
                now=dt_util.now().time(),
                params=params,
            )
            legacy = calculate_legacy(
                grid_power=grid,
                current_output=output,
                battery_soc=soc,
                integral_old=self.legacy_integral,
                last_error=self.legacy_last_error,
                now=dt_util.now().time(),
                params=params,
            )
            corrected_output = self._bounded_output(result.final_output)
            legacy_output = self._bounded_output(legacy.final_output)
            comparison = self.option[OPT_CONTROL_STRATEGY] == STRATEGY_COMPARISON
            active = legacy if comparison else result
            desired = legacy_output if comparison else corrected_output
        except (TypeError, ValueError, OverflowError) as err:
            await self._handle_invalid_input(str(err))
            return

        self._unavailable_since = None
        self._safe_output_written = False
        self.integral = result.integral
        self.last_error = result.error
        self.legacy_integral = legacy.integral
        self.legacy_last_error = legacy.error
        reason = "legacy_rule" if comparison else result.limiting_reason
        if desired < active.final_output:
            maximum = min(
                MAX_OUTPUT,
                _number(
                    self.hass.states.get(
                        async_target_entity(self.hass, self.entry.data)
                    ).attributes["max"]
                ),
            )
            reason = "device_max" if active.final_output > maximum else "device_step"
        # Update in place so acknowledged command history survives invalid input and mode changes.
        self.snapshot.mode = active.mode
        self.snapshot.available = True
        self.snapshot.steering_logic = "legacy" if comparison else "corrected"
        self.snapshot.limiting_reason = reason
        self.snapshot.grid_power = grid
        self.snapshot.current_output = output
        self.snapshot.actual_output = actual
        self.snapshot.battery_soc = soc
        self.snapshot.final_output = desired
        self.snapshot.corrected_output = corrected_output
        self.snapshot.legacy_output = legacy_output
        self.snapshot.comparison_difference = corrected_output - legacy_output
        for field in (
            "error",
            "integral",
            "derivative",
            "correction",
            "feed_in_limit",
            "sustainable_output",
            "linear_soc_output",
            "morning_output",
            "morning_active",
        ):
            setattr(self.snapshot, field, getattr(active, field))
        self.snapshot.last_error_message = None
        if abs(desired - output) < 0.01:
            self.snapshot.skipped_write_count += 1
        else:
            await self._async_write_output(desired)
        await self._async_save_state()

    async def _handle_invalid_input(self, message: str) -> None:
        now = dt_util.utcnow()
        if self._unavailable_since is None:
            self._unavailable_since = now
        self._inactive(MODE_INVALID_INPUT)
        self.snapshot.last_error_message = message
        try:
            self.snapshot.current_output = self._read_float(
                async_target_entity(self.hass, self.entry.data)
            )
        except TypeError, ValueError, OverflowError:
            self.snapshot.current_output = None
        try:
            timeout = _number(self.option[OPT_UNAVAILABLE_TIMEOUT])
            if not 0 <= timeout <= 3600 or not timeout.is_integer():
                raise ValueError("Invalid safety timeout")
        except TypeError, ValueError, OverflowError:
            timeout = DEFAULTS[OPT_UNAVAILABLE_TIMEOUT]
        if timeout > 0 and (now - self._unavailable_since).total_seconds() >= timeout:
            try:
                safe = _number(self.option[OPT_SAFE_OUTPUT])
                if not 0 <= safe <= MAX_OUTPUT:
                    raise ValueError("Invalid safety output")
            except TypeError, ValueError, OverflowError:
                safe = DEFAULTS[OPT_SAFE_OUTPUT]
            self.snapshot.limiting_reason = "safety_output"
            self.snapshot.steering_logic = "safety"
            if self._safe_output_written:
                self.snapshot.final_output = self.snapshot.last_confirmed_output
            else:
                self.snapshot.final_output = safe
                await self._async_write_output(safe)
                self._safe_output_written = self.snapshot.last_write_success

    def _write_failed(self, message: str) -> None:
        self.snapshot.mode = MODE_WRITE_ERROR
        self.snapshot.limiting_reason = MODE_WRITE_ERROR
        self.snapshot.last_write_success = False
        self.snapshot.last_error_message = message
        self.snapshot.last_write_error = message
        self.snapshot.last_write_error_at = dt_util.utcnow()
        self.snapshot.failed_write_count += 1

    async def _async_write_output(self, value: float) -> None:
        if self._stopping or not self._ensure_target():
            return
        # Capture the target across awaits: reconfigure may update entry.data meanwhile.
        entity_id = async_target_entity(self.hass, self.entry.data)
        try:
            bounded = self._bounded_output(value, entity_id)
            self.snapshot.final_output = bounded
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": bounded},
                blocking=True,
            )
            reported = self._read_float(entity_id)
            self.snapshot.current_output = reported
            if abs(reported - bounded) >= 0.01:
                raise HomeAssistantError(
                    f"Output limit {bounded} W is not confirmed; reported {reported} W"
                )
        except asyncio.CancelledError:
            self._write_failed("Output command cancelled; result is unconfirmed")
            raise
        except (HomeAssistantError, TypeError, ValueError, OverflowError) as err:
            _LOGGER.error("Failed to set SolarFlow output to %s W: %s", value, err)
            self._write_failed(str(err))
            # The service may fail after the device accepted a write: report only what is readable.
            try:
                self.snapshot.current_output = self._read_float(entity_id)
            except TypeError, ValueError, OverflowError:
                self.snapshot.current_output = None
            return
        self.snapshot.last_write_success = True
        self.snapshot.last_confirmed_output = bounded
        self.snapshot.last_confirmed_at = dt_util.utcnow()
        self.snapshot.write_count += 1

    async def async_reset_pid(self) -> None:
        async with self._update_lock:
            if self._stopping:
                raise HomeAssistantError("The SolarFlow controller is stopping")
            self.integral = self.last_error = 0.0
            self.legacy_integral = self.legacy_last_error = 0.0
            self.snapshot.integral = self.snapshot.error = 0.0
            await self._async_save_state()
            self._notify()

    async def async_set_option(self, key: str, value: Any) -> None:
        async with self._update_lock:
            if self._stopping:
                raise HomeAssistantError("The SolarFlow controller is stopping")
            if key not in DEFAULTS:
                raise HomeAssistantError(f"Unknown SolarFlow setting: {key}")
            options = {**self.entry.options, key: value}
            try:
                _parameters({**DEFAULTS, **options})
            except (TypeError, ValueError, OverflowError) as err:
                raise HomeAssistantError(f"Invalid SolarFlow settings: {err}") from err
            self.hass.config_entries.async_update_entry(self.entry, options=options)
            if key == OPT_INTERVAL:
                self._schedule_interval()
            try:
                await self._async_update_impl()
            finally:
                self._notify()

    async def _async_save_state(self) -> None:
        await self._store.async_save(
            {
                "integral": self.integral,
                "last_error": self.last_error,
                "legacy_integral": self.legacy_integral,
                "legacy_last_error": self.legacy_last_error,
            }
        )
