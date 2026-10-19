"""Regression tests for the corrected regulator with the unchanged published API.

Real Home Assistant services, registries and integration lifecycle are used.
Only the physical SolarFlow HTTP endpoint, clock and grid measurement are simulated.
No connection to any production Home Assistant or physical device is made.
"""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.solarflow2400_api.api import ZendureApiError
from custom_components.solarflow2400_api.const import DOMAIN as API_DOMAIN
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarflow_zero_export.const import DOMAIN as ZERO_DOMAIN

REPORT = json.loads(Path(__file__).with_name("report.json").read_text())
API = "custom_components.solarflow2400_api.api.ZendureLocalApi"
POWER_ID = "sensor.zendure_solarflow_outputhome_leistung"
GRID_ID = "sensor.test_grid_connection"


@pytest.fixture
async def pair(hass):
    report = deepcopy(REPORT)
    clock = [datetime(2026, 10, 19, 12, tzinfo=UTC)]
    behavior = SimpleNamespace(accept=True, entered=None, release=None)

    async def read(*args):
        return deepcopy(report)

    async def write(serial, key, value):
        assert serial == "HUB-TEST"
        if behavior.entered is not None:
            behavior.entered.set()
            await behavior.release.wait()
        if behavior.accept:
            report["properties"][key] = value
        return {}

    async def setup(
        *,
        grid=320,
        output=200,
        soc=95,
        maximum=1000,
        validation=True,
        options=None,
        hour=12,
        actual=None,
        explicit_power=True,
        power_id=POWER_ID,
    ):
        clock[0] = clock[0].replace(hour=hour)
        report["properties"].update(
            outputLimit=output,
            electricLevel=soc,
            inverseMaxPower=maximum,
            acMode=2,
            gridReverse=2,
            outputHomePower=output if actual is None else actual,
        )
        api = MockConfigEntry(
            domain=API_DOMAIN,
            unique_id="HUB-TEST",
            title="API test",
            data={"serial": "HUB-TEST", "host": "192.0.2.1", "model": "SolarFlow"},
            options={
                "validation_delay": 1,
                "auto_recovery": False,
                "command_validation": validation,
            },
            version=1,
        )
        api.add_to_hass(hass)
        # Existing registry IDs mirror an existing renamed-entity configuration, with test serials.
        registry = er.async_get(hass)
        for platform, unique, object_id in (
            ("number", "HUB-TEST_outputLimit", "zendure_solarflow_outputlimit"),
            ("sensor", "HUB-TEST_electricLevel", "zendure_solarflow_electriclevel"),
            ("sensor", "HUB-TEST_outputHomePower", "zendure_solarflow_outputhome_leistung"),
        ):
            registry.async_get_or_create(
                platform, API_DOMAIN, unique, config_entry=api, suggested_object_id=object_id
            )
        assert await hass.config_entries.async_setup(api.entry_id)
        await hass.async_block_till_done()

        def entity(unique):
            return next(
                item.entity_id
                for item in er.async_entries_for_config_entry(er.async_get(hass), api.entry_id)
                if item.unique_id == unique
            )

        output_id = entity("HUB-TEST_outputLimit")
        soc_id = entity("HUB-TEST_electricLevel")
        hass.states.async_set(GRID_ID, grid, {"unit_of_measurement": "W", "device_class": "power"})
        hass.states.async_set(
            power_id,
            output if actual is None else actual,
            {"unit_of_measurement": "W", "device_class": "power"},
        )
        zero = MockConfigEntry(
            domain=ZERO_DOMAIN,
            title="Regler test",
            data={
                "grid_power_entity": GRID_ID,
                "output_limit_entity": output_id,
                "battery_soc_entity": soc_id,
                **({"output_power_entity": power_id} if explicit_power else {}),
            },
            options=options or {},
            version=1,
        )
        zero.add_to_hass(hass)
        assert await hass.config_entries.async_setup(zero.entry_id)
        await hass.async_block_till_done()
        return SimpleNamespace(
            api=api, zero=zero, ctrl=zero.runtime_data, output_id=output_id, soc_id=soc_id
        )

    with (
        patch(f"{API}.async_get_report", side_effect=read),
        patch(f"{API}.async_write_property", side_effect=write) as post,
        patch(
            "custom_components.solarflow_zero_export.controller.dt_util",
            SimpleNamespace(now=lambda: clock[0], utcnow=lambda: clock[0]),
        ),
    ):
        yield SimpleNamespace(setup=setup, report=report, post=post, clock=clock, behavior=behavior)


