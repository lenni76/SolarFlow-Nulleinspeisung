"""Pure calculation logic for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from math import floor, isfinite

from .const import (
    BATTERY_CAPACITY_WH,
    ERROR_MAX,
    ERROR_MIN,
    INTEGRAL_MAX,
    INTEGRAL_MIN,
    MAX_OUTPUT,
    MIN_OUTPUT,
    MODE_FREE_PID,
    MODE_LOW_SOC,
    MODE_MIN_SOC,
    MODE_MORNING,
    MODE_SOC_LIMITED,
    OUTPUT_STEP,
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def round_to_step(value: float, step: float = OUTPUT_STEP) -> float:
    """PHP-compatible positive rounding to the configured output step."""
    return clamp(float(int((value / step) + 0.5) * step), MIN_OUTPUT, MAX_OUTPUT)


def floor_to_step(value: float, step: float = OUTPUT_STEP) -> float:
    """Round a safety ceiling down; never increase the permitted output."""
    return max(MIN_OUTPUT, float(floor(max(0, value) / step) * step))


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

    def validate(self) -> None:
        """Reject unsafe settings, including previously saved options."""
        numbers = (
            self.kp,
            self.ki,
            self.kd,
            self.target_import,
            self.reserve_hours,
            self.free_soc_threshold,
            self.low_soc_output,
            self.low_soc_threshold,
            self.min_soc_shutdown,
        )
        if not all(isfinite(value) for value in numbers):
            raise ValueError("Settings must be finite numbers")
        if (
            min(
                self.kp,
                self.ki,
                self.kd,
                self.target_import,
                self.reserve_hours,
                self.low_soc_output,
            )
            < 0
        ):
            raise ValueError("Gains, target import, reserve and output must not be negative")
        if (
            not 0
            <= self.min_soc_shutdown
            <= self.low_soc_threshold
            < self.free_soc_threshold
            <= 100
        ):
            raise ValueError("SOC thresholds must satisfy 0 <= shutdown <= low < free <= 100")


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
    limiting_reason: str = "pid"


def calculate(
    *,
    grid_power: float,
    current_output: float,
    actual_output: float,
    battery_soc: float,
    integral_old: float,
    last_error: float,
    now: time,
    params: Parameters,
) -> Result:
    """Retain PID gains, but constrain every mode to measured house demand.

    Positive grid power is import. The writable limit is not measured delivery.
    A sample-based ceiling cannot guarantee physical zero export after load changes.
    """
    params.validate()
    if not all(
        isfinite(value)
        for value in (
            grid_power,
            current_output,
            actual_output,
            battery_soc,
            integral_old,
            last_error,
        )
    ):
        raise ValueError("Inputs and PID state must be finite")
    if current_output < 0 or actual_output < 0 or not 0 <= battery_soc <= 100:
        raise ValueError("Output must be non-negative and SOC must be within 0..100")
    feed_in_limit = clamp(actual_output + grid_power - params.target_import, MIN_OUTPUT, MAX_OUTPUT)

    error = grid_power - params.target_import
    integral = clamp(integral_old + error, INTEGRAL_MIN, INTEGRAL_MAX)
    derivative = error - last_error
    correction = (params.kp * error) + (params.ki * integral) + (params.kd * derivative)
    pid_output = round_to_step(clamp(current_output + correction, MIN_OUTPUT, MAX_OUTPUT))
    # Hold only on the import side of the chosen target; never hold an export.
    pid_final = (
        current_output
        if params.target_import <= grid_power < params.target_import + OUTPUT_STEP
        else pid_output
    )

    sustainable_raw = (
        0.0
        if params.reserve_hours <= 0
        else (BATTERY_CAPACITY_WH * (battery_soc / 100.0) / params.reserve_hours)
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

    morning_active = (
        time_in_window(now, params.morning_start, params.morning_end) and battery_soc < 100
    )
    morning_output = floor_to_step(feed_in_limit)

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

    if mode == MODE_MIN_SOC:
        reason = "min_soc"
    elif mode == MODE_MORNING:
        reason = "target_import"
    elif mode == MODE_LOW_SOC:
        reason = "target_import" if feed_in_limit < params.low_soc_output else "low_soc"
    elif feed_in_limit <= min(pid_final, linear_output if mode == MODE_SOC_LIMITED else MAX_OUTPUT):
        reason = "target_import"
    elif mode == MODE_SOC_LIMITED and linear_output < pid_final:
        reason = "soc_reserve"
    else:
        reason = "pid"

    return Result(
        limiting_reason=reason,
        mode=mode,
        final_output=floor_to_step(clamp(final_output, MIN_OUTPUT, MAX_OUTPUT)),
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
