"""Support for E3/DC setpoints as numbers."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import E3dcConfigEntry, E3dcRuntimeData
from .entity import E3dcEntity, E3dcEntityDescription
from .holds import ACTIVE_POWER_LIMIT, BATTERY_POWER, FEED_IN_LIMIT

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class E3dcSetpointNumberDescription(NumberEntityDescription, E3dcEntityDescription):
    """Describe a setpoint the integration holds once it is set."""

    hold_key: str


SETPOINT_NUMBERS: tuple[E3dcSetpointNumberDescription, ...] = (
    E3dcSetpointNumberDescription(
        key="battery_power_setpoint",
        translation_key="battery_power_setpoint",
        component="battery_control",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=-50000,
        native_max_value=50000,
        native_step=100,
        mode=NumberMode.BOX,
        hold_key=BATTERY_POWER,
    ),
    E3dcSetpointNumberDescription(
        key="feed_in_limit_setpoint",
        translation_key="feed_in_limit_setpoint",
        component="grid_control",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=100000,
        native_step=100,
        mode=NumberMode.BOX,
        hold_key=FEED_IN_LIMIT,
    ),
    E3dcSetpointNumberDescription(
        key="active_power_limit_setpoint",
        translation_key="active_power_limit_setpoint",
        component="grid_control",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        mode=NumberMode.BOX,
        hold_key=ACTIVE_POWER_LIMIT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E3dcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the E3/DC number platform."""
    runtime_data = entry.runtime_data
    served = runtime_data.served_components
    async_add_entities(
        E3dcSetpointNumber(runtime_data, description)
        for description in SETPOINT_NUMBERS
        if description.component in served
    )


class E3dcSetpointNumber(E3dcEntity, NumberEntity):
    """A setpoint: setting it writes it and starts holding it."""

    entity_description: E3dcSetpointNumberDescription

    def __init__(
        self,
        runtime_data: E3dcRuntimeData,
        entity_description: E3dcSetpointNumberDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(runtime_data, entity_description)
        self._holds = runtime_data.holds

    @property
    @override
    def native_value(self) -> float | None:
        """The last value set, held or not."""
        return self._holds.requested(self.entity_description.hold_key)

    @override
    async def async_set_native_value(self, value: float) -> None:
        await self._holds.async_start(self.entity_description.hold_key, value)
