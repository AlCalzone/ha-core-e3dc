"""Tests for the E3/DC integration."""

from e3dc_ess_modbus.model import register
from modbus_connection.mock import MockModbusUnit

from homeassistant.const import CONF_HOST, CONF_PORT

MOCK_SERIAL = "S10-12345678912"
MOCK_MODEL = "S10 X"
MOCK_FIRMWARE = "S10_2026_04"

MOCK_ENTRY_DATA = {CONF_HOST: "192.168.1.100", CONF_PORT: 502}


def _ascii_words(text: str, length: int) -> list[int]:
    """Pack ASCII into ``length`` registers, two characters each."""
    padded = text.ljust(length * 2, "\0")
    return [(ord(padded[i]) << 8) | ord(padded[i + 1]) for i in range(0, length * 2, 2)]


def int32_words(value: int) -> list[int]:
    """An int32 as E3/DC sends it, low word first."""
    raw = value & 0xFFFFFFFF
    return [raw & 0xFFFF, raw >> 16]


def seed(unit: MockModbusUnit, holding: dict[int, int | list[int]]) -> None:
    """Load register values, given by the manual's numbering, into the mock."""
    for index, value in holding.items():
        unit.holding[register(index)] = value


def seed_identity(
    unit: MockModbusUnit, serial: str = MOCK_SERIAL, model: str = MOCK_MODEL
) -> None:
    """Seed the identification block: every firmware has it."""
    seed(
        unit,
        {
            40001: 0xE3DC,  # Marker for the E3/DC protocol
            40002: 0x0203,  # Modbus protocol version 2.3
            40003: 210,  # Number of registers the power station serves
            40004: _ascii_words("HagerEnergy GmbH", 16),  # Manufacturer
            40020: _ascii_words(model, 16),  # Model
            40036: _ascii_words(serial, 16),  # Serial number
            40052: _ascii_words(MOCK_FIRMWARE, 16),  # Firmware release
        },
    )


def seed_power_station(unit: MockModbusUnit) -> None:
    """Seed an S10 X with one wallbox, a root meter and every firmware block."""
    seed_identity(unit)
    seed(
        unit,
        {
            40068: int32_words(5321),  # PV power
            40070: int32_words(-1200),  # Battery power, discharging
            40072: int32_words(870),  # House power
            40074: int32_words(-600),  # Grid power, feeding in
            40078: int32_words(11000),  # Wallbox power
            40080: int32_words(4200),  # Wallbox solar power
            40082: 6738,  # Self-sufficiency 26 % (high byte), self-consumption 82 %
            40083: 87,  # Battery state of charge, in %
            40084: 2,  # Emergency power not active
            40085: 0b0010100,  # EMS status: emergency power ready, feed-in limited
            40088: 0b0000000111011,  # Wallbox 0: solar, charging, plugged, locked
            40096: 612,  # DC string 1 voltage, in V
            40099: 450,  # DC string 1 current, in 0.01 A
            40102: 2754,  # DC string 1 power, in W
            40105: 1,  # Meter 0 type: root
            40106: 0xFF38,  # Meter 0 power L1, -200 W
            40107: 150,  # Meter 0 power L2, in W
            40108: 100,  # Meter 0 power L3, in W
            40109: 6,  # Meter 1 type: not used
            40137: 1,  # SG Ready status
            40138: int32_words(-200),  # Meter 0 power L1, 32 bit
            40140: int32_words(150),  # Meter 0 power L2, 32 bit
            40142: int32_words(100),  # Meter 0 power L3, 32 bit
            40186: int32_words(5000),  # Feed-in limit, in W
            40188: 1,  # Power output ready
            40194: 30,  # Active power failsafe timeout, in s
            40196: 30,  # Reactive power failsafe timeout, in s
            40201: 0,  # Inverter mode: normal
            40202: int32_words(9000),  # Battery max charge power, in W
            40204: int32_words(-9000),  # Battery max discharge power, in W
            40206: int32_words(7800),  # Battery remaining energy, in Wh
            40208: int32_words(10500),  # Battery full charge energy, in Wh
            41006: int32_words(1750),  # Inverter 0 active power L1, in W
            41018: 2301,  # Inverter 0 voltage L1, in 0.1 V
            41019: 2299,  # Inverter 0 voltage L2, in 0.1 V
            41020: 2310,  # Inverter 0 voltage L3, in 0.1 V
            41024: 5001,  # Inverter 0 frequency, in 0.01 Hz
            41025: 2754,  # Inverter 0 DC power 1, in W
            41027: 1210,  # Inverter 0 DC power 3, in W
        },
    )
