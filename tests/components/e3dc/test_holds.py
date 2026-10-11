"""Tests for the setpoints the E3/DC integration holds."""

import asyncio
from unittest.mock import AsyncMock

from e3dc_ess_modbus.model import register
from freezegun.api import FrozenDateTimeFactory
from modbus_connection import IllegalFunctionError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest

from homeassistant.components.e3dc.holds import REWRITE_INTERVAL
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_HOMEASSISTANT_STOP,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.common import MockConfigEntry, async_fire_time_changed

BATTERY_POWER = "number.s10_x_battery_power_setpoint"
BATTERY_CONTROL = "switch.s10_x_battery_power_control"
FEED_IN_LIMIT = "number.s10_x_feed_in_limit"
FEED_IN_CONTROL = "switch.s10_x_feed_in_limit_control"
ACTIVE_POWER_LIMIT = "number.s10_x_active_power_limit"
ACTIVE_POWER_CONTROL = "switch.s10_x_active_power_limit_control"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the platforms with setpoint entities."""
    return [Platform.NUMBER, Platform.SWITCH]


@pytest.fixture
def writes(mock_unit: MockModbusUnit) -> list[WriteEvent]:
    """Every write the power station receives."""
    events: list[WriteEvent] = []
    mock_unit.on_write(events.append)
    return events


def _writes_to(writes: list[WriteEvent], index: int) -> list[list[int]]:
    return [write.values for write in writes if write.address == register(index)]


async def _set(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def _switch(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(REWRITE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


def _refuse_fc16(monkeypatch: pytest.MonkeyPatch, unit: MockModbusUnit) -> None:
    monkeypatch.setattr(
        unit, "write_registers", AsyncMock(side_effect=IllegalFunctionError())
    )


@pytest.mark.usefixtures("init_integration")
async def test_battery_power_is_held_until_switched_off(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    writes: list[WriteEvent],
) -> None:
    """Test setting the battery power holds it until the control switch is off."""
    assert hass.states.get(BATTERY_POWER).state == STATE_UNKNOWN
    assert hass.states.get(BATTERY_CONTROL).state == STATE_OFF

    await _set(hass, BATTERY_POWER, 3000)

    assert hass.states.get(BATTERY_POWER).state == "3000.0"
    assert hass.states.get(BATTERY_CONTROL).state == STATE_ON

    await _tick(hass, freezer)
    await _tick(hass, freezer)
    assert _writes_to(writes, 40197) == [[3000, 0]] * 3

    await _switch(hass, BATTERY_CONTROL, False)
    await _tick(hass, freezer)

    assert _writes_to(writes, 40197) == [[3000, 0]] * 3
    assert _writes_to(writes, 40199) == [[1]]
    assert hass.states.get(BATTERY_CONTROL).state == STATE_OFF
    assert hass.states.get(BATTERY_POWER).state == "3000.0"

    await _switch(hass, BATTERY_CONTROL, True)

    assert _writes_to(writes, 40197)[-1] == [3000, 0]
    assert hass.states.get(BATTERY_CONTROL).state == STATE_ON


@pytest.mark.usefixtures("init_integration")
async def test_switching_on_without_a_value_raises(hass: HomeAssistant) -> None:
    """Test a control switch needs a value to hold."""
    with pytest.raises(HomeAssistantError) as err:
        await _switch(hass, FEED_IN_CONTROL, True)

    assert err.value.translation_key == "no_setpoint"


@pytest.mark.usefixtures("init_integration")
async def test_grid_limits_are_handed_back(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    writes: list[WriteEvent],
) -> None:
    """Test switching off lifts the active power limit and drops the feed-in limit."""
    await _set(hass, FEED_IN_LIMIT, 4000)
    await _set(hass, ACTIVE_POWER_LIMIT, 70)

    await _switch(hass, FEED_IN_CONTROL, False)
    await _switch(hass, ACTIVE_POWER_CONTROL, False)
    await _tick(hass, freezer)

    assert _writes_to(writes, 40186) == [[4000, 0]]
    assert _writes_to(writes, 40192) == [[700], [1000]]
    assert hass.states.get(FEED_IN_CONTROL).state == STATE_OFF
    assert hass.states.get(ACTIVE_POWER_CONTROL).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_a_failing_rewrite_makes_the_state_unknown(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    mock_unit: MockModbusUnit,
    writes: list[WriteEvent],
) -> None:
    """Test a failing rewrite is logged once, shows unknown, and recovers."""
    await _set(hass, BATTERY_POWER, 3000)
    mock_unit.fail_write(register(40197), ModbusTimeoutError())

    await _tick(hass, freezer)
    await _tick(hass, freezer)
    assert caplog.text.count("Could not rewrite battery_power") == 1
    assert hass.states.get(BATTERY_CONTROL).state == STATE_UNKNOWN

    mock_unit.fail_write(register(40197), None)
    await _tick(hass, freezer)

    assert "Rewriting battery_power works again" in caplog.text
    assert hass.states.get(BATTERY_CONTROL).state == STATE_ON
    assert _writes_to(writes, 40197)[-1] == [3000, 0]


@pytest.mark.usefixtures("init_integration")
async def test_a_failed_release_is_retried(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    mock_unit: MockModbusUnit,
    writes: list[WriteEvent],
) -> None:
    """Test a hand-back that fails shows unknown and is retried on every tick."""
    await _set(hass, BATTERY_POWER, 3000)
    mock_unit.fail_write(register(40199), ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _switch(hass, BATTERY_CONTROL, False)
    assert err.value.translation_key == "write_failed"
    assert hass.states.get(BATTERY_CONTROL).state == STATE_UNKNOWN

    await _tick(hass, freezer)
    assert hass.states.get(BATTERY_CONTROL).state == STATE_UNKNOWN

    mock_unit.fail_write(register(40199), None)
    await _tick(hass, freezer)

    assert "Released battery_power after an earlier failure" in caplog.text
    assert hass.states.get(BATTERY_CONTROL).state == STATE_OFF
    assert _writes_to(writes, 40197) == [[3000, 0]]


@pytest.mark.parametrize(
    ("entity_id", "value", "index", "translation_key"),
    [
        pytest.param(
            BATTERY_POWER, 3000, 40198, "battery_power_inconsistent", id="battery"
        ),
        pytest.param(
            FEED_IN_LIMIT, 70000, 40187, "feed_in_limit_inconsistent", id="feed_in"
        ),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_a_half_written_setpoint_says_what_was_attempted(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    entity_id: str,
    value: int,
    index: int,
    translation_key: str,
) -> None:
    """Test a half-written pair raises an error naming what was put back."""
    _refuse_fc16(monkeypatch, mock_unit)
    mock_unit.fail_write(register(index), ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _set(hass, entity_id, value)

    assert err.value.translation_key == translation_key


@pytest.mark.usefixtures("init_integration")
async def test_a_half_written_rewrite_ends_the_hold(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    mock_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a half-written rewrite ends the hold, since the library ended it too."""
    await _set(hass, BATTERY_POWER, 3000)
    _refuse_fc16(monkeypatch, mock_unit)
    mock_unit.fail_write(register(40198), ModbusTimeoutError())

    await _tick(hass, freezer)

    assert "Stopped holding battery_power after a half-written rewrite" in caplog.text
    assert hass.states.get(BATTERY_CONTROL).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_a_failed_first_write_raises(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a setpoint the power station refuses raises a translated error."""
    mock_unit.fail_write(register(40192), ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _set(hass, ACTIVE_POWER_LIMIT, 50)

    assert err.value.translation_key == "write_failed"
    assert hass.states.get(ACTIVE_POWER_CONTROL).state == STATE_OFF


async def test_unloading_hands_the_battery_back(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    writes: list[WriteEvent],
) -> None:
    """Test unloading the entry ends remote battery control."""
    await _set(hass, BATTERY_POWER, 3000)

    await hass.config_entries.async_unload(init_integration.entry_id)

    assert _writes_to(writes, 40199) == [[1]]


async def test_a_failing_release_on_unload_is_logged(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a release that fails while unloading doesn't stop the unload."""
    await _set(hass, BATTERY_POWER, 3000)
    mock_unit.fail_write(register(40199), ModbusTimeoutError())

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert "Could not release battery_power" in caplog.text


@pytest.mark.usefixtures("init_integration")
async def test_stopping_home_assistant_hands_setpoints_back(
    hass: HomeAssistant, writes: list[WriteEvent]
) -> None:
    """Test the holds are released when Home Assistant stops."""
    await _set(hass, ACTIVE_POWER_LIMIT, 60)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    assert _writes_to(writes, 40192) == [[600], [1000]]


@pytest.mark.usefixtures("init_integration")
async def test_a_stop_during_a_rewrite_is_not_undone(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    writes: list[WriteEvent],
) -> None:
    """Test a rewrite in progress doesn't write a hold that was stopped meanwhile."""
    await _set(hass, FEED_IN_LIMIT, 4000)
    await _set(hass, BATTERY_POWER, 3000)
    write_registers = mock_unit.write_registers
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_feed_in(address: int, values: list[int]) -> None:
        if address == register(40186):
            started.set()
            await release.wait()
        await write_registers(address, values)

    monkeypatch.setattr(mock_unit, "write_registers", slow_feed_in)
    freezer.tick(REWRITE_INTERVAL)
    async_fire_time_changed(hass)
    await started.wait()
    stop = hass.async_create_task(_switch(hass, BATTERY_CONTROL, False))
    await asyncio.sleep(0)
    release.set()
    await stop
    await hass.async_block_till_done(wait_background_tasks=True)

    battery_writes = [
        w.address for w in writes if w.address in (register(40197), register(40199))
    ]
    assert battery_writes[-1] == register(40199)
    assert hass.states.get(BATTERY_CONTROL).state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_a_replacement_during_a_rewrite_wins(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    writes: list[WriteEvent],
) -> None:
    """Test a value set during a rewrite is the one written last and held."""
    await _set(hass, BATTERY_POWER, 3000)
    write_registers = mock_unit.write_registers
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def slow_first(address: int, values: list[int]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await release.wait()
        await write_registers(address, values)

    monkeypatch.setattr(mock_unit, "write_registers", slow_first)
    freezer.tick(REWRITE_INTERVAL)
    async_fire_time_changed(hass)
    await started.wait()
    replace = hass.async_create_task(_set(hass, BATTERY_POWER, -2000))
    await asyncio.sleep(0)
    release.set()
    await replace
    await _tick(hass, freezer)

    assert _writes_to(writes, 40197)[-2:] == [[0xF830, 0xFFFF]] * 2
    assert hass.states.get(BATTERY_POWER).state == "-2000.0"


async def test_a_setpoint_during_unload_is_refused(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    writes: list[WriteEvent],
) -> None:
    """Test no hold starts once the entry has handed its setpoints back."""
    holds = init_integration.runtime_data.holds
    await holds.async_stop_all()

    with pytest.raises(HomeAssistantError) as err:
        await holds.async_start("battery_power", 3000)
    await _tick(hass, freezer)

    assert err.value.translation_key == "not_loaded"
    assert _writes_to(writes, 40197) == []