async def test_normal_pair_retains_20w_target_and_confirms_440w(hass, pair):
    p = await pair.setup()
    assert p.output_id == "number.zendure_solarflow_outputlimit"
    assert p.soc_id == "sensor.zendure_solarflow_electriclevel"
    assert p.zero.data["output_power_entity"] == POWER_ID
    assert er.async_get(hass).async_get(POWER_ID).unique_id == "HUB-TEST_outputHomePower"
    assert p.ctrl.option["target_import"] == 20
    assert p.ctrl.snapshot.final_output == 440
    assert p.ctrl.snapshot.last_write_success is True
    assert p.api.runtime_data.diagnostics.command_success is True
    assert float(hass.states.get(p.output_id).state) == 440
    assert float(hass.states.get(p.soc_id).state) == 95
    assert hass.states.get(p.output_id).attributes["step"] == 1
    assert p.ctrl.snapshot.final_output % 20 == 0
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 440)


async def test_ignored_command_now_reaches_controller_as_error(hass, pair):
    pair.behavior.accept = False
    p = await pair.setup()
    assert p.ctrl.snapshot.mode == "write_error"
    assert p.ctrl.snapshot.last_write_success is False
    assert p.api.runtime_data.diagnostics.command_success is False
    assert pair.post.await_count == 2
    assert pair.report["properties"]["outputLimit"] == 200


async def test_safety_zero_is_retried_until_confirmed(hass, pair):
    p = await pair.setup(grid=20)
    assert pair.post.await_count == 0
    pair.behavior.accept = False
    hass.states.async_set(GRID_ID, "unavailable")
    await p.ctrl.async_update()
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    assert pair.post.await_count == 2
    assert p.ctrl._safe_output_written is False
    await p.ctrl.async_update()
    assert pair.post.await_count == 4
    pair.behavior.accept = True
    await p.ctrl.async_update()
    assert pair.post.await_count == 5
    assert p.ctrl._safe_output_written is True
    assert pair.report["properties"]["outputLimit"] == 0
    await p.ctrl.async_update()
    assert pair.post.await_count == 5


async def test_validation_off_ignored_command_is_not_reported_as_success(hass, pair):
    pair.behavior.accept = False
    p = await pair.setup(validation=False)
    assert p.ctrl.snapshot.last_write_success is False
    assert p.ctrl.snapshot.mode == "write_error"
    assert p.api.runtime_data.diagnostics.command_success is None
    assert pair.report["properties"]["outputLimit"] == 200
    assert pair.post.await_count == 1


async def test_reported_800w_bound_is_respected_before_api_call(hass, pair):
    p = await pair.setup(grid=2000, maximum=800)
    assert p.ctrl.snapshot.final_output == 800
    assert hass.states.get(p.output_id).attributes["max"] == 800
    assert p.ctrl.snapshot.last_write_success is True
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 800)


async def test_reported_1000w_bound_accepts_same_controller_command(hass, pair):
    p = await pair.setup(grid=2000, maximum=1000)
    assert p.ctrl.snapshot.final_output == 1000
    assert p.ctrl.snapshot.last_write_success is True
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 1000)


async def test_low_soc_reduces_output_during_50w_export(hass, pair):
    p = await pair.setup(grid=-50, output=100, soc=20)
    assert p.ctrl.snapshot.mode == "low_soc"
    assert p.ctrl.snapshot.final_output == 20
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 20)


