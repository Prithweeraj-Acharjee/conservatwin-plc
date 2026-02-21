"""
ConservaTwin PLC — Memory Module
=================================
Implements the PLC I/Q/M image tables as byte-array-backed memory.
All addressing follows IEC 61131-3 conventions:
  I = Input image  (plant → PLC)
  Q = Output image (PLC → plant)
  M = Internal memory / markers (HMI commands, mode bits, latches)

Bit addressing: word_index * 8 + bit_index  (e.g., I0.3 = byte 0, bit 3)
Word addressing: 16-bit signed integer view over respective byte arrays.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import Dict, Any


# ─── Address constants ────────────────────────────────────────────────────────
# Each zone occupies 4 bytes (32 bits) in I and Q images.
# Zones: A=0, B=1, C=2 (Vault)

class I:
    """Input image bit addresses (plant → PLC)."""
    # Zone A (byte 0-3)
    A_TEMP_VALID      = (0, 0)   # sensor valid flag
    A_TEMP_HIGH       = (0, 1)   # temp > SP+2
    A_TEMP_LOW        = (0, 2)   # temp < SP-2
    A_RH_VALID        = (0, 3)
    A_RH_HIGH         = (0, 4)
    A_RH_LOW          = (0, 5)
    A_RH_SLEW_WARN    = (0, 6)   # slew rate warning
    A_DOOR_OPEN       = (0, 7)

    # Zone A analogue words (I-word addresses, 16-bit)
    A_TEMP_W          = 2        # IW2: temperature ×100 fixed-point
    A_RH_W            = 4        # IW4: RH ×100 fixed-point
    A_SLEW_W          = 6        # IW6: RH slew rate ×100

    # Zone B (byte 8-15)
    B_TEMP_VALID      = (8, 0)
    B_TEMP_HIGH       = (8, 1)
    B_TEMP_LOW        = (8, 2)
    B_RH_VALID        = (8, 3)
    B_RH_HIGH         = (8, 4)
    B_RH_LOW          = (8, 5)
    B_CUMTEMP_WARN    = (8, 6)   # cumulative temp overexposure warning
    B_DOOR_OPEN       = (8, 7)

    B_TEMP_W          = 10
    B_RH_W            = 12
    B_CUMTEMP_W       = 14       # IW14: cumulative overexposure minutes ×10

    # Zone C — Vault (byte 16-23)
    C_TEMP_VALID      = (16, 0)
    C_TEMP_HIGH       = (16, 1)
    C_TEMP_LOW        = (16, 2)
    C_RH_VALID        = (16, 3)
    C_RH_HIGH         = (16, 4)
    C_RH_LOW          = (16, 5)
    C_DOOR_OPEN       = (16, 7)

    C_TEMP_W          = 18
    C_RH_W            = 20

    # System (byte 24)
    ESTOP             = (24, 0)  # hardware E-stop input
    WATCHDOG_OK       = (24, 1)  # watchdog heartbeat from plant
    PWR_OK            = (24, 2)  # power supply healthy
    FIRE_ALARM        = (24, 3)  # building fire alarm integration


class Q:
    """Output image bit addresses (PLC → plant)."""
    # Zone A actuators (byte 0)
    A_HEAT            = (0, 0)
    A_COOL            = (0, 1)
    A_HUMIDIFY        = (0, 2)
    A_DEHUMIDIFY      = (0, 3)
    A_FAN             = (0, 4)
    A_ALARM_LIGHT     = (0, 5)

    # Zone B actuators (byte 4)
    B_HEAT            = (4, 0)
    B_COOL            = (4, 1)
    B_HUMIDIFY        = (4, 2)
    B_DEHUMIDIFY      = (4, 3)
    B_FAN             = (4, 4)
    B_ALARM_LIGHT     = (4, 5)

    # Zone C — Vault actuators (byte 8)
    C_HEAT            = (8, 0)
    C_COOL            = (8, 1)
    C_HUMIDIFY        = (8, 2)
    C_DEHUMIDIFY      = (8, 3)
    C_FAN             = (8, 4)
    C_ALARM_LIGHT     = (8, 5)

    # Zone A analogue outputs (PID control values, Q-word addresses)
    A_TEMP_CV_W       = 2        # QW2: temperature PID CV ×100
    A_RH_CV_W         = 4        # QW4: RH PID CV ×100

    B_TEMP_CV_W       = 10
    B_RH_CV_W         = 12

    C_TEMP_CV_W       = 18
    C_RH_CV_W         = 20

    # System outputs (byte 12)
    SAFE_STATE        = (24, 0)  # all actuators forced off
    ESTOP_ACK         = (24, 1)


class M:
    """Marker / internal memory bit addresses (HMI commands → logic)."""
    # Mode bits per zone
    A_AUTO            = (0, 0)   # 1=Auto, 0=Manual
    A_MANUAL_HEAT     = (0, 1)
    A_MANUAL_COOL     = (0, 2)
    A_MANUAL_HUMIDIFY = (0, 3)
    A_MANUAL_DEHUMID  = (0, 4)
    A_ALARM_ACK       = (0, 5)   # operator alarm acknowledge

    B_AUTO            = (4, 0)
    B_MANUAL_HEAT     = (4, 1)
    B_MANUAL_COOL     = (4, 2)
    B_MANUAL_HUMIDIFY = (4, 3)
    B_MANUAL_DEHUMID  = (4, 4)
    B_ALARM_ACK       = (4, 5)

    C_AUTO            = (8, 0)
    C_MANUAL_HEAT     = (8, 1)
    C_MANUAL_COOL     = (8, 2)
    C_MANUAL_HUMIDIFY = (8, 3)
    C_MANUAL_DEHUMID  = (8, 4)
    C_ALARM_ACK       = (8, 5)

    # System M bits (byte 12)
    ESTOP_CMD         = (12, 0)  # software E-stop command from HMI
    PRES_FIRST_MODE   = (12, 1)  # preservation-first optimizer enable
    REPLAY_MODE       = (12, 2)  # historian replay active
    FAULT_INJECT      = (12, 3)  # test harness fault injection active
    GLOBAL_ACK        = (12, 4)  # acknowledge all alarms

    # Alarm latch outputs (byte 16) — written by AlarmLatch FBs
    A_ALARM_LATCHED   = (16, 0)
    A_TEMP_ALARM      = (16, 1)
    A_RH_ALARM        = (16, 2)
    A_SLEW_ALARM      = (16, 3)

    B_ALARM_LATCHED   = (17, 0)
    B_TEMP_ALARM      = (17, 1)
    B_RH_ALARM        = (17, 2)
    B_CUMTEMP_ALARM   = (17, 3)

    C_ALARM_LATCHED   = (18, 0)
    C_TEMP_ALARM      = (18, 1)
    C_RH_ALARM        = (18, 2)

    WATCHDOG_ALARM    = (19, 0)
    SENSOR_A_INVALID  = (19, 1)
    SENSOR_B_INVALID  = (19, 2)
    SENSOR_C_INVALID  = (19, 3)

    # Risk index words (M-word addresses)
    A_RISK_W          = 20       # MW20: Zone A PRI ×100
    B_RISK_W          = 22       # MW22: Zone B PRI ×100
    C_RISK_W          = 24       # MW24: Vault PRI ×100


IMAGE_SIZE = 64   # bytes per image table


class IOImage:
    """Byte-array-backed memory image for one of I, Q, or M tables."""

    def __init__(self, name: str, size: int = IMAGE_SIZE):
        self.name = name
        self._data = bytearray(size)
        self.size = size

    def read_bit(self, byte_addr: int, bit_addr: int) -> bool:
        self._check_addr(byte_addr)
        return bool((self._data[byte_addr] >> bit_addr) & 1)

    def write_bit(self, byte_addr: int, bit_addr: int, value: bool) -> None:
        self._check_addr(byte_addr)
        if value:
            self._data[byte_addr] |= (1 << bit_addr)
        else:
            self._data[byte_addr] &= ~(1 << bit_addr)

    def read_word(self, byte_addr: int) -> int:
        """Read signed 16-bit integer at byte_addr."""
        self._check_addr(byte_addr, width=2)
        return struct.unpack_from('>h', self._data, byte_addr)[0]

    def write_word(self, byte_addr: int, value: int) -> None:
        """Write signed 16-bit integer at byte_addr. Clamps to int16 range."""
        self._check_addr(byte_addr, width=2)
        value = max(-32768, min(32767, int(value)))
        struct.pack_into('>h', self._data, byte_addr, value)

    def snapshot(self) -> bytes:
        """Return immutable snapshot of current image."""
        return bytes(self._data)

    def restore(self, snap: bytes) -> None:
        """Restore from snapshot (replay mode)."""
        assert len(snap) == self.size
        self._data[:] = snap

    def as_hex(self) -> str:
        return self._data.hex(' ')

    def as_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'hex': self.as_hex(),
            'bytes': list(self._data),
        }

    def _check_addr(self, byte_addr: int, width: int = 1) -> None:
        if byte_addr < 0 or byte_addr + width > self.size:
            raise IndexError(
                f"{self.name}: address {byte_addr} out of range [0, {self.size})"
            )


@dataclass
class PLCMemory:
    """Holds all three image tables for the PLC."""
    I: IOImage = field(default_factory=lambda: IOImage("I", IMAGE_SIZE))
    Q: IOImage = field(default_factory=lambda: IOImage("Q", IMAGE_SIZE))
    M: IOImage = field(default_factory=lambda: IOImage("M", IMAGE_SIZE))

    def snapshot(self) -> Dict[str, bytes]:
        return {'I': self.I.snapshot(), 'Q': self.Q.snapshot(), 'M': self.M.snapshot()}

    def restore(self, snap: Dict[str, bytes]) -> None:
        self.I.restore(snap['I'])
        self.Q.restore(snap['Q'])
        self.M.restore(snap['M'])

    def as_dict(self) -> Dict[str, Any]:
        return {
            'I': self.I.as_dict(),
            'Q': self.Q.as_dict(),
            'M': self.M.as_dict(),
        }
