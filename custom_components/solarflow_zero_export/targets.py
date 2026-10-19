"""Stable target identity and event-loop-local exclusive write ownership."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_OUTPUT_LIMIT, CONF_OUTPUT_TARGET_ID, DOMAIN

LEASES = f"{DOMAIN}_output_leases"


@callback
def async_target_data(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Any]:
    """Capture identity from the freshly selected entity, never from submitted metadata."""
    target = er.async_get(hass).async_get(data[CONF_OUTPUT_LIMIT])
    return {**data, CONF_OUTPUT_TARGET_ID: target.id if target else None}


@callback
def async_target_entity(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    registry = er.async_get(hass)
    target = (
        registry.async_get(data[CONF_OUTPUT_TARGET_ID]) if data.get(CONF_OUTPUT_TARGET_ID) else None
    )
    return target.entity_id if target else data[CONF_OUTPUT_LIMIT]


@callback
def async_target_key(hass: HomeAssistant, data: Mapping[str, Any]) -> str:
    target = er.async_get(hass).async_get(async_target_entity(hass, data))
    return f"registry:{target.id}" if target else f"entity:{data[CONF_OUTPUT_LIMIT]}"


@callback
def async_target_conflict(
    hass: HomeAssistant, data: Mapping[str, Any], exclude: str | None = None
) -> bool:
    key = async_target_key(hass, data)
    return any(
        entry.entry_id != exclude and async_target_key(hass, entry.data) == key
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


@callback
def async_target_keys(hass: HomeAssistant, data: Mapping[str, Any]) -> frozenset[str]:
    # Also reserve the service entity ID: a previously unregistered entity may
    # acquire a registry ID while an already issued command is still in flight.
    return frozenset((async_target_key(hass, data), f"entity:{async_target_entity(hass, data)}"))


@callback
def async_claim(hass: HomeAssistant, keys: frozenset[str], owner: object) -> bool:
    """Check all aliases atomically before claiming any of them."""
    leases = hass.data.setdefault(LEASES, {})
    if any(key in leases and leases[key] is not owner for key in keys):
        return False
    for key in keys:
        leases[key] = owner
    return True


@callback
def async_release(hass: HomeAssistant, keys: frozenset[str] | None, owner: object) -> None:
    leases = hass.data.get(LEASES, {})
    for key in keys or ():
        if leases.get(key) is owner:
            del leases[key]
