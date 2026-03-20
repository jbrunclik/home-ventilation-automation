from datetime import datetime, timedelta

from home_ventilation.config import ScheduleConfig, ThresholdsConfig
from home_ventilation.models import FanSpeed, FanState


def _is_schedule_active(schedule: ScheduleConfig, now: datetime) -> bool:
    """Check if the current time falls within an active schedule window."""
    hour = now.hour
    minute = now.minute

    # Check if hour is within start_hour..end_hour (may wrap past midnight)
    if schedule.start_hour > schedule.end_hour:
        in_range = hour >= schedule.start_hour or hour < schedule.end_hour
    else:
        in_range = schedule.start_hour <= hour < schedule.end_hour

    return in_range and minute < schedule.run_minutes


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
    1. Manual switch press -> HIGH for override_minutes
    2. Humidity thresholds
    3. CO2 thresholds
    4. Time-based schedule
    """
    override_until = current_state.override_until

    # Detect switch press (rising edge: was False, now True)
    switch_pressed = False
    prev = current_state.previous_switch_states
    if prev is not None:
        for input_id, is_on in switch_states.items():
            if is_on and not prev.get(input_id, False):
                switch_pressed = True
                break

    new_switch_states = dict(switch_states)

    # 1. Manual override
    if switch_pressed:
        override_until = now + timedelta(minutes=override_minutes)

    if override_until and now < override_until:
        return FanSpeed.HIGH, FanState(
            current_speed=FanSpeed.HIGH,
            override_until=override_until,
            previous_switch_states=new_switch_states,
        )

    # Clear expired override
    override_until = None

    # 2. Humidity check (max of all sensors)
    valid_humidity = [h for h in humidity_values if h is not None]
    if valid_humidity:
        max_humidity = max(valid_humidity)
        if max_humidity > thresholds.humidity_high:
            return FanSpeed.HIGH, FanState(
                current_speed=FanSpeed.HIGH,
                override_until=override_until,
                previous_switch_states=new_switch_states,
            )
        if max_humidity >= thresholds.humidity_low:
            return FanSpeed.LOW, FanState(
                current_speed=FanSpeed.LOW,
                override_until=override_until,
                previous_switch_states=new_switch_states,
            )

    # 3. CO2 check (max of all sensors)
    valid_co2 = [c for c in co2_values if c is not None]
    if valid_co2:
        max_co2 = max(valid_co2)
        if max_co2 > thresholds.co2_high:
            return FanSpeed.HIGH, FanState(
                current_speed=FanSpeed.HIGH,
                override_until=override_until,
                previous_switch_states=new_switch_states,
            )
        if max_co2 >= thresholds.co2_low:
            return FanSpeed.LOW, FanState(
                current_speed=FanSpeed.LOW,
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
