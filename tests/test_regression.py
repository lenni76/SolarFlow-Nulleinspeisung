"""Safety and arithmetic regressions for the four approved correction areas."""

from dataclasses import replace
from datetime import time
from math import inf, nan

import pytest

from custom_components.solarflow_zero_export.calculation import calculate, floor_to_step
from tests.test_calculation import P


def calc(
    *,
    grid=320,
    limit=200,
    actual=200,
    soc=95,
    target=20,
    now=time(12),
    integral=0,
    previous_error=0,
    **overrides,
):
    return calculate(
        grid_power=grid,
        current_output=limit,
        actual_output=actual,
        battery_soc=soc,
        integral_old=integral,
        last_error=previous_error,
        now=now,
        params=replace(P, target_import=target, **overrides),
    )


def test_normal_pid_values_unchanged():
    r = calc()
    assert r.final_output == 440
    assert (r.error, r.integral, r.derivative) == (300, 300, 300)


def test_low_soc_does_not_force_exporting_output():
    assert calc(grid=-50, limit=100, actual=100, soc=20).final_output == 20


def test_export_is_never_in_hold_zone():
    assert calc(grid=-10).final_output == 160


def test_changing_target_moves_hold_zone():
    assert calc(grid=20, target=100).final_output <= 120
    assert calc(grid=100, target=100).final_output == 200


def test_morning_honors_80w_target():
    assert calc(grid=300, actual=200, target=80, soc=50, now=time(9)).final_output == 420


def test_morning_does_not_confuse_800w_limit_with_200w_delivery():
    assert calc(grid=300, limit=800, actual=200, soc=50, now=time(9)).final_output == 480


def test_large_integral_cannot_overrule_measured_demand_ceiling():
    assert calc(grid=-100, limit=800, actual=300, integral=1500).final_output <= 180


@pytest.mark.parametrize(
    "soc,now", [(4, time(12)), (20, time(12)), (50, time(12)), (95, time(12)), (50, time(9))]
)
def test_all_modes_respect_house_demand_budget(soc, now):
    for actual in (0, 1, 100, 801, 2400):
        for grid in (-1000, -50, -10, 0, 19, 20, 35, 100, 2000):
            for target in (0, 20, 80):
                r = calc(grid=grid, actual=actual, soc=soc, now=now, target=target)
                budget = max(0, min(1000, actual + grid - target))
                assert 0 <= r.final_output <= budget
                assert r.final_output % 20 == 0


def test_external_pv_surplus_cannot_request_more_discharge():
    assert calc(grid=-500, actual=100, limit=800).final_output == 0


@pytest.mark.parametrize("bad", [nan, inf, -inf])
def test_nonfinite_measurements_are_rejected(bad):
    with pytest.raises(ValueError):
        calc(actual=bad)


@pytest.mark.parametrize("soc", [-1, 101])
def test_soc_outside_percent_range_rejected(soc):
    with pytest.raises(ValueError):
        calc(soc=soc)


@pytest.mark.parametrize(
    "options",
    [
        {"target": -1},
        {"free_soc_threshold": 30},
        {"low_soc_threshold": 4},
        {"kp": nan},
        {"reserve_hours": -1},
        {"low_soc_output": -20},
    ],
)
def test_invalid_settings_rejected(options):
    with pytest.raises(ValueError):
        calc(**options)


@pytest.mark.parametrize("house", [60, 100, 500, 999, 1600])
def test_idealized_closed_loop_never_commands_beyond_fixed_house_demand(house):
    # Instantaneous actuation and exact, synchronous measurements are explicit assumptions.
    output = 0.0
    integral = previous_error = 0.0
    for _ in range(40):
        r = calc(
            grid=house - output,
            limit=output,
            actual=output,
            integral=integral,
            previous_error=previous_error,
        )
        output, integral, previous_error = r.final_output, r.integral, r.error
        assert house - output >= 20


def test_safety_floor_never_rounds_30w_ceiling_up_to_40w():
    assert floor_to_step(30) == 20
