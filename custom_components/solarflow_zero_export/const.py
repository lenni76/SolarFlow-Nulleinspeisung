"""Constants for SolarFlow Nulleinspeisung."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "solarflow_zero_export"
NAME: Final = "SolarFlow-Nulleinspeisung"
MANUFACTURER: Final = "lenni76"

PLATFORMS: Final = ["binary_sensor", "button", "number", "sensor", "switch", "time"]

CONF_GRID_POWER: Final = "grid_power_entity"
CONF_OUTPUT_LIMIT: Final = "output_limit_entity"
CONF_BATTERY_SOC: Final = "battery_soc_entity"

OPT_KP: Final = "kp"
OPT_KI: Final = "ki"
OPT_KD: Final = "kd"
OPT_TARGET_IMPORT: Final = "target_import"
OPT_RESERVE_HOURS: Final = "reserve_hours"
OPT_FREE_SOC_THRESHOLD: Final = "free_soc_threshold"
OPT_LOW_SOC_OUTPUT: Final = "low_soc_output"
OPT_LOW_SOC_THRESHOLD: Final = "low_soc_threshold"
OPT_MIN_SOC_SHUTDOWN: Final = "min_soc_shutdown"
OPT_MORNING_START: Final = "morning_start"
OPT_MORNING_END: Final = "morning_end"
OPT_INTERVAL: Final = "interval"
OPT_ENABLED: Final = "enabled"
OPT_SAFE_OUTPUT: Final = "safe_output"
OPT_UNAVAILABLE_TIMEOUT: Final = "unavailable_timeout"

DEFAULTS: Final = {
    OPT_KP: 0.6,
    OPT_KI: 0.04,
    OPT_KD: 0.15,
    OPT_TARGET_IMPORT: 20.0,
    OPT_RESERVE_HOURS: 5.0,
    OPT_FREE_SOC_THRESHOLD: 90.0,
    OPT_LOW_SOC_OUTPUT: 100.0,
    OPT_LOW_SOC_THRESHOLD: 30.0,
    OPT_MIN_SOC_SHUTDOWN: 5.0,
    OPT_MORNING_START: "07:30:00",
    OPT_MORNING_END: "11:00:00",
    OPT_INTERVAL: 5,
    OPT_ENABLED: True,
    OPT_SAFE_OUTPUT: 0.0,
    OPT_UNAVAILABLE_TIMEOUT: 60,
}

MIN_OUTPUT: Final = 0.0
MAX_OUTPUT: Final = 1000.0
OUTPUT_STEP: Final = 20.0
INTEGRAL_MIN: Final = -1500.0
INTEGRAL_MAX: Final = 1500.0
ERROR_MIN: Final = -2000.0
ERROR_MAX: Final = 2000.0
FEED_IN_BUFFER: Final = 750.0
BATTERY_CAPACITY_WH: Final = 2700.0
DEAD_ZONE_MIN: Final = -15.0
DEAD_ZONE_MAX: Final = 35.0
MORNING_TARGET_IMPORT: Final = 20.0

MODE_DISABLED: Final = "disabled"
MODE_MIN_SOC: Final = "min_soc_shutdown"
MODE_MORNING: Final = "morning"
MODE_LOW_SOC: Final = "low_soc"
MODE_SOC_LIMITED: Final = "soc_limited_pid"
MODE_FREE_PID: Final = "free_pid"
MODE_INVALID_INPUT: Final = "invalid_input"
MODE_WRITE_ERROR: Final = "write_error"
MODE_STARTING: Final = "starting"
