from datetime import datetime, timedelta

from home_ventilation.config import ScheduleConfig, ThresholdsConfig
from home_ventilation.models import FanSpeed, FanState


def _in_schedule_window(schedule: ScheduleConfig, now: datetime) -> bool:
    """Check if the current time falls within the schedule's time window."""
    hour = now.hour
    if schedule.start_hour > schedule.end_hour:
        return hour >= schedule.start_hour or hour < schedule.end_hour
    return schedule.start_hour <= hour < schedule.end_hour


def _is_schedule_active(schedule: ScheduleConfig, now: datetime) -> bool:
    """Check if the periodic run is active (inside window AND within run_minutes)."""
    return (
        schedule.run_minutes > 0
        and _in_schedule_window(schedule, now)
        and now.minute < schedule.run_minutes
    )


def _apply_max_speed(speed: FanSpeed, schedule: ScheduleConfig | None, now: datetime) -> FanSpeed:
    """Cap speed to schedule.max_speed when inside the schedule window."""
    if schedule and schedule.max_speed and _in_schedule_window(schedule, now):
        cap = FanSpeed(schedule.max_speed)
        if speed.value == "high" and cap.value == "low":
            return cap
    return speed


def decide_speed(
    co2_values: list[int | None],
    humidity_values: list[float | None],
    switch_states: dict[int, bool],
    current_state: FanState,
    thresholds: ThresholdsConfig,
    override_minutes: int,
    now: datetime,
    schedule: ScheduleConfig | None = None,
) -> tuple[FanSpeed, FanState]:
    """Decide fan speed based on sensor readings and switch state.

    Priority (highest to lowest):
    1a. Any switch currently ON -> HIGH
    1b. Switch released -> HIGH for override_minutes cooldown
    2. Humidity thresholds
    3. CO2 thresholds
    4. Time-based schedule
    """
    override_until = current_state.override_until
    new_switch_states = dict(switch_states)

    # 1a. Any switch currently ON → HIGH (no timer needed)
    any_switch_on = any(switch_states.values()) if switch_states else False
    if any_switch_on:
        return FanSpeed.HIGH, FanState(
            current_speed=FanSpeed.HIGH,
            override_until=None,
            previous_switch_states=new_switch_states,
        )

    # 1b. Detect switch release (falling edge) → start cooldown timer
    prev = current_state.previous_switch_states
    if prev is not None:
        for input_id, was_on in prev.items():
            if was_on and not switch_states.get(input_id, False):
                override_until = now + timedelta(minutes=override_minutes)
                break

    if override_until and now < override_until:
        return FanSpeed.HIGH, FanState(
            current_speed=FanSpeed.HIGH,
            override_until=override_until,
            previous_switch_states=new_switch_states,
        )

    # Clear expired override
    override_until = None

    # 2. Humidity check (max of all sensors)
    #    Hysteresis: lower thresholds when fan is already at/above the guarded speed
    current_speed = current_state.current_speed
    valid_humidity = [h for h in humidity_values if h is not None]
    if valid_humidity:
        max_humidity = max(valid_humidity)
        eff_humidity_high = thresholds.humidity_high
        eff_humidity_low = thresholds.humidity_low
        if current_speed == FanSpeed.HIGH:
            eff_humidity_high -= thresholds.humidity_hysteresis
        if current_speed in (FanSpeed.LOW, FanSpeed.HIGH):
            eff_humidity_low -= thresholds.humidity_hysteresis
        if max_humidity > eff_humidity_high:
            speed = FanSpeed.HIGH
        elif max_humidity >= eff_humidity_low:
            speed = FanSpeed.LOW
        else:
            speed = None
        if speed is not None:
            speed = _apply_max_speed(speed, schedule, now)
            return speed, FanState(
                current_speed=speed,
                override_until=override_until,
                previous_switch_states=new_switch_states,
            )

    # 3. CO2 check (max of all sensors)
    #    Hysteresis: lower thresholds when fan is already at/above the guarded speed
    valid_co2 = [c for c in co2_values if c is not None]
    if valid_co2:
        max_co2 = max(valid_co2)
        eff_co2_high = thresholds.co2_high
        eff_co2_low = thresholds.co2_low
        if current_speed == FanSpeed.HIGH:
            eff_co2_high -= thresholds.co2_hysteresis
        if current_speed in (FanSpeed.LOW, FanSpeed.HIGH):
            eff_co2_low -= thresholds.co2_hysteresis
        if max_co2 > eff_co2_high:
            speed = FanSpeed.HIGH
        elif max_co2 >= eff_co2_low:
            speed = FanSpeed.LOW
        else:
            speed = None
        if speed is not None:
            speed = _apply_max_speed(speed, schedule, now)
            return speed, FanState(
                current_speed=speed,
                override_until=override_until,
                previous_switch_states=new_switch_states,
            )

    # 4. Time-based schedule
    if schedule and _is_schedule_active(schedule, now):
        speed = FanSpeed(schedule.speed)
        return speed, FanState(
            current_speed=speed,
            override_until=override_until,
            previous_switch_states=new_switch_states,
        )

    return FanSpeed.OFF, FanState(
        current_speed=FanSpeed.OFF,
        override_until=override_until,
        previous_switch_states=new_switch_states,
    )
