"""Keep remote control setpoints alive until they are stopped or expire."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from e3dc_ess_modbus import (
    BatteryControl,
    E3dcPowerStation,
    GridControl,
    InconsistentWriteError,
)
from modbus_connection import ModbusError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# The power station drops a setpoint 30 seconds after the last write
REWRITE_INTERVAL = timedelta(seconds=10)

BATTERY_POWER = "battery_power"
FEED_IN_LIMIT = "feed_in_limit"
ACTIVE_POWER_LIMIT = "active_power_limit"


@dataclass(frozen=True, kw_only=True)
class _Setpoint:
    """How to write one kind of setpoint, and how to hand control back."""

    write: Callable[[E3dcPowerStation, float], Awaitable[None]]
    release: Callable[[E3dcPowerStation], Awaitable[None]] | None
    inconsistent_key: str | None


def _grid(device: E3dcPowerStation) -> GridControl:
    assert device.grid_control is not None
    return device.grid_control


def _battery(device: E3dcPowerStation) -> BatteryControl:
    assert device.battery_control is not None
    return device.battery_control


SETPOINTS: dict[str, _Setpoint] = {
    BATTERY_POWER: _Setpoint(
        write=lambda device, value: _battery(device).async_write_battery_power(
            int(value)
        ),
        release=lambda device: _battery(device).async_stop_remote_control(),
        inconsistent_key="battery_power_inconsistent",
    ),
    FEED_IN_LIMIT: _Setpoint(
        write=lambda device, value: _grid(device).async_write_feed_in_limit(int(value)),
        # The station falls back to its own limit 30 seconds after the last write
        release=None,
        inconsistent_key="feed_in_limit_inconsistent",
    ),
    ACTIVE_POWER_LIMIT: _Setpoint(
        write=lambda device, value: _grid(device).async_write_active_power_limit(value),
        # A failsafe timeout of 0 keeps the limit forever, so lift it explicitly
        release=lambda device: _grid(device).async_write_active_power_limit(100),
        inconsistent_key=None,
    ),
}


@dataclass
class Hold:
    """A setpoint the integration keeps writing."""

    value: float
    until: datetime | None
    failing: bool = False


class SetpointHolds:
    """The setpoints held for one power station."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: E3dcPowerStation,
        notify: Callable[[], None],
    ) -> None:
        """Initialize the holds."""
        self._hass = hass
        self._entry = entry
        self._device = device
        self._notify = notify
        self._holds: dict[str, Hold] = {}
        self._unsub_interval: CALLBACK_TYPE | None = None

    def get(self, key: str) -> Hold | None:
        """The hold of ``key``, if one is active."""
        return self._holds.get(key)

    async def async_start(
        self, key: str, value: float, duration: timedelta | None
    ) -> None:
        """Write ``value`` now and keep writing it until stopped or ``duration`` ends.

        Raises ``HomeAssistantError`` when the first write fails.
        """
        await self._async_write(key, value)
        until = dt_util.utcnow() + duration if duration is not None else None
        self._holds[key] = Hold(value, until)
        self._ensure_interval()
        self._notify()

    async def async_stop(self, key: str) -> None:
        """Stop holding ``key`` and hand control back to the power station."""
        self._holds.pop(key, None)
        self._stop_interval_if_idle()
        self._notify()
        if (release := SETPOINTS[key].release) is not None:
            try:
                await release(self._device)
            except (ModbusError, InconsistentWriteError) as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="write_failed"
                ) from err

    async def async_stop_all(self) -> None:
        """Hand every held setpoint back, for an unloading entry."""
        for key in list(self._holds):
            try:
                await self.async_stop(key)
            except HomeAssistantError as err:
                _LOGGER.warning("Could not release %s on unload: %s", key, err)

    async def _async_write(self, key: str, value: float) -> None:
        """Write a setpoint once, translating a failure."""
        setpoint = SETPOINTS[key]
        try:
            await setpoint.write(self._device, value)
        except InconsistentWriteError as err:
            self._holds.pop(key, None)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=setpoint.inconsistent_key or "write_failed",
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="write_failed"
            ) from err

    @callback
    def _ensure_interval(self) -> None:
        if self._unsub_interval is None:
            self._unsub_interval = async_track_time_interval(
                self._hass, self._async_rewrite, REWRITE_INTERVAL
            )

    @callback
    def _stop_interval_if_idle(self) -> None:
        if not self._holds and self._unsub_interval is not None:
            self._unsub_interval()
            self._unsub_interval = None

    async def _async_rewrite(self, now: datetime) -> None:
        """Write every held setpoint again, ending those whose time is up."""
        for key, hold in list(self._holds.items()):
            if hold.until is not None and now >= hold.until:
                try:
                    await self.async_stop(key)
                except HomeAssistantError as err:
                    _LOGGER.warning("Could not release %s: %s", key, err)
                continue
            try:
                await self._async_write(key, hold.value)
            except HomeAssistantError as err:
                if key not in self._holds:
                    _LOGGER.warning("Stopped holding %s: %s", key, err.__cause__)
                    self._stop_interval_if_idle()
                    self._notify()
                elif not hold.failing:
                    hold.failing = True
                    _LOGGER.warning("Could not rewrite %s: %s", key, err.__cause__)
                continue
            if hold.failing:
                hold.failing = False
                _LOGGER.info("Rewriting %s works again", key)
