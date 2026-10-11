"""Tests for the setpoints the E3/DC integration holds."""

from datetime import timedelta
from unittest.mock import AsyncMock

from e3dc_ess_modbus.model import register
from freezegun.api import FrozenDateTimeFactory
from modbus_connection import IllegalFunctionError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest

from homeassistant.components.e3dc.const import DOMAIN
from homeassistant.components.e3dc.holds import REWRITE_INTERVAL
from homeassistant.components.e3dc.services import (
    SERVICE_CLEAR_GRID_LIMITS,
    SERVICE_SET_ACTIVE_POWER_LIMIT,
    SERVICE_SET_BATTERY_POWER,
    SERVICE_SET_FEED_IN_LIMIT,
    SERVICE_STOP_BATTERY_CONTROL,
)
from homeassistant.const import ATTR_CONFIG_ENTRY_ID, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from tests.common import MockConfigEntry, async_fire_time_changed

BATTERY_SETPOINT = "sensor.s10_x_battery_power_setpoint"
REMOTE_CONTROL = "binary_sensor.s10_x_remote_battery_control"


@pytest.fixture
def writes(mock_unit: MockModbusUnit) -> list[WriteEvent]:
    """Every write the power station receives."""
    events: list[WriteEvent] = []
    mock_unit.on_write(events.append)
    return events


def _writes_to(writes: list[WriteEvent], index: int) -> list[list[int]]:
    return [write.values for write in writes if write.address == register(index)]


