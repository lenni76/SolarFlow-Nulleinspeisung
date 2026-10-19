"""Config flow for SolarFlow Nulleinspeisung."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .bindings import async_output_power_entity
from .const import (
    CONF_BATTERY_SOC,
    CONF_GRID_POWER,
    CONF_OUTPUT_LIMIT,
    CONF_OUTPUT_POWER,
    DOMAIN,
    NAME,
)
from .targets import async_target_conflict, async_target_data, async_target_entity


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_GRID_POWER, default=defaults.get(CONF_GRID_POWER)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_OUTPUT_LIMIT, default=defaults.get(CONF_OUTPUT_LIMIT)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="number")),
            vol.Required(
                CONF_BATTERY_SOC, default=defaults.get(CONF_BATTERY_SOC)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(
                CONF_OUTPUT_POWER, default=defaults.get(CONF_OUTPUT_POWER)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


class SolarFlowZeroExportConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle SolarFlow Nulleinspeisung config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None and async_target_conflict(
            self.hass, async_target_data(self.hass, user_input)
        ):
            return self.async_show_form(
                step_id="user",
                data_schema=_schema(user_input),
                errors={CONF_OUTPUT_LIMIT: "output_already_controlled"},
            )
        if user_input is not None:
            unique_id = "|".join(
                (
                    user_input[CONF_GRID_POWER],
                    user_input[CONF_OUTPUT_LIMIT],
                    user_input[CONF_BATTERY_SOC],
                )
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            # async_set_unique_id can yield: recheck before committing the entry.
            if async_target_conflict(self.hass, async_target_data(self.hass, user_input)):
                return self.async_show_form(
                    step_id="user",
                    data_schema=_schema(user_input),
                    errors={CONF_OUTPUT_LIMIT: "output_already_controlled"},
                )
            return self.async_create_entry(
                title=NAME, data=async_target_data(self.hass, user_input)
            )
        return self.async_show_form(step_id="user", data_schema=_schema())

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            data = async_target_data(self.hass, user_input)
            if async_target_conflict(self.hass, data, entry.entry_id):
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_schema(user_input),
                    errors={CONF_OUTPUT_LIMIT: "output_already_controlled"},
                )
            return self.async_update_reload_and_abort(entry, data_updates=data)
        defaults = {**entry.data, CONF_OUTPUT_LIMIT: async_target_entity(self.hass, entry.data)}
        if power_id := async_output_power_entity(self.hass, entry.data):
            defaults.setdefault(CONF_OUTPUT_POWER, power_id)
        return self.async_show_form(step_id="reconfigure", data_schema=_schema(defaults))
