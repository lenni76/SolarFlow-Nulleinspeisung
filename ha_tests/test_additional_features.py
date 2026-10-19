"""Behavioral checks for opt-in comparison, ownership and production diagnostics."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solarflow_zero_export.const import DOMAIN
from custom_components.solarflow_zero_export.diagnostics import async_get_config_entry_diagnostics
from custom_components.solarflow_zero_export.targets import LEASES, async_target_key
from ha_tests.test_coupling import GRID_ID, POWER_ID


def form_data(entry):
    return {k: v for k, v in entry.data.items() if k != "output_limit_registry_id"}


def entity_id(hass, entry, key):
    return next(
        item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if item.unique_id == f"{entry.entry_id}_{key}"
    )


async def duplicate(hass, original, **updates):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Second controller", data={**original.data, **updates}, version=1
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_default_is_corrected_with_only_one_command(hass, pair):
    p = await pair.setup(grid=-10)
    s = p.ctrl.snapshot
    assert p.ctrl.option["control_strategy"] == "corrected"
    assert (
        s.steering_logic,
        s.final_output,
        s.corrected_output,
        s.legacy_output,
        s.comparison_difference,
    ) == ("corrected", 160, 160, 200, -40)
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 160)


async def test_opt_in_comparison_shadow_cannot_send_its_160w_command(hass, pair):
    p = await pair.setup(grid=-10, options={"control_strategy": "comparison"})
    s = p.ctrl.snapshot
    assert (s.steering_logic, s.final_output, s.corrected_output, s.legacy_output) == (
        "legacy",
        200,
        160,
        200,
    )
    assert s.limiting_reason == "legacy_rule"
    pair.post.assert_not_awaited()


async def test_comparison_preserves_original_morning_arithmetic_but_one_writer(hass, pair):
    p = await pair.setup(
        grid=300,
        output=800,
        actual=200,
        soc=50,
        hour=9,
        options={"control_strategy": "comparison", "target_import": 80},
    )
    s = p.ctrl.snapshot
    assert (s.final_output, s.corrected_output, s.legacy_output) == (1000, 420, 1000)
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 1000)


async def test_strategy_selector_changes_in_place_and_retains_existing_entity_ids(hass, pair):
    p = await pair.setup(grid=-10, options={"control_strategy": "comparison"})
    before = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), p.zero.entry_id)
    }
    select = entity_id(hass, p.zero, "control_strategy")
    assert hass.states.get(select).state == "comparison"
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "corrected"}, blocking=True
        )
        await hass.async_block_till_done()
        reload.assert_not_awaited()
    assert p.zero.runtime_data is p.ctrl
    assert p.ctrl.snapshot.steering_logic == "corrected"
    assert hass.states.get(select).state == "corrected"
    assert before == {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), p.zero.entry_id)
    }
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 160)


async def test_strategy_change_waits_for_pending_command(hass, pair):
    p = await pair.setup(grid=20)
    pair.behavior.entered = asyncio.Event()
    pair.behavior.release = asyncio.Event()
    hass.states.async_set(GRID_ID, -10, {"unit_of_measurement": "W"})
    update = asyncio.create_task(p.ctrl.async_update())
    change = None
    try:
        await asyncio.wait_for(pair.behavior.entered.wait(), 5)
        change = asyncio.create_task(p.ctrl.async_set_option("control_strategy", "comparison"))
        await asyncio.sleep(0)
        assert not change.done()
        assert p.ctrl.option["control_strategy"] == "corrected"
    finally:
        pair.behavior.release.set()
        await update
        if change is not None:
            await change
    assert p.ctrl.snapshot.steering_logic == "legacy"
    # Legacy hold uses the then-confirmed 160 W, with no shadow command.
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 160)


async def test_invalid_strategy_never_persists_or_writes(hass, pair):
    p = await pair.setup(grid=20)
    with pytest.raises(HomeAssistantError):
        await p.ctrl.async_set_option("control_strategy", "guessed")
    assert p.ctrl.option["control_strategy"] == "corrected"
    pair.post.assert_not_awaited()


async def test_corrupt_stored_strategy_uses_common_zero_safety(hass, pair):
    p = await pair.setup(grid=20, options={"control_strategy": "guessed"})
    assert p.ctrl.snapshot.mode == "invalid_input"
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.steering_logic == "safety"
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 0)


async def test_both_pid_states_survive_reload_and_reset_together(hass, pair):
    p = await pair.setup()
    corrected, legacy = p.ctrl.integral, p.ctrl.legacy_integral
    assert corrected == legacy == 300
    await hass.config_entries.async_reload(p.zero.entry_id)
    await hass.async_block_till_done()
    ctrl = p.zero.runtime_data
    assert ctrl.integral == ctrl.legacy_integral == 600
    await ctrl.async_reset_pid()
    assert (ctrl.integral, ctrl.last_error, ctrl.legacy_integral, ctrl.legacy_last_error) == (
        0,
        0,
        0,
        0,
    )


async def test_duplicate_user_flow_rejected_even_with_different_sources(hass, pair):
    p = await pair.setup(grid=20)
    data = {**form_data(p.zero), "grid_power_entity": "sensor.other_grid"}
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=data)
    assert result["type"] == "form"
    assert result["errors"] == {"output_limit_entity": "output_already_controlled"}
    pair.post.assert_not_awaited()


async def test_duplicate_reconfigure_rejected_without_reload_or_data_change(hass, pair):
    p = await pair.setup(grid=20)
    second = MockConfigEntry(
        domain=DOMAIN, data={**form_data(p.zero), "output_limit_entity": "number.other_output"}
    )
    second.add_to_hass(hass)
    before = dict(second.data)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": second.entry_id}
    )
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=form_data(p.zero)
        )
        reload.assert_not_awaited()
    assert result["type"] == "form"
    assert result["errors"] == {"output_limit_entity": "output_already_controlled"}
    assert dict(second.data) == before


async def test_duplicate_entry_is_blocked_including_safety_and_direct_write(hass, pair):
    p = await pair.setup(grid=20)
    second = await duplicate(hass, p.zero)
    ctrl = second.runtime_data
    assert ctrl.snapshot.mode == "target_conflict"
    assert ctrl.snapshot.available is False
    assert ctrl.snapshot.final_output is None
    await ctrl._async_write_output(500)
    hass.states.async_set(GRID_ID, "unavailable")
    pair.clock[0] += timedelta(seconds=120)
    await ctrl.async_update()
    assert ctrl.snapshot.mode == "target_conflict"
    pair.post.assert_not_awaited()
    assert hass.states.get(entity_id(hass, second, "steering_logic")).state == "target_conflict"
    assert hass.states.get(entity_id(hass, second, "healthy")).state == "on"


async def test_blocked_entry_can_claim_after_owner_has_fully_stopped(hass, pair):
    p = await pair.setup(grid=20)
    second = await duplicate(hass, p.zero)
    assert await hass.config_entries.async_unload(p.zero.entry_id)
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    await second.runtime_data.async_update()
    assert second.runtime_data.snapshot.steering_logic == "corrected"
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 440)
    # Stopping the old object again cannot release the new owner's lease.
    await p.ctrl.async_stop()
    key = async_target_key(hass, second.data)
    assert hass.data[LEASES][key] is second.runtime_data


async def test_pending_owner_keeps_lease_until_issued_write_has_finished(hass, pair):
    p = await pair.setup(grid=20)
    second = await duplicate(hass, p.zero)
    pair.behavior.entered = asyncio.Event()
    pair.behavior.release = asyncio.Event()
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    update = asyncio.create_task(p.ctrl.async_update())
    stop = None
    try:
        await asyncio.wait_for(pair.behavior.entered.wait(), 5)
        stop = asyncio.create_task(p.ctrl.async_stop())
        await asyncio.sleep(0)
        await second.runtime_data.async_update()
        assert second.runtime_data.snapshot.mode == "target_conflict"
        assert pair.post.await_count == 1
    finally:
        pair.behavior.release.set()
        await update
        if stop is not None:
            await stop
    await second.runtime_data.async_update()
    assert second.runtime_data.snapshot.steering_logic == "corrected"


async def test_renamed_output_retains_identity_and_duplicate_protection(hass, pair):
    p = await pair.setup(grid=20, explicit_power=False)
    registry = er.async_get(hass)
    identity = p.zero.data["output_limit_registry_id"]
    renamed = "number.user_renamed_solarflow_limit"
    registry.async_update_entity(p.output_id, new_entity_id=renamed)
    await hass.async_block_till_done()
    assert registry.async_get(renamed).id == identity
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.last_write_success is True
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 440)
    data = {**form_data(p.zero), "output_limit_entity": renamed, "output_power_entity": POWER_ID}
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=data)
    assert result["errors"] == {"output_limit_entity": "output_already_controlled"}


async def test_stop_releases_lease_even_if_store_fails(hass, pair):
    p = await pair.setup(grid=20)
    with (
        patch.object(p.ctrl._store, "async_save", side_effect=HomeAssistantError("disk failure")),
        pytest.raises(HomeAssistantError),
    ):
        await p.ctrl.async_stop()
    assert not hass.data[LEASES]
    assert p.ctrl.snapshot.steering_logic == "stopping"


async def test_status_distinguishes_actual_proposal_report_and_confirmed_command(hass, pair):
    p = await pair.setup(actual=180)
    s = p.ctrl.snapshot
    assert (s.actual_output, s.final_output, s.current_output, s.last_confirmed_output) == (
        180,
        440,
        440,
        440,
    )
    assert s.last_confirmed_at == pair.clock[0]
    assert (s.write_count, s.failed_write_count, s.skipped_write_count) == (1, 0, 0)
    await hass.async_block_till_done()
    for key, value in [
        ("actual_output", "180.0"),
        ("reported_output_limit", "440.0"),
        ("last_confirmed_output", "440.0"),
        ("steering_logic", "corrected"),
    ]:
        assert hass.states.get(entity_id(hass, p.zero, key)).state == value
    payload = await async_get_config_entry_diagnostics(hass, p.zero)
    json.dumps(payload, allow_nan=False)
    assert payload["snapshot"]["last_confirmed_at"] == pair.clock[0].isoformat()


async def test_skipped_write_does_not_invent_confirmation(hass, pair):
    p = await pair.setup(grid=20)
    s = p.ctrl.snapshot
    assert s.skipped_write_count == 1
    assert s.last_confirmed_output is None
    assert s.last_confirmed_at is None
    assert s.write_count == 0


async def test_failed_command_history_survives_next_success_and_input_failure(hass, pair):
    pair.behavior.accept = False
    p = await pair.setup()
    s = p.ctrl.snapshot
    assert s.failed_write_count == 1  # one HA command, despite API internal retry
    assert s.last_confirmed_at is None
    error, time = s.last_write_error, s.last_write_error_at
    pair.behavior.accept = True
    pair.clock[0] += timedelta(seconds=5)
    await p.ctrl.async_update()
    assert s.last_write_success is True
    assert s.write_count == 1
    assert (s.last_write_error, s.last_write_error_at) == (error, time)
    assert s.last_confirmed_at == pair.clock[0]
    hass.states.async_set(GRID_ID, "unavailable")
    await p.ctrl.async_update()
    assert s.final_output is s.corrected_output is s.legacy_output is s.actual_output is None
    assert s.last_confirmed_output == 400
    assert s.limiting_reason == "invalid_input"
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, p.zero, "failed_write_count")).state == "1"
    assert hass.states.get(entity_id(hass, p.zero, "last_confirmed_output")).state == "400.0"
    assert hass.states.get(entity_id(hass, p.zero, "last_write_error")).state != "unavailable"


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"soc": 3}, "min_soc"),
        ({"grid": 500, "soc": 20}, "low_soc"),
        ({"grid": 2000, "soc": 50}, "soc_reserve"),
        ({"grid": -10}, "target_import"),
        ({"grid": 2000, "maximum": 800}, "device_max"),
        ({}, "pid"),
    ],
)
async def test_limiting_reason_matches_active_constraint(hass, pair, kwargs, reason):
    p = await pair.setup(**kwargs)
    assert p.ctrl.snapshot.limiting_reason == reason


async def test_long_error_is_safe_for_ha_state_and_full_in_diagnostics(hass, pair):
    p = await pair.setup(grid=20)
    message = "device failure " * 100
    p.ctrl._write_failed(message)
    p.ctrl._notify()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id(hass, p.zero, "last_write_error"))
    assert len(state.state) == 255
    assert state.attributes["message"] == message
    assert p.ctrl.snapshot.last_write_error == message


async def test_disabled_status_clears_live_proposals_without_command(hass, pair):
    p = await pair.setup(grid=20)
    await p.ctrl.async_set_option("enabled", False)
    assert p.ctrl.snapshot.steering_logic == "disabled"
    assert p.ctrl.snapshot.final_output is None
    assert p.ctrl.snapshot.actual_output is None
    pair.post.assert_not_awaited()


async def test_acknowledged_safety_remains_visible_without_more_writes(hass, pair):
    p = await pair.setup(grid=20)
    hass.states.async_set(GRID_ID, "unavailable")
    await p.ctrl.async_update()
    pair.clock[0] += timedelta(seconds=61)
    await p.ctrl.async_update()
    await p.ctrl.async_update()
    await hass.async_block_till_done()
    assert p.ctrl.snapshot.steering_logic == "safety"
    assert p.ctrl.snapshot.limiting_reason == "safety_output"
    assert p.ctrl.snapshot.final_output == 0
    assert hass.states.get(entity_id(hass, p.zero, "calculated_output")).state == "0.0"
    assert hass.states.get(entity_id(hass, p.zero, "reported_output_limit")).state == "0.0"
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 0)


async def test_device_step_is_identified_as_limiting_reason(hass, pair):
    p = await pair.setup(grid=20)
    state = hass.states.get(p.output_id)
    hass.states.async_set(p.output_id, 200, {**state.attributes, "step": 100})
    hass.states.async_set(GRID_ID, 320, {"unit_of_measurement": "W"})
    await p.ctrl.async_update()
    assert p.ctrl.snapshot.limiting_reason == "device_step"
    pair.post.assert_awaited_once_with("HUB-TEST", "outputLimit", 400)


async def test_legacy_comparison_also_requires_acknowledgement(hass, pair):
    pair.behavior.accept = False
    p = await pair.setup(
        grid=300, output=800, actual=200, soc=50, hour=9, options={"control_strategy": "comparison"}
    )
    assert p.ctrl.snapshot.mode == "write_error"
    assert p.ctrl.snapshot.steering_logic == "legacy"
    assert p.ctrl.snapshot.failed_write_count == 1
    assert p.ctrl.snapshot.last_confirmed_output is None
    assert pair.post.await_count == 2


async def test_new_registry_identity_cannot_bypass_existing_entity_lease(hass, pair):
    from custom_components.solarflow_zero_export.targets import (
        async_claim,
        async_release,
        async_target_keys,
    )

    p = await pair.setup(grid=20)
    await p.ctrl.async_stop()
    registry = er.async_get(hass)
    entity = "number.initially_unregistered_output"
    data = {"output_limit_entity": entity}
    owner, other = object(), object()
    old_keys = async_target_keys(hass, data)
    assert old_keys == frozenset({f"entity:{entity}"})
    assert async_claim(hass, old_keys, owner)
    registry.async_get_or_create(
        "number", "test", "late-registry", suggested_object_id="initially_unregistered_output"
    )
    new_keys = async_target_keys(hass, data)
    assert len(new_keys) == 2
    assert not async_claim(hass, new_keys, other)
    # Failed claims must not leave partial ownership.
    assert len(hass.data[LEASES]) == 1
    async_release(hass, old_keys, owner)
    assert async_claim(hass, new_keys, other)
    async_release(hass, new_keys, other)
    assert not hass.data[LEASES]


async def test_corrupt_shadow_pid_state_does_not_break_corrected_control(hass, pair):
    p = await pair.setup(grid=20)
    await p.ctrl.async_stop()
    with patch.object(
        p.ctrl._store,
        "async_load",
        return_value={
            "integral": 300,
            "last_error": 300,
            "legacy_integral": "NaN",
            "legacy_last_error": 42,
        },
    ):
        await p.ctrl.async_start()
    assert p.ctrl.snapshot.steering_logic == "corrected"
    assert p.ctrl.legacy_integral == 0
    assert p.ctrl.snapshot.last_write_success is True


async def test_direct_write_is_inert_after_stop(hass, pair):
    p = await pair.setup(grid=20)
    await p.ctrl.async_stop()
    await p.ctrl._async_write_output(500)
    pair.post.assert_not_awaited()
