"""Services for the E3/DC integration."""

import probatio

from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import (
    async_get_config_entry,
    async_register_admin_service,
)

from .const import DOMAIN
from .coordinator import E3dcConfigEntry
from .holds import ACTIVE_POWER_LIMIT, BATTERY_POWER, FEED_IN_LIMIT

SERVICE_CLEAR_GRID_LIMITS = "clear_grid_limits"
SERVICE_SET_ACTIVE_POWER_LIMIT = "set_active_power_limit"
SERVICE_SET_BATTERY_POWER = "set_battery_power"
SERVICE_SET_FEED_IN_LIMIT = "set_feed_in_limit"
SERVICE_STOP_BATTERY_CONTROL = "stop_battery_control"

ATTR_DURATION = "duration"
ATTR_LIMIT = "limit"
ATTR_POWER = "power"

_ENTRY_SCHEMA = probatio.Schema({probatio.Required(ATTR_CONFIG_ENTRY_ID): str})
_DURATION = {
    probatio.Optional(ATTR_DURATION): probatio.All(
        cv.time_period, cv.positive_timedelta
    )
}

# The selectors in services.yaml bound only the UI. This bounds scripted calls.
SET_BATTERY_POWER_SCHEMA = _ENTRY_SCHEMA.extend(
    {
        probatio.Required(ATTR_POWER): probatio.All(
            probatio.Coerce(int), probatio.Range(min=-100000, max=100000)
        ),
        **_DURATION,
    }
)

SET_FEED_IN_LIMIT_SCHEMA = _ENTRY_SCHEMA.extend(
    {
        probatio.Required(ATTR_POWER): probatio.All(
            probatio.Coerce(int), probatio.Range(min=0, max=100000)
        ),
        **_DURATION,
    }
)

SET_ACTIVE_POWER_LIMIT_SCHEMA = _ENTRY_SCHEMA.extend(
    {
        probatio.Required(ATTR_LIMIT): probatio.All(
            probatio.Coerce(float), probatio.Percentage()
        ),
        **_DURATION,
    }
)


def _get_entry(
    hass: HomeAssistant, call: ServiceCall, component: str
) -> E3dcConfigEntry:
    """Return a loaded entry whose power station serves the needed registers."""
    entry: E3dcConfigEntry = async_get_config_entry(
        hass, DOMAIN, call.data[ATTR_CONFIG_ENTRY_ID]
    )
    if component not in entry.runtime_data.served_components:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unsupported_action",
            translation_placeholders={"title": entry.title},
        )
    return entry


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the E3/DC services."""

    async def _handle_set_battery_power(call: ServiceCall) -> None:
        entry = _get_entry(hass, call, "battery_control")
        await entry.runtime_data.holds.async_start(
            BATTERY_POWER, call.data[ATTR_POWER], call.data.get(ATTR_DURATION)
        )

    async def _handle_stop_battery_control(call: ServiceCall) -> None:
        entry = _get_entry(hass, call, "battery_control")
        await entry.runtime_data.holds.async_stop(BATTERY_POWER)

    async def _handle_set_feed_in_limit(call: ServiceCall) -> None:
        entry = _get_entry(hass, call, "grid_control")
        await entry.runtime_data.holds.async_start(
            FEED_IN_LIMIT, call.data[ATTR_POWER], call.data.get(ATTR_DURATION)
        )

    async def _handle_set_active_power_limit(call: ServiceCall) -> None:
        entry = _get_entry(hass, call, "grid_control")
        await entry.runtime_data.holds.async_start(
            ACTIVE_POWER_LIMIT, call.data[ATTR_LIMIT], call.data.get(ATTR_DURATION)
        )

    async def _handle_clear_grid_limits(call: ServiceCall) -> None:
        entry = _get_entry(hass, call, "grid_control")
        holds = entry.runtime_data.holds
        await holds.async_stop(FEED_IN_LIMIT)
        await holds.async_stop(ACTIVE_POWER_LIMIT)

    for service, handler, schema in (
        (
            SERVICE_SET_BATTERY_POWER,
            _handle_set_battery_power,
            SET_BATTERY_POWER_SCHEMA,
        ),
        (SERVICE_STOP_BATTERY_CONTROL, _handle_stop_battery_control, _ENTRY_SCHEMA),
        (
            SERVICE_SET_FEED_IN_LIMIT,
            _handle_set_feed_in_limit,
            SET_FEED_IN_LIMIT_SCHEMA,
        ),
        (
            SERVICE_SET_ACTIVE_POWER_LIMIT,
            _handle_set_active_power_limit,
            SET_ACTIVE_POWER_LIMIT_SCHEMA,
        ),
        (SERVICE_CLEAR_GRID_LIMITS, _handle_clear_grid_limits, _ENTRY_SCHEMA),
    ):
        async_register_admin_service(hass, DOMAIN, service, handler, schema=schema)