async def test_negative_grid_is_not_a_hold_zone(hass, pair):
    p = await pair.setup(grid=-10, output=200, soc=95)
    assert p.ctrl.snapshot.mode == "free_pid"
    assert p.ctrl.snapshot.final_output == 160
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 160)


async def test_morning_respects_configured_80w_target(hass, pair):
    p = await pair.setup(grid=300, output=200, soc=50, hour=9, options={"target_import": 80})
    assert p.ctrl.snapshot.mode == "morning"
    assert p.ctrl.option["target_import"] == 80
    assert p.ctrl.snapshot.final_output == 420  # measured 200 + grid 300 - selected 80


async def test_invalid_soc_thresholds_reach_safety_timeout(hass, pair):
    p = await pair.setup(grid=20, options={"free_soc_threshold": 20, "low_soc_threshold": 30})
    assert p.ctrl.snapshot.mode == "invalid_input"
    first_failure = p.ctrl._unavailable_since
    for _ in range(3):
        pair.clock[0] += timedelta(seconds=61)
        await p.ctrl.async_update()
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 0)
    assert p.ctrl._unavailable_since == first_failure


async def test_unload_waits_until_pending_output_command_finishes(hass, pair):
    p = await pair.setup(grid=20)
    pair.behavior.entered = asyncio.Event()
    pair.behavior.release = asyncio.Event()
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    update = asyncio.create_task(p.ctrl.async_update())
    unload = None
    try:
        await asyncio.wait_for(pair.behavior.entered.wait(), timeout=5)
        unload = asyncio.create_task(hass.config_entries.async_unload(p.zero.entry_id))
        for _ in range(10):
            await asyncio.sleep(0)
            if p.ctrl._stopping:
                break
        assert p.ctrl._stopping
        assert not unload.done()
        assert pair.report["properties"]["outputLimit"] == 200
    finally:
        pair.behavior.release.set()
        await update
        if unload is not None:
            assert await unload
    count = pair.post.await_count
    await p.ctrl.async_update()
    assert pair.post.await_count == count
    assert pair.report["properties"]["outputLimit"] == 440
    with pytest.raises(HomeAssistantError):
        await p.ctrl.async_set_option("kp", 0.5)
    with pytest.raises(HomeAssistantError):
        await p.ctrl.async_reset_pid()


async def test_option_change_applies_without_reload(hass, pair):
    p = await pair.setup(grid=20)
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        await p.ctrl.async_set_option("kp", 0.5)
        await hass.async_block_till_done()
        reload.assert_not_awaited()
    assert p.zero.runtime_data is p.ctrl
    assert p.ctrl.option["kp"] == 0.5


async def test_disabling_controller_does_not_set_output_zero(hass, pair):
    p = await pair.setup(grid=20, options={"enabled": False})
    assert p.ctrl.snapshot.mode == "disabled"
    assert pair.report["properties"]["outputLimit"] == 200
    assert pair.post.await_count == 0


async def test_morning_uses_measured_200w_output_instead_of_limit(hass, pair):
    p = await pair.setup(grid=300, output=800, actual=200, soc=50, hour=9)
    assert p.ctrl.snapshot.final_output == 480
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 480)


async def test_grid_unit_kw_is_converted_to_watts(hass, pair):
    p = await pair.setup(grid=20)
    hass.states.async_set(GRID_ID, 0.32, {"unit_of_measurement": "kW"})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.grid_power == 320
    assert p.ctrl.snapshot.available is True
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 440)


async def test_reserve_calculation_still_assumes_2700wh(hass, pair):
    p = await pair.setup(grid=20, soc=50)
    assert p.ctrl.snapshot.sustainable_output == 270  # 2700 * .5 / 5
    assert p.ctrl.snapshot.sustainable_output != 240  # 2400 Wh without extension


