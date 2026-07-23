"""Config flow for SolarFlow Nulleinspeisung."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_BATTERY_SOC, CONF_GRID_POWER, CONF_OUTPUT_LIMIT, DOMAIN, NAME


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_GRID_POWER, default=defaults.get(CONF_GRID_POWER)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_OUTPUT_LIMIT, default=defaults.get(CONF_OUTPUT_LIMIT)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="number")
        ),
        vol.Required(CONF_BATTERY_SOC, default=defaults.get(CONF_BATTERY_SOC)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
    })


class SolarFlowZeroExportConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle SolarFlow Nulleinspeisung config flow."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            unique_id = "|".join((user_input[CONF_GRID_POWER], user_input[CONF_OUTPUT_LIMIT], user_input[CONF_BATTERY_SOC]))
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema())

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(step_id="reconfigure", data_schema=_schema(dict(entry.data)))
