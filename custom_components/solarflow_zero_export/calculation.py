"""Pure calculation logic for SolarFlow Nulleinspeisung."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from .const import (
    BATTERY_CAPACITY_WH, DEAD_ZONE_MAX, DEAD_ZONE_MIN, ERROR_MAX, ERROR_MIN,
    FEED_IN_BUFFER, INTEGRAL_MAX, INTEGRAL_MIN, MAX_OUTPUT, MIN_OUTPUT,
    MODE_FREE_PID, MODE_LOW_SOC, MODE_MIN_SOC, MODE_MORNING,
    MODE_SOC_LIMITED, MORNING_TARGET_IMPORT, OUTPUT_STEP,
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def round_to_step(value: float, step: float = OUTPUT_STEP) -> float:
    """PHP-compatible positive rounding to the configured output step."""
    return clamp(float(int((value / step) + 0.5) * step), MIN_OUTPUT, MAX_OUTPUT)


def time_in_window(now: time, start: time, end: time) -> bool:
    """Return whether now is inside a time window, including overnight windows."""
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


@dataclass(slots=True, frozen=True)
class Parameters:
    kp: float
    ki: float
    kd: float
    target_import: float
    reserve_hours: float
    free_soc_threshold: float
    low_soc_output: float
    low_soc_threshold: float
    min_soc_shutdown: float
    morning_start: time
    morning_end: time


@dataclass(slots=True, frozen=True)
class Result:
    mode: str
    final_output: float
    error: float
    integral: float
    derivative: float
    correction: float
    feed_in_limit: float
    sustainable_output: float
    linear_soc_output: float
    morning_output: float
    morning_active: bool


def calculate(
    *, grid_power: float, current_output: float, battery_soc: float,
    integral_old: float, last_error: float, now: time, params: Parameters,
) -> Result:
    """Calculate one iteration, preserving the original script's discrete PID semantics."""
    feed_in_limit = clamp(grid_power + FEED_IN_BUFFER + current_output, MIN_OUTPUT, MAX_OUTPUT)

    error = grid_power - params.target_import
    integral = clamp(integral_old + error, INTEGRAL_MIN, INTEGRAL_MAX)
    derivative = error - last_error
    correction = (params.kp * error) + (params.ki * integral) + (params.kd * derivative)
    pid_output = round_to_step(clamp(current_output + correction, MIN_OUTPUT, MAX_OUTPUT))
    pid_final = current_output if DEAD_ZONE_MIN < grid_power < DEAD_ZONE_MAX else pid_output

    sustainable_raw = 0.0 if params.reserve_hours <= 0 else (
        BATTERY_CAPACITY_WH * (battery_soc / 100.0) / params.reserve_hours
    )
    sustainable = clamp(sustainable_raw, MIN_OUTPUT, MAX_OUTPUT)

    if battery_soc <= params.low_soc_threshold:
        linear_raw = params.low_soc_output
    elif battery_soc >= params.free_soc_threshold:
        linear_raw = MAX_OUTPUT
    else:
        denominator = params.free_soc_threshold - params.low_soc_threshold
        ratio = (battery_soc - params.low_soc_threshold) / denominator
        linear_raw = params.low_soc_output + ratio * (sustainable - params.low_soc_output)
    linear_output = round_to_step(clamp(linear_raw, MIN_OUTPUT, MAX_OUTPUT))

    morning_active = time_in_window(now, params.morning_start, params.morning_end) and battery_soc < 100
    morning_house_load = current_output + grid_power
    morning_output = round_to_step(clamp(morning_house_load - MORNING_TARGET_IMPORT, MIN_OUTPUT, MAX_OUTPUT))

    if battery_soc <= params.min_soc_shutdown:
        mode = MODE_MIN_SOC
        final_output = 0.0
    elif morning_active:
        mode = MODE_MORNING
        final_output = min(morning_output, feed_in_limit)
    elif battery_soc < params.low_soc_threshold:
        mode = MODE_LOW_SOC
        final_output = min(params.low_soc_output, feed_in_limit)
    elif battery_soc < params.free_soc_threshold:
        mode = MODE_SOC_LIMITED
        final_output = min(pid_final, linear_output, feed_in_limit)
    else:
        mode = MODE_FREE_PID
        final_output = min(pid_final, feed_in_limit)

    return Result(
        mode=mode,
        final_output=clamp(final_output, MIN_OUTPUT, MAX_OUTPUT),
        error=clamp(error, ERROR_MIN, ERROR_MAX),
        integral=integral,
        derivative=derivative,
        correction=correction,
        feed_in_limit=feed_in_limit,
        sustainable_output=sustainable,
        linear_soc_output=linear_output,
        morning_output=morning_output,
        morning_active=morning_active,
    )