async def _call(
    hass: HomeAssistant, entry: MockConfigEntry, service: str, **data: object
) -> None:
    await hass.services.async_call(
        DOMAIN,
        service,
        {ATTR_CONFIG_ENTRY_ID: entry.entry_id, **data},
        blocking=True,
    )


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(REWRITE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_battery_power_is_held_until_stopped(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    writes: list[WriteEvent],
) -> None:
    """Test the battery power is rewritten until the hold is stopped."""
    await _call(hass, init_integration, SERVICE_SET_BATTERY_POWER, power=3000)

    assert hass.states.get(BATTERY_SETPOINT).state == "3000"
    assert hass.states.get(REMOTE_CONTROL).state == STATE_ON

    await _tick(hass, freezer)
    await _tick(hass, freezer)
    assert _writes_to(writes, 40197) == [[3000, 0]] * 3

    await _call(hass, init_integration, SERVICE_STOP_BATTERY_CONTROL)
    await _tick(hass, freezer)

    assert _writes_to(writes, 40197) == [[3000, 0]] * 3
    assert _writes_to(writes, 40199) == [[1]]
    assert hass.states.get(BATTERY_SETPOINT).state == STATE_UNKNOWN
    assert hass.states.get(REMOTE_CONTROL).state == STATE_OFF


async def test_a_hold_with_a_duration_ends_on_its_own(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    writes: list[WriteEvent],
) -> None:
    """Test a hold with a duration hands control back when it runs out."""
    await _call(
        hass,
        init_integration,
        SERVICE_SET_BATTERY_POWER,
        power=-2000,
        duration={"seconds": 15},
    )
    await _tick(hass, freezer)
    await _tick(hass, freezer)

    assert len(_writes_to(writes, 40197)) == 2
    assert _writes_to(writes, 40199) == [[1]]
    assert hass.states.get(REMOTE_CONTROL).state == STATE_OFF


async def test_clearing_grid_limits_lifts_the_active_power_limit(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    writes: list[WriteEvent],
) -> None:
    """Test clearing the grid limits stops both holds and lifts the cap."""
    await _call(hass, init_integration, SERVICE_SET_FEED_IN_LIMIT, power=4000)
    await _call(hass, init_integration, SERVICE_SET_ACTIVE_POWER_LIMIT, limit=70)
    assert hass.states.get("sensor.s10_x_feed_in_limit_setpoint").state == "4000"
    assert hass.states.get("sensor.s10_x_active_power_limit_setpoint").state == "70.0"

    await _call(hass, init_integration, SERVICE_CLEAR_GRID_LIMITS)
    await _tick(hass, freezer)

    assert _writes_to(writes, 40186) == [[4000, 0]]
    assert _writes_to(writes, 40192) == [[700], [1000]]
    assert hass.states.get("sensor.s10_x_feed_in_limit_setpoint").state == STATE_UNKNOWN


async def test_a_failing_rewrite_keeps_the_hold(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    writes: list[WriteEvent],
) -> None:
    """Test a rewrite that fails is logged once and retried."""
    await _call(hass, init_integration, SERVICE_SET_BATTERY_POWER, power=3000)
    mock_unit.fail_write(register(40197), ModbusTimeoutError())

    await _tick(hass, freezer)
    await _tick(hass, freezer)
    assert caplog.text.count("Could not rewrite battery_power") == 1
    assert hass.states.get(REMOTE_CONTROL).state == STATE_ON

    mock_unit.fail_write(register(40197), None)
    await _tick(hass, freezer)

    assert "Rewriting battery_power works again" in caplog.text
    assert _writes_to(writes, 40197)[-1] == [3000, 0]


@pytest.mark.parametrize(
    ("service", "data", "index", "translation_key"),
    [
        pytest.param(
            SERVICE_SET_BATTERY_POWER,
            {"power": 3000},
            40198,
            "battery_power_inconsistent",
            id="battery",
        ),
        pytest.param(
            SERVICE_SET_FEED_IN_LIMIT,
            {"power": 70000},
            40187,
            "feed_in_limit_inconsistent",
            id="feed_in",
        ),
    ],
)
async def test_a_half_written_setpoint_says_what_was_restored(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    data: dict[str, int],
    index: int,
    translation_key: str,
) -> None:
    """Test a half-written pair raises an error naming the state left behind."""
    monkeypatch.setattr(
        mock_unit, "write_registers", AsyncMock(side_effect=IllegalFunctionError())
    )
    mock_unit.fail_write(register(index), ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, init_integration, service, **data)

    assert err.value.translation_key == translation_key
    assert hass.states.get(REMOTE_CONTROL).state == STATE_OFF


async def test_unloading_hands_the_battery_back(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    writes: list[WriteEvent],
) -> None:
    """Test unloading the entry ends remote battery control."""
    await _call(hass, init_integration, SERVICE_SET_BATTERY_POWER, power=3000)

    await hass.config_entries.async_unload(init_integration.entry_id)

    assert _writes_to(writes, 40199) == [[1]]


async def test_a_failing_release_on_unload_is_logged(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a release that fails while unloading doesn't stop the unload."""
    await _call(hass, init_integration, SERVICE_SET_BATTERY_POWER, power=3000)
    mock_unit.fail_write(register(40199), ModbusTimeoutError())

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert "Could not release battery_power on unload" in caplog.text


async def test_a_failing_stop_raises(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a stop the power station refuses raises a translated error."""
    mock_unit.fail_write(register(40199), ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, init_integration, SERVICE_STOP_BATTERY_CONTROL)

    assert err.value.translation_key == "write_failed"


async def test_a_failing_release_after_a_duration_is_logged(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a release that fails when a duration ends is logged."""
    await _call(
        hass,
        init_integration,
        SERVICE_SET_BATTERY_POWER,
        power=-2000,
        duration=timedelta(seconds=5),
    )
    mock_unit.fail_write(register(40199), ModbusTimeoutError())
    await _tick(hass, freezer)

    assert "Could not release battery_power" in caplog.text


async def test_a_rewrite_left_half_written_stops_the_hold(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a half-written rewrite ends the hold, since the library ended it too."""
    await _call(hass, init_integration, SERVICE_SET_BATTERY_POWER, power=3000)
    monkeypatch.setattr(
        mock_unit, "write_registers", AsyncMock(side_effect=IllegalFunctionError())
    )
    mock_unit.fail_write(register(40198), ModbusTimeoutError())

    await _tick(hass, freezer)

    assert "Stopped holding battery_power" in caplog.text
    assert hass.states.get(REMOTE_CONTROL).state == STATE_OFF
