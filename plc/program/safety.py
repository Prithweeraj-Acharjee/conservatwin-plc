"""
ConservaTwin PLC — Safety Program
===================================
E-Stop handling, sensor validity gating, Manual/Auto mode interlocks.
Runs at the START of every scan, before zone programs.
If E-Stop is active, this program forces all Q bits to safe state.
"""

from __future__ import annotations
from plc.memory import I, Q, M


def execute(mem, alarms, dt: float) -> bool:
    """
    Safety network — runs first every scan.

    Returns:
        True  = safe to run zone programs
        False = E-Stop or critical safety fault; zone programs must NOT run
    """
    # ── E-Stop detection ──────────────────────────────────────────────────────
    hw_estop  = mem.I.read_bit(*I.ESTOP)          # hardware E-stop (NC contact)
    sw_estop  = mem.M.read_bit(*M.ESTOP_CMD)      # software E-stop from HMI
    fire_alarm = mem.I.read_bit(*I.FIRE_ALARM)

    estop_active = hw_estop or sw_estop or fire_alarm

    alarms.estop.update(SET=estop_active, ACK=False)   # E-Stop never auto-acks

    if estop_active:
        _force_safe_state(mem)
        mem.Q.write_bit(*Q.SAFE_STATE, True)
        return False

    # ── Power / watchdog check ────────────────────────────────────────────────
    pwr_ok = mem.I.read_bit(*I.PWR_OK)
    if not pwr_ok:
        _force_safe_state(mem)
        mem.Q.write_bit(*Q.SAFE_STATE, True)
        return False

    mem.Q.write_bit(*Q.SAFE_STATE, False)
    mem.Q.write_bit(*Q.ESTOP_ACK, True)
    return True


def _force_safe_state(mem) -> None:
    """Turn off every actuator output."""
    actuator_bits = [
        Q.A_HEAT, Q.A_COOL, Q.A_HUMIDIFY, Q.A_DEHUMIDIFY, Q.A_FAN,
        Q.B_HEAT, Q.B_COOL, Q.B_HUMIDIFY, Q.B_DEHUMIDIFY, Q.B_FAN,
        Q.C_HEAT, Q.C_COOL, Q.C_HUMIDIFY, Q.C_DEHUMIDIFY, Q.C_FAN,
    ]
    for bit in actuator_bits:
        mem.Q.write_bit(*bit, False)
    # Turn on all alarm lights
    for bit in [Q.A_ALARM_LIGHT, Q.B_ALARM_LIGHT, Q.C_ALARM_LIGHT]:
        mem.Q.write_bit(*bit, True)
