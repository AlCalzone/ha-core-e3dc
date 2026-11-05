"""Support for E3/DC sensors."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, override

from e3dc_ess_modbus import (
    E3dcPowerStation,
    EmergencyPowerStatus,
    InverterMode,
    PowerMeterType,
)
from e3dc_ess_modbus.inverter import Inverter

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    Platform,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import E3dcConfigEntry
from .entity import (
    E3dcEntity,
    E3dcEntityDescription,
    async_add_part_entities,
    present_inverters,
    present_meters,
)

PARALLEL_UPDATES = 0

# The manual marks DC tracker 3 as not used, but the E3/DC one reports it.
DC_TRACKERS = (1, 2, 3)
PHASES = ("l1", "l2", "l3")


def _meter_phase_value(
    number: int, phase: str
) -> Callable[[E3dcPowerStation], StateType]:
    """Read the power on ``phase`` of power meter slot ``number``."""

    def _value(device: E3dcPowerStation) -> StateType:
        value: StateType = getattr(
            device.power_meter_readings[number], f"power_{phase}"
        )
        return value

    return _value


def _enum_options(enum_type: type[IntEnum]) -> list[str]:
    """The sensor options a device enum maps to."""
    return [member.name.lower() for member in enum_type]


@dataclass(frozen=True, kw_only=True)
class E3dcSensorDescription(SensorEntityDescription, E3dcEntityDescription):
    """Describe an E3/DC sensor."""

    value_fn: Callable[[E3dcPowerStation], StateType | IntEnum]
    exists_fn: Callable[[E3dcPowerStation], bool] = lambda _: True


def _has_wallbox(device: E3dcPowerStation) -> bool:
    """Whether a wallbox is configured."""
    return bool(device.wallboxes.configured)


def _has_additional_feeder(device: E3dcPowerStation) -> bool:
    """Whether a power meter measures an additional feeder, e.g. a second PV inverter."""
    return any(
        meter.meter_type
        in (PowerMeterType.EXTERNAL_PRODUCTION, PowerMeterType.EXTERNAL_FARM)
        for meter in device.power_meter_readings.values()
    )


def _power(
    key: str,
    value_fn: Callable[[E3dcPowerStation], int | None],
    exists_fn: Callable[[E3dcPowerStation], bool] = lambda _: True,
) -> E3dcSensorDescription:
    """A power flow sensor, in watts."""
    return E3dcSensorDescription(
        key=key,
        translation_key=key,
        component="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=value_fn,
        exists_fn=exists_fn,
    )


STATION_SENSORS: tuple[E3dcSensorDescription, ...] = (
    _power("pv_power", lambda device: device.power.pv_power),
    _power(
        "battery_power",
        # E3/DC reports charging as positive power
        # Negate it because Home Assistant expects discharging as positive
        lambda device: (
            None if (power := device.power.battery_power) is None else -power
        ),
    ),
    _power("house_power", lambda device: device.power.house_power),
    _power("grid_power", lambda device: device.power.grid_power),
    _power(
        "additional_power",
        lambda device: device.power.additional_power,
        _has_additional_feeder,
    ),
    _power("wallbox_power", lambda device: device.power.wallbox_power, _has_wallbox),
    _power(
        "wallbox_solar_power",
        lambda device: device.power.wallbox_solar_power,
        _has_wallbox,
    ),
    E3dcSensorDescription(
        key="battery_soc",
        component="power",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.power.battery_soc,
    ),
    E3dcSensorDescription(
        key="autarky",
        translation_key="autarky",
        component="power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.power.autarky,
    ),
    E3dcSensorDescription(
        key="self_consumption",
        translation_key="self_consumption",
        component="power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.power.self_consumption,
    ),
    E3dcSensorDescription(
        key="emergency_power_status",
        translation_key="emergency_power_status",
        component="power",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(EmergencyPowerStatus),
        value_fn=lambda device: device.power.emergency_power_status,
        exists_fn=lambda device: (
            device.power.emergency_power_status
            is not EmergencyPowerStatus.NOT_SUPPORTED
        ),
    ),
    E3dcSensorDescription(
        key="max_charge_power",
        translation_key="max_charge_power",
        component="battery_limits",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: (
            limits.max_charge_power
            if (limits := device.battery_limits) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="max_discharge_power",
        translation_key="max_discharge_power",
        component="battery_limits",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: (
            limits.max_discharge_power
            if (limits := device.battery_limits) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="remaining_energy",
        component="battery_limits",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: (
            limits.remaining_energy
            if (limits := device.battery_limits) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="full_charge_energy",
        translation_key="full_charge_energy",
        component="battery_limits",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: (
            limits.full_charge_energy
            if (limits := device.battery_limits) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="sg_ready_status",
        translation_key="sg_ready_status",
        component="wide_power_meters",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: (
            meters.sg_ready_status
            if (meters := device.wide_power_meters) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="active_power_failsafe_timeout",
        translation_key="active_power_failsafe_timeout",
        component="grid_control",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: (
            grid.active_power_failsafe_timeout
            if (grid := device.grid_control) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="reactive_power_failsafe_timeout",
        translation_key="reactive_power_failsafe_timeout",
        component="grid_control",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: (
            grid.reactive_power_failsafe_timeout
            if (grid := device.grid_control) is not None
            else None
        ),
    ),
    E3dcSensorDescription(
        key="inverter_mode",
        translation_key="inverter_mode",
        component="inverter_mode_control",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(InverterMode),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: (
            mode.inverter_mode
            if (mode := device.inverter_mode_control) is not None
            else None
        ),
    ),
)


def _power_meter_sensors(number: int) -> list[E3dcSensorDescription]:
    """The sensors of power meter slot ``number``."""
    part = ("power_meter", number)
    sensors = [
        E3dcSensorDescription(
            key=f"power_meter_{number}_type",
            translation_key="power_meter_type",
            component="power_meters",
            part=part,
            device_class=SensorDeviceClass.ENUM,
            options=_enum_options(PowerMeterType),
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda device: device.power_meter_readings[number].meter_type,
        ),
        E3dcSensorDescription(
            key=f"power_meter_{number}_power",
            component="power_meters",
            part=part,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda device: _sum(
                (
                    (meter := device.power_meter_readings[number]).power_l1,
                    meter.power_l2,
                    meter.power_l3,
                )
            ),
        ),
    ]
    sensors.extend(
        E3dcSensorDescription(
            key=f"power_meter_{number}_power_{phase}",
            translation_key="power_phase",
            translation_placeholders={"phase": phase.upper()},
            component="power_meters",
            part=part,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            value_fn=_meter_phase_value(number, phase),
        )
        for phase in PHASES
    )
    return sensors


def _inverter_value(
    number: int, attribute: str
) -> Callable[[E3dcPowerStation], StateType]:
    """Read ``attribute`` of inverter slot ``number``."""

    def _value(device: E3dcPowerStation) -> StateType:
        if TYPE_CHECKING:
            assert device.inverters is not None
        inverter: Inverter = device.inverters[number]
        value: StateType = getattr(inverter, attribute)
        return value

    return _value


@dataclass(frozen=True, kw_only=True)
class _InverterMeasurement:
    """One measurement every inverter repeats, before it gets a number."""

    key: str
    translation_key: str
    translation_placeholders: Mapping[str, str] | None = None
    device_class: SensorDeviceClass
    native_unit_of_measurement: str
    suggested_display_precision: int | None = None
    enabled_default: bool = False


_INVERTER_MEASUREMENTS: tuple[_InverterMeasurement, ...] = (
    *(
        _InverterMeasurement(
            key=f"active_power_{phase}",
            translation_key="inverter_active_power",
            translation_placeholders={"phase": phase.upper()},
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            enabled_default=True,
        )
        for phase in PHASES
    ),
    *(
        _InverterMeasurement(
            key=f"apparent_power_{phase}",
            translation_key="inverter_apparent_power",
            translation_placeholders={"phase": phase.upper()},
            device_class=SensorDeviceClass.APPARENT_POWER,
            native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        )
        for phase in PHASES
    ),
    *(
        _InverterMeasurement(
            key=f"reactive_power_{phase}",
            translation_key="inverter_reactive_power",
            translation_placeholders={"phase": phase.upper()},
            device_class=SensorDeviceClass.REACTIVE_POWER,
            native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        )
        for phase in PHASES
    ),
    *(
        _InverterMeasurement(
            key=f"voltage_{phase}",
            translation_key="inverter_voltage",
            translation_placeholders={"phase": phase.upper()},
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            suggested_display_precision=1,
        )
        for phase in PHASES
    ),
    *(
        _InverterMeasurement(
            key=f"current_{phase}",
            translation_key="inverter_current",
            translation_placeholders={"phase": phase.upper()},
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            suggested_display_precision=2,
        )
        for phase in PHASES
    ),
    _InverterMeasurement(
        key="frequency",
        translation_key="inverter_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2,
    ),
    *(
        _InverterMeasurement(
            key=f"dc_power_{tracker}",
            translation_key="inverter_dc_power",
            translation_placeholders={"tracker": str(tracker)},
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            enabled_default=True,
        )
        for tracker in DC_TRACKERS
    ),
    *(
        _InverterMeasurement(
            key=f"dc_voltage_{tracker}",
            translation_key="inverter_dc_voltage",
            translation_placeholders={"tracker": str(tracker)},
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            suggested_display_precision=1,
        )
        for tracker in DC_TRACKERS
    ),
    *(
        _InverterMeasurement(
            key=f"dc_current_{tracker}",
            translation_key="inverter_dc_current",
            translation_placeholders={"tracker": str(tracker)},
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            suggested_display_precision=2,
        )
        for tracker in DC_TRACKERS
    ),
)


def _inverter_sensors(number: int) -> list[E3dcSensorDescription]:
    """The sensors of inverter slot ``number``."""
    return [
        E3dcSensorDescription(
            key=f"inverter_{number}_{measurement.key}",
            translation_key=measurement.translation_key,
            translation_placeholders=measurement.translation_placeholders,
            component="inverters",
            part=("inverter", number),
            device_class=measurement.device_class,
            native_unit_of_measurement=measurement.native_unit_of_measurement,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=measurement.suggested_display_precision,
            entity_registry_enabled_default=measurement.enabled_default,
            value_fn=_inverter_value(number, measurement.key),
        )
        for measurement in _INVERTER_MEASUREMENTS
    ]


def _sum(values: tuple[int | None, ...]) -> int | None:
    """The sum of the phase values, or ``None`` if any is unknown."""
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E3dcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the E3/DC sensor platform."""
    runtime_data = entry.runtime_data
    served = runtime_data.served_components
    async_add_entities(
        E3dcSensor(runtime_data, description)
        for description in STATION_SENSORS
        if description.component in served
        and description.exists_fn(runtime_data.device)
    )
    async_add_part_entities(
        entry,
        Platform.SENSOR,
        "power_meter",
        present_meters,
        async_add_entities,
        lambda number: (
            E3dcSensor(runtime_data, description)
            for description in _power_meter_sensors(number)
        ),
    )
    async_add_part_entities(
        entry,
        Platform.SENSOR,
        "inverter",
        present_inverters,
        async_add_entities,
        lambda number: (
            E3dcSensor(runtime_data, description)
            for description in _inverter_sensors(number)
        ),
    )


class E3dcSensor(E3dcEntity, SensorEntity):
    """Defines an E3/DC sensor."""

    entity_description: E3dcSensorDescription

    @property
    @override
    def native_value(self) -> StateType:
        value = self.entity_description.value_fn(self.coordinator.device)
        if isinstance(value, IntEnum):
            return value.name.lower()
        return value
