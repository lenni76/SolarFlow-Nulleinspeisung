from datetime import time

from custom_components.solarflow_zero_export.calculation import (
    Parameters,
    calculate,
    time_in_window,
)

P = Parameters(
    kp=0.6,
    ki=0.04,
    kd=0.15,
    target_import=20,
    reserve_hours=5,
    free_soc_threshold=90,
    low_soc_output=100,
    low_soc_threshold=30,
    min_soc_shutdown=5,
    morning_start=time(7, 30),
    morning_end=time(11),
)


def test_min_soc_priority():
    r = calculate(
        grid_power=500,
        current_output=500,
        actual_output=500,
        battery_soc=5,
        integral_old=0,
        last_error=0,
        now=time(12),
        params=P,
    )
    assert r.final_output == 0 and r.mode == "min_soc_shutdown"


def test_morning_priority_and_limit():
    r = calculate(
        grid_power=200,
        current_output=300,
        actual_output=300,
        battery_soc=50,
        integral_old=0,
        last_error=0,
        now=time(8),
        params=P,
    )
    assert r.mode == "morning" and r.final_output == 480


def test_low_soc_ceiling_respects_measured_grid_demand():
    r = calculate(
        grid_power=100,
        current_output=0,
        actual_output=0,
        battery_soc=20,
        integral_old=0,
        last_error=0,
        now=time(12),
        params=P,
    )
    assert r.mode == "low_soc" and r.final_output == 80


def test_dead_zone_keeps_current_output():
    r = calculate(
        grid_power=20,
        current_output=400,
        actual_output=400,
        battery_soc=95,
        integral_old=0,
        last_error=0,
        now=time(12),
        params=P,
    )
    assert r.final_output == 400


def test_integral_clamped():
    r = calculate(
        grid_power=5000,
        current_output=0,
        actual_output=0,
        battery_soc=95,
        integral_old=1400,
        last_error=0,
        now=time(12),
        params=P,
    )
    assert r.integral == 1500


def test_overnight_window():
    assert time_in_window(time(23), time(22), time(6))
    assert time_in_window(time(5), time(22), time(6))
    assert not time_in_window(time(12), time(22), time(6))
