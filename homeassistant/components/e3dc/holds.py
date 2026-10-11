"""Keep remote control setpoints alive until they are stopped."""

import asyncio
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

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# The power station drops a setpoint 30 seconds after the last write
REWRITE_INTERVAL = timedelta(seconds=10)

BATTERY_POWER = "battery_power"
FEED_IN_LIMIT = "feed_in_limit"
ACTIVE_POWER_LIMIT = "active_power_limit"


def _grid(device: E3dcPowerStation) -> GridControl:
    assert device.grid_control is not None
    return device.grid_control


def _battery(device: E3dcPowerStation) -> BatteryControl:
    assert device.battery_control is not None
    return device.battery_control


@dataclass(frozen=True, kw_only=True)
class _Setpoint:
    """How to write one kind of setpoint, and how to hand control back."""

    write: Callable[[E3dcPowerStation, float], Awaitable[None]]
    release: Callable[[E3dcPowerStation], Awaitable[None]] | None
    inconsistent_key: str | None


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
    """A setpoint the integration keeps writing, or is still handing back."""

    value: float
    failing: bool = False
    """The last rewrite failed, so the device may have dropped the setpoint."""
    releasing: bool = False
    """Handing control back failed and is retried on every tick."""

    @property
    def confirmed(self) -> bool:
        """Whether the last write to the device succeeded."""
        return not self.failing and not self.releasing


class SetpointHolds:
    """The setpoints held for one power station.

    One lock serializes starting, stopping and rewriting, so a rewrite never
    writes a hold that was stopped or replaced while it waited.
    """

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
        self._lock = asyncio.Lock()
        self._closed = False
        self._holds: dict[str, Hold] = {}
        self._requested: dict[str, float] = {}
        self._unsub_interval: CALLBACK_TYPE | None = None
        self._tick: asyncio.Task[None] | None = None

    def get(self, key: str) -> Hold | None:
        """The hold of ``key``, if one is active or still being handed back."""
        return self._holds.get(key)

    def requested(self, key: str) -> float | None:
        """The last value requested for ``key``, held or not."""
        return self._requested.get(key)

    async def async_start(self, key: str, value: float) -> None:
        """Write ``value`` now and keep writing it until stopped.

        Raises ``HomeAssistantError`` when the first write fails.
        """
        self._requested[key] = value
        try:
            async with self._lock:
                if self._closed:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="not_loaded"
                    )
                try:
                    await SETPOINTS[key].write(self._device, value)
                except InconsistentWriteError as err:
                    self._drop(key)
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key=SETPOINTS[key].inconsistent_key
                        or "write_failed",
                    ) from err
                except ModbusError as err:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="write_failed"
                    ) from err
                self._holds[key] = Hold(value)
                self._ensure_interval()
        finally:
            self._notify()

    async def async_resume(self, key: str) -> None:
        """Hold the last value requested for ``key`` again."""
        if (value := self._requested.get(key)) is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="no_setpoint"
            )
        await self.async_start(key, value)

    async def async_stop(self, key: str) -> None:
        """Stop holding ``key`` and hand control back to the power station.

        If handing back fails, the hold stays and every tick retries it.
        """
        try:
            async with self._lock:
                await self._async_release(key)
        finally:
            self._notify()

    async def async_stop_all(self) -> None:
        """Hand every setpoint back and accept no new ones, for unload or shutdown."""
        async with self._lock:
            self._closed = True
            if self._unsub_interval is not None:
                self._unsub_interval()
                self._unsub_interval = None
            for key in list(self._holds):
                try:
                    await self._async_release(key)
                except HomeAssistantError as err:
                    _LOGGER.warning("Could not release %s: %s", key, err.__cause__)
        if self._tick is not None:
            await self._tick
        self._notify()

    async def _async_release(self, key: str) -> None:
        """Hand ``key`` back; call only while holding the lock."""
        if (hold := self._holds.get(key)) is None:
            return
        if (release := SETPOINTS[key].release) is not None:
            try:
                await release(self._device)
            except (ModbusError, InconsistentWriteError) as err:
                hold.releasing = True
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="write_failed"
                ) from err
        self._drop(key)

    @callback
    def _drop(self, key: str) -> None:
        self._holds.pop(key, None)
        if not self._holds and self._unsub_interval is not None:
            self._unsub_interval()
            self._unsub_interval = None

    @callback
    def _ensure_interval(self) -> None:
        if self._unsub_interval is None:
            self._unsub_interval = async_track_time_interval(
                self._hass, self._async_on_interval, REWRITE_INTERVAL
            )

    @callback
    def _async_on_interval(self, now: datetime) -> None:
        """Start a rewrite, unless the last one is still running."""
        if self._tick is not None and not self._tick.done():
            return
        self._tick = self._entry.async_create_background_task(
            self._hass, self._async_rewrite(), "e3dc setpoint rewrite"
        )

    async def _async_rewrite(self) -> None:
        """Write every held setpoint again, and retry failed releases."""
        changed = False
        async with self._lock:
            if self._closed:
                return
            for key, hold in list(self._holds.items()):
                if hold.releasing:
                    try:
                        await self._async_release(key)
                    except HomeAssistantError:
                        continue
                    _LOGGER.info("Released %s after an earlier failure", key)
                    changed = True
                    continue
                try:
                    await SETPOINTS[key].write(self._device, hold.value)
                except InconsistentWriteError as err:
                    _LOGGER.warning(
                        "Stopped holding %s after a half-written rewrite: %s", key, err
                    )
                    self._drop(key)
                    changed = True
                    continue
                except ModbusError as err:
                    if not hold.failing:
                        hold.failing = True
                        changed = True
                        _LOGGER.warning("Could not rewrite %s: %s", key, err)
                    continue
                if hold.failing:
                    hold.failing = False
                    changed = True
                    _LOGGER.info("Rewriting %s works again", key)
        if changed:
            self._notify()