async def test_legacy_three_entity_mapping_resolves_exact_api_measurement(hass, pair):
    p = await pair.setup(explicit_power=False)
    assert "output_power_entity" not in p.zero.data
    assert p.ctrl.snapshot.last_write_success is True
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 440)


async def test_explicit_user_sensor_wins_over_different_api_measurement(hass, pair):
    alternative = "sensor.test_independent_delivery_meter"
    p = await pair.setup(grid=20, power_id=alternative)
    hass.states.async_set(alternative, 0, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 0)


async def test_missing_selected_measurement_is_not_replaced_by_limit(hass, pair):
    p = await pair.setup(grid=20)
    hass.states.async_remove(POWER_ID)
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.mode == "invalid_input"
    assert pair.post.await_count == 0
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 0)


async def test_ignored_unvalidated_safety_zero_is_retried(hass, pair):
    p = await pair.setup(grid=20, validation=False)
    hass.states.async_set(GRID_ID, "unavailable")
    pair.behavior.accept = False
    await p.ctrl.async_update()
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    assert p.ctrl._safe_output_written is False
    await p.ctrl.async_update()
    assert pair.post.await_count == 2


async def test_current_max_and_step_bound_every_command(hass, pair):
    p = await pair.setup(grid=20)
    state = hass.states.get(p.output_id)
    hass.states.async_set(p.output_id, 200, {**state.attributes, "max": 835, "step": 100})
    hass.states.async_set(GRID_ID, 2000, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.final_output == 800
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 800)


async def test_safety_value_is_bounded_to_current_device_max(hass, pair):
    p = await pair.setup(grid=20, maximum=800, options={"safe_output": 1000})
    hass.states.async_set(GRID_ID, "unavailable")
    await p.ctrl.async_update()
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 800)


@pytest.mark.parametrize(
    "attrs",
    [
        {"min": 100},
        {"max": "nan"},
        {"step": 0},
        {"step": "nan"},
        {"unit_of_measurement": "kW"},
    ],
)
async def test_invalid_output_contract_never_sends_a_command(hass, pair, attrs):
    p = await pair.setup(grid=20)
    state = hass.states.get(p.output_id)
    hass.states.async_set(p.output_id, 200, {**state.attributes, **attrs})
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.mode == "invalid_input"
    assert pair.post.await_count == 0


@pytest.mark.parametrize(
    "key,value",
    [
        ("kp", float("nan")),
        ("ki", -1),
        ("target_import", -1),
        ("interval", 0),
        ("interval", 5.5),
        ("unavailable_timeout", -1),
        ("safe_output", 1001),
        ("free_soc_threshold", 20),
        ("morning_start", "bad"),
        ("morning_start", "07:30:00+00:00"),
        ("enabled", "false"),
    ],
)
async def test_invalid_ui_settings_are_rejected_before_persisting(hass, pair, key, value):
    p = await pair.setup(grid=20)
    before = dict(p.zero.options)
    with pytest.raises(HomeAssistantError):
        await p.ctrl.async_set_option(key, value)
    assert dict(p.zero.options) == before
    assert pair.post.await_count == 0


async def test_interval_change_replaces_timer_without_reload(hass, pair):
    p = await pair.setup(grid=20)
    old_timer = p.ctrl._remove_interval
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        await p.ctrl.async_set_option("interval", 20)
        await hass.async_block_till_done()
        reload.assert_not_awaited()
    assert p.ctrl._remove_interval is not old_timer
    assert p.ctrl.option["interval"] == 20


async def test_reconfigure_reloads_exactly_once_without_deprecated_listener(hass, pair):
    p = await pair.setup(grid=20)
    before = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), p.zero.entry_id)
    }
    result = await hass.config_entries.flow.async_init(
        ZERO_DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": p.zero.entry_id}
    )
    assert result["type"] == "form"
    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                key: value
                for key, value in p.zero.data.items()
                if key != "output_limit_registry_id"
            },
        )
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(p.zero.entry_id)
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert p.zero.runtime_data is not p.ctrl
    assert p.ctrl._stopping is True
    after = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), p.zero.entry_id)
    }
    assert after == before


