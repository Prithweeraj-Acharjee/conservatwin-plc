"""
ConservaTwin PLC — Vault Control Program
=========================================
Zone C — Vault / Archive
Strictest control: Temp 18°C, RH 45%
Fastest alarm escalation, aggressive recovery
"""

from __future__ import annotations
from plc.memory import I, Q, M

SP_TEMP  = 18.0
SP_RH    = 45.0
FP_SCALE = 100.0


def execute(mem, timers, pids, alarms, debounce_sensors, risk, dt: float,
            opt_sp_temp: float = SP_TEMP, opt_sp_rh: float = SP_RH) -> None:
    """Vault scan cycle program — tightest tolerances."""

    # ── 1. Read I image ───────────────────────────────────────────────────────
    temp_valid = debounce_sensors['c_temp'].update(mem.I.read_bit(*I.C_TEMP_VALID))
    rh_valid   = debounce_sensors['c_rh'].update(  mem.I.read_bit(*I.C_RH_VALID))

    temp = mem.I.read_word(I.C_TEMP_W) / FP_SCALE
    rh   = mem.I.read_word(I.C_RH_W)  / FP_SCALE

    # ── 2. Mode ───────────────────────────────────────────────────────────────
    auto_mode = mem.M.read_bit(*M.C_AUTO)
    alarm_ack = mem.M.read_bit(*M.C_ALARM_ACK) or mem.M.read_bit(*M.GLOBAL_ACK)

    # ── 3. Sensor validity ────────────────────────────────────────────────────
    sensor_fault = not temp_valid or not rh_valid
    alarms.c_sensor.update(SET=sensor_fault, ACK=alarm_ack)
    mem.M.write_bit(*M.SENSOR_C_INVALID, sensor_fault)

    if sensor_fault:
        _safe_state_c(mem)
        return

    # ── 4. Aggressive alarm (15-second TON) ──────────────────────────────────
    temp_deviated = abs(temp - opt_sp_temp) > 1.0      # vault: tighter than 2°C
    rh_deviated   = abs(rh   - opt_sp_rh)  > 3.0      # vault: tighter than 5%

    temp_alarm_ton_q, _ = timers.c_temp_alarm_ton.update(IN=temp_deviated, dt=dt)
    rh_alarm_ton_q,   _ = timers.c_rh_alarm_ton.update(  IN=rh_deviated,   dt=dt)

    alarms.c_temp.update(SET=temp_alarm_ton_q, ACK=alarm_ack)
    alarms.c_rh.update(  SET=rh_alarm_ton_q,   ACK=alarm_ack)

    mem.M.write_bit(*M.C_TEMP_ALARM,    alarms.c_temp.Q)
    mem.M.write_bit(*M.C_RH_ALARM,      alarms.c_rh.Q)
    mem.I.write_bit(*I.C_TEMP_HIGH, temp > opt_sp_temp + 1.0)
    mem.I.write_bit(*I.C_TEMP_LOW,  temp < opt_sp_temp - 1.0)
    mem.I.write_bit(*I.C_RH_HIGH,   rh   > opt_sp_rh   + 3.0)
    mem.I.write_bit(*I.C_RH_LOW,    rh   < opt_sp_rh   - 3.0)

    any_alarm = alarms.c_temp.Q or alarms.c_rh.Q or alarms.c_sensor.Q
    mem.M.write_bit(*M.C_ALARM_LATCHED, any_alarm)
    mem.Q.write_bit(*Q.C_ALARM_LIGHT, any_alarm)

    # ── 5. PID — highest gains ────────────────────────────────────────────────
    temp_cv = pids.c_temp.update(sp=opt_sp_temp, pv=temp, dt=dt, auto=auto_mode)
    rh_cv   = pids.c_rh.update(  sp=opt_sp_rh,   pv=rh,   dt=dt, auto=auto_mode)

    mem.Q.write_word(Q.C_TEMP_CV_W, int(temp_cv * FP_SCALE))
    mem.Q.write_word(Q.C_RH_CV_W,   int(rh_cv   * FP_SCALE))

    if auto_mode:
        mem.Q.write_bit(*Q.C_HEAT,       temp_cv > 3.0)    # tighter deadband
        mem.Q.write_bit(*Q.C_COOL,       temp_cv < -3.0)
        mem.Q.write_bit(*Q.C_FAN,        abs(temp_cv) > 0.5 or abs(rh_cv) > 0.5)
        mem.Q.write_bit(*Q.C_HUMIDIFY,   rh_cv > 3.0)
        mem.Q.write_bit(*Q.C_DEHUMIDIFY, rh_cv < -3.0)
    else:
        mem.Q.write_bit(*Q.C_HEAT,       mem.M.read_bit(*M.C_MANUAL_HEAT))
        mem.Q.write_bit(*Q.C_COOL,       mem.M.read_bit(*M.C_MANUAL_COOL))
        mem.Q.write_bit(*Q.C_HUMIDIFY,   mem.M.read_bit(*M.C_MANUAL_HUMIDIFY))
        mem.Q.write_bit(*Q.C_DEHUMIDIFY, mem.M.read_bit(*M.C_MANUAL_DEHUMID))
        mem.Q.write_bit(*Q.C_FAN,        False)

    # ── 6. Risk + Recovery ────────────────────────────────────────────────────
    risk_val, _, _ = risk.update(temp=temp, rh=rh, dt=dt, sp_temp=opt_sp_temp, sp_rh=opt_sp_rh)
    mem.M.write_word(M.C_RISK_W, int(risk_val * FP_SCALE))

    # Recovery RTO: stable conditions for 5 minutes clears recovery flag
    conditions_ok = not temp_deviated and not rh_deviated
    timers.c_recovery_rto.update(IN=conditions_ok, CLR=any_alarm, dt=dt)


def _safe_state_c(mem) -> None:
    for bit in [Q.C_HEAT, Q.C_COOL, Q.C_HUMIDIFY, Q.C_DEHUMIDIFY, Q.C_FAN]:
        mem.Q.write_bit(*bit, False)
    mem.Q.write_bit(*Q.C_ALARM_LIGHT, True)
