"""
ConservaTwin PLC — Zone B Control Program
==========================================
Gallery B — "Basquiat: Soul That Saw the Inside"
Artwork: Acrylic / Oil / Canvas / Pigment Layers
Setpoints: Temp 21°C ±2, RH 50% ±5

Special: tracks cumulative temperature overexposure minutes
"""

from __future__ import annotations
from plc.memory import I, Q, M

SP_TEMP = 21.0
SP_RH   = 50.0
FP_SCALE = 100.0


def execute(mem, timers, pids, alarms, debounce_sensors, risk, dt: float,
            opt_sp_temp: float = SP_TEMP, opt_sp_rh: float = SP_RH) -> None:
    """Zone B scan cycle program."""

    # ── 1. Read I image ───────────────────────────────────────────────────────
    temp_valid_raw = mem.I.read_bit(*I.B_TEMP_VALID)
    rh_valid_raw   = mem.I.read_bit(*I.B_RH_VALID)
    temp_valid = debounce_sensors['b_temp'].update(temp_valid_raw)
    rh_valid   = debounce_sensors['b_rh'].update(rh_valid_raw)

    temp_fp = mem.I.read_word(I.B_TEMP_W)
    rh_fp   = mem.I.read_word(I.B_RH_W)
    temp    = temp_fp / FP_SCALE
    rh      = rh_fp   / FP_SCALE

    # ── 2. Mode ───────────────────────────────────────────────────────────────
    auto_mode  = mem.M.read_bit(*M.B_AUTO)
    alarm_ack  = mem.M.read_bit(*M.B_ALARM_ACK) or mem.M.read_bit(*M.GLOBAL_ACK)

    # ── 3. Sensor validity gate ───────────────────────────────────────────────
    sensor_fault = not temp_valid or not rh_valid
    alarms.b_sensor.update(SET=sensor_fault, ACK=alarm_ack)
    mem.M.write_bit(*M.SENSOR_B_INVALID, sensor_fault)

    if sensor_fault:
        _safe_state_b(mem)
        return

    # ── 4. Alarm detection ────────────────────────────────────────────────────
    temp_alarm_set = (temp > opt_sp_temp + 2.0) or (temp < opt_sp_temp - 2.0)
    rh_low_trip,  _ = timers.b_rh_low_ton.update(IN=(rh < opt_sp_rh - 5.0), dt=dt)
    rh_high_trip, _ = timers.b_rh_high_ton.update(IN=(rh > opt_sp_rh + 5.0), dt=dt)
    rh_alarm_set = rh_low_trip or rh_high_trip

    alarms.b_temp.update(SET=temp_alarm_set, ACK=alarm_ack)
    alarms.b_rh.update(  SET=rh_alarm_set,   ACK=alarm_ack)

    mem.M.write_bit(*M.B_TEMP_ALARM, alarms.b_temp.Q)
    mem.M.write_bit(*M.B_RH_ALARM,   alarms.b_rh.Q)
    mem.I.write_bit(*I.B_TEMP_HIGH, temp > opt_sp_temp + 2.0)
    mem.I.write_bit(*I.B_TEMP_LOW,  temp < opt_sp_temp - 2.0)
    mem.I.write_bit(*I.B_RH_HIGH,   rh > opt_sp_rh + 5.0)
    mem.I.write_bit(*I.B_RH_LOW,    rh < opt_sp_rh - 5.0)

    # Cumulative temp overexposure RTO
    risk_val, risk_alarm, risk_crit, cumtemp = risk.update(
        temp=temp, rh=rh, dt=dt, sp_temp=opt_sp_temp, sp_rh=opt_sp_rh)

    cumtemp_warn = cumtemp > 30.0
    mem.I.write_bit(*I.B_CUMTEMP_WARN, cumtemp_warn)
    mem.I.write_word(I.B_CUMTEMP_W, int(cumtemp * 10))  # ×10 scale for better resolution
    alarms.b_cumtemp.update(SET=cumtemp_warn, ACK=alarm_ack)
    mem.M.write_bit(*M.B_CUMTEMP_ALARM, alarms.b_cumtemp.Q)

    any_alarm = alarms.b_temp.Q or alarms.b_rh.Q or alarms.b_cumtemp.Q or alarms.b_sensor.Q
    mem.M.write_bit(*M.B_ALARM_LATCHED, any_alarm)
    mem.Q.write_bit(*Q.B_ALARM_LIGHT, any_alarm)

    # ── 5. PID + Outputs ──────────────────────────────────────────────────────
    temp_cv = pids.b_temp.update(sp=opt_sp_temp, pv=temp, dt=dt, auto=auto_mode)
    rh_cv   = pids.b_rh.update(  sp=opt_sp_rh,   pv=rh,   dt=dt, auto=auto_mode)

    mem.Q.write_word(Q.B_TEMP_CV_W, int(temp_cv * FP_SCALE))
    mem.Q.write_word(Q.B_RH_CV_W,   int(rh_cv   * FP_SCALE))

    if auto_mode:
        mem.Q.write_bit(*Q.B_HEAT,       temp_cv > 5.0)
        mem.Q.write_bit(*Q.B_COOL,       temp_cv < -5.0)
        mem.Q.write_bit(*Q.B_FAN,        abs(temp_cv) > 1.0 or abs(rh_cv) > 1.0)
        mem.Q.write_bit(*Q.B_HUMIDIFY,   rh_cv > 5.0)
        mem.Q.write_bit(*Q.B_DEHUMIDIFY, rh_cv < -5.0)
    else:
        mem.Q.write_bit(*Q.B_HEAT,       mem.M.read_bit(*M.B_MANUAL_HEAT))
        mem.Q.write_bit(*Q.B_COOL,       mem.M.read_bit(*M.B_MANUAL_COOL))
        mem.Q.write_bit(*Q.B_HUMIDIFY,   mem.M.read_bit(*M.B_MANUAL_HUMIDIFY))
        mem.Q.write_bit(*Q.B_DEHUMIDIFY, mem.M.read_bit(*M.B_MANUAL_DEHUMID))
        mem.Q.write_bit(*Q.B_FAN,        False)

    # ── 6. Risk index → M word ───────────────────────────────────────────────
    mem.M.write_word(M.B_RISK_W, int(risk_val * FP_SCALE))


def _safe_state_b(mem) -> None:
    for bit in [Q.B_HEAT, Q.B_COOL, Q.B_HUMIDIFY, Q.B_DEHUMIDIFY, Q.B_FAN]:
        mem.Q.write_bit(*bit, False)
    mem.Q.write_bit(*Q.B_ALARM_LIGHT, True)