async def test_overlapping_timer_calls_do_not_queue_extra_writes(hass, pair):
    p = await pair.setup(grid=20)
    pair.behavior.entered = asyncio.Event()
    pair.behavior.release = asyncio.Event()
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    update = asyncio.create_task(p.ctrl.async_update())
    try:
        await asyncio.wait_for(pair.behavior.entered.wait(), timeout=5)
        await p.ctrl.async_update()
        await p.ctrl.async_update()
        assert pair.post.await_count == 1
    finally:
        pair.behavior.release.set()
        await update
    assert pair.post.await_count == 1


async def test_option_change_waits_for_pending_write_then_uses_same_controller(hass, pair):
    p = await pair.setup(grid=20)
    pair.behavior.entered = asyncio.Event()
    pair.behavior.release = asyncio.Event()
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    update = asyncio.create_task(p.ctrl.async_update())
    change = None
    try:
        await asyncio.wait_for(pair.behavior.entered.wait(), timeout=5)
        change = asyncio.create_task(p.ctrl.async_set_option("kp", 0.5))
        await asyncio.sleep(0)
        assert not change.done()
        assert p.ctrl.option["kp"] == 0.6
    finally:
        pair.behavior.release.set()
        await update
        if change is not None:
            await change
    assert p.zero.runtime_data is p.ctrl
    assert p.ctrl.option["kp"] == 0.5


async def test_platform_setup_failure_does_not_leave_a_writing_timer(hass, pair):
    original = hass.config_entries.async_forward_entry_setups

    async def forward(entry, platforms):
        if entry.domain == ZERO_DOMAIN:
            raise RuntimeError("Simulated platform setup failure")
        await original(entry, platforms)

    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=forward),
        pytest.raises(AssertionError),
    ):
        await pair.setup(grid=20)
    zero = next(entry for entry in hass.config_entries.async_entries(ZERO_DOMAIN))
    assert zero.runtime_data._stopping is True
    assert zero.runtime_data._remove_interval is None
    await zero.runtime_data.async_update()
    assert pair.post.await_count == 0


async def test_failed_platform_unload_resumes_the_existing_timer(hass, pair):
    p = await pair.setup(grid=20)
    with patch.object(
        hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=False
    ):
        assert not await hass.config_entries.async_unload(p.zero.entry_id)
    assert p.ctrl._stopping is False
    assert p.ctrl._remove_interval is not None


@pytest.mark.parametrize("bad", [{"integral": "bad"}, {"last_error": float("nan")}, [1]])
async def test_corrupt_pid_store_does_not_prevent_safe_start(hass, pair, bad):
    p = await pair.setup(grid=20)
    await p.ctrl.async_stop()
    with patch.object(p.ctrl._store, "async_load", new_callable=AsyncMock, return_value=bad):
        await p.ctrl.async_start()
    assert p.ctrl.integral == 0
    assert p.ctrl.last_error == 0
    assert p.ctrl.snapshot.available is True


async def test_existing_ui_entities_update_options_without_reloading(hass, pair):
    p = await pair.setup(grid=20)
    entities = er.async_entries_for_config_entry(er.async_get(hass), p.zero.entry_id)
    lookup = {
        item.unique_id.removeprefix(p.zero.entry_id + "_"): item.entity_id for item in entities
    }
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        await hass.services.async_call(
            "number", "set_value", {"entity_id": lookup["kp"], "value": 0.5}, blocking=True
        )
        await hass.services.async_call(
            "time",
            "set_value",
            {"entity_id": lookup["morning_start"], "time": "08:00:00"},
            blocking=True,
        )
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": lookup["enabled"]}, blocking=True
        )
        await hass.async_block_till_done()
        reload.assert_not_awaited()
    assert p.zero.runtime_data is p.ctrl
    assert p.ctrl.option["kp"] == 0.5
    assert p.ctrl.option["morning_start"] == "08:00:00"
    assert p.ctrl.option["enabled"] is False
    assert pair.post.await_count == 0
    p.ctrl.integral = 15
    p.ctrl.last_error = 50
    await hass.services.async_call(
        "button", "press", {"entity_id": lookup["reset_pid"]}, blocking=True
    )
    assert p.ctrl.integral == 0 and p.ctrl.last_error == 0
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": lookup["enabled"]}, blocking=True
    )
    assert p.ctrl.option["enabled"] is True
    assert pair.post.await_count == 0


async def test_cancelled_write_is_not_reported_as_success(hass, pair):
    p = await pair.setup(grid=20)
    pair.behavior.entered = asyncio.Event()
    pair.behavior.release = asyncio.Event()
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    update = asyncio.create_task(p.ctrl.async_update())
    try:
        await asyncio.wait_for(pair.behavior.entered.wait(), timeout=5)
        update.cancel()
        with pytest.raises(asyncio.CancelledError):
            await update
    finally:
        pair.behavior.release.set()
        if not update.done():
            await update
    assert p.ctrl.snapshot.mode == "write_error"
    assert p.ctrl.snapshot.last_write_success is False
    assert not p.ctrl._update_lock.locked()
    await p.ctrl.async_stop()
    await p.ctrl.async_update()
    assert pair.post.await_count == 1


async def test_network_write_failure_is_visible_to_controller(hass, pair):
    p = await pair.setup(grid=20)
    pair.post.side_effect = ZendureApiError("Simulated network write failure")
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.mode == "write_error"
    assert p.ctrl.snapshot.last_write_success is False
    assert "Simulated network write failure" in p.ctrl.snapshot.last_error_message


async def test_validation_report_failure_does_not_confirm_command(hass, pair):
    p = await pair.setup(grid=20)
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    with patch(f"{API}.async_get_report", side_effect=ZendureApiError("Report offline")):
        await p.ctrl.async_update()
    assert p.ctrl.snapshot.last_write_success is False
    assert pair.post.await_count == 2


async def test_measured_output_kw_is_converted(hass, pair):
    p = await pair.setup(grid=20)
    hass.states.async_set(POWER_ID, 0.2, {"unit_of_measurement": "kW"})
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 440)


@pytest.mark.parametrize("unit,value", [("V", 200), ("W", "nan"), ("W", -1)])
async def test_invalid_measured_output_starts_input_error(hass, pair, unit, value):
    p = await pair.setup(grid=20)
    hass.states.async_set(POWER_ID, value, {"unit_of_measurement": unit})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.mode == "invalid_input"
    assert pair.post.await_count == 0


async def test_new_user_flow_stores_all_four_sources_and_starts_controller(hass, pair):
    p = await pair.setup(grid=20)
    data = dict(p.zero.data)
    assert await hass.config_entries.async_unload(p.zero.entry_id)
    await hass.config_entries.async_remove(p.zero.entry_id)
    result = await hass.config_entries.flow.async_init(ZERO_DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={key: value for key, value in data.items() if key != "output_limit_registry_id"},
    )
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    created = result["result"]
    assert dict(created.data) == data
    assert created.runtime_data.snapshot.available is True
    assert pair.post.await_count == 0


async def test_disabled_automatic_api_measurement_is_not_used(hass, pair):
    p = await pair.setup(grid=20, explicit_power=False)
    er.async_get(hass).async_update_entity(POWER_ID, disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.mode == "invalid_input"
    assert pair.post.await_count == 0


async def test_corrupt_timing_and_safety_options_fall_back_to_zero_safety(hass, pair):
    p = await pair.setup(
        grid=20,
        options={
            "interval": 0,
            "unavailable_timeout": "nan",
            "safe_output": "nan",
        },
    )
    assert p.ctrl.snapshot.mode == "invalid_input"
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 0)
    assert p.ctrl._safe_output_written is True
