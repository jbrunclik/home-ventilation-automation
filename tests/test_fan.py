from datetime import datetime, timedelta, timezone

from home_ventilation.config import ScheduleConfig
from home_ventilation.fan import decide_speed
from home_ventilation.models import FanSpeed, FanState
from tests.conftest import DEFAULT_THRESHOLDS

SCHEDULE = ScheduleConfig(start_hour=22, end_hour=7, run_minutes=10, speed="low")

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
OVERRIDE_MINUTES = 15


def _state(
    speed: FanSpeed = FanSpeed.OFF,
    override_until: datetime | None = None,
    prev_switches: dict[int, bool] | None = None,
) -> FanState:
    return FanState(
        current_speed=speed,
        override_until=override_until,
        previous_switch_states=prev_switches if prev_switches is not None else {0: False},
    )


# --- CO2 thresholds ---


def test_co2_below_low_returns_off():
    speed, _ = decide_speed(
        co2_values=[500],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_co2_at_low_boundary_returns_low():
    speed, _ = decide_speed(
        co2_values=[800],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_co2_between_low_and_high_returns_low():
    speed, _ = decide_speed(
        co2_values=[1000],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_co2_at_high_boundary_returns_low():
    speed, _ = decide_speed(
        co2_values=[1200],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_co2_above_high_returns_high():
    speed, _ = decide_speed(
        co2_values=[1500],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


# --- Humidity thresholds ---


def test_humidity_below_low_returns_off():
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[50.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_humidity_at_low_boundary_returns_low():
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[60.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_humidity_between_low_and_high_returns_low():
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[65.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_humidity_above_high_returns_high():
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[75.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


# --- Priority: humidity > CO2 ---


def test_humidity_high_overrides_co2_low():
    speed, _ = decide_speed(
        co2_values=[500],
        humidity_values=[75.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


def test_humidity_low_overrides_co2_off():
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[65.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


# --- Manual override ---


def test_switch_press_triggers_override():
    state = _state(prev_switches={0: False})
    speed, new_state = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: True},
        current_state=state,
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH
    assert new_state.override_until == NOW + timedelta(minutes=OVERRIDE_MINUTES)


def test_override_active_returns_high():
    override_until = NOW + timedelta(minutes=5)
    state = _state(override_until=override_until, prev_switches={0: False})
    speed, new_state = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=state,
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH
    assert new_state.override_until == override_until


def test_override_expired_falls_through():
    override_until = NOW - timedelta(minutes=1)
    state = _state(override_until=override_until, prev_switches={0: False})
    speed, new_state = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=state,
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF
    assert new_state.override_until is None


def test_override_beats_low_humidity():
    state = _state(prev_switches={0: False})
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[65.0],
        switch_states={0: True},
        current_state=state,
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


# --- Multi-sensor max ---


def test_multi_co2_takes_max():
    speed, _ = decide_speed(
        co2_values=[500, 1300],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


def test_multi_humidity_takes_max():
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[50.0, 75.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


# --- None sensor values ---


def test_all_none_returns_off():
    speed, _ = decide_speed(
        co2_values=[None],
        humidity_values=[None],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_none_co2_with_valid_humidity():
    speed, _ = decide_speed(
        co2_values=[None],
        humidity_values=[75.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


def test_no_previous_switch_state_no_edge():
    """First poll cycle: no previous state, switch is on, should not trigger override."""
    state = FanState()  # previous_switch_states is None
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: True},
        current_state=state,
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


# --- Time-based schedule ---


def test_schedule_active_at_night():
    night = datetime(2026, 1, 15, 23, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE,
    )
    assert speed == FanSpeed.LOW


def test_schedule_inactive_after_run_minutes():
    night = datetime(2026, 1, 15, 23, 15, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE,
    )
    assert speed == FanSpeed.OFF


def test_schedule_inactive_during_day():
    day = datetime(2026, 1, 15, 14, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=day,
        schedule=SCHEDULE,
    )
    assert speed == FanSpeed.OFF


def test_schedule_active_after_midnight():
    early = datetime(2026, 1, 15, 3, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=early,
        schedule=SCHEDULE,
    )
    assert speed == FanSpeed.LOW


def test_schedule_boundary_at_end_hour():
    """At exactly end_hour:00, schedule should be inactive."""
    boundary = datetime(2026, 1, 15, 7, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=boundary,
        schedule=SCHEDULE,
    )
    assert speed == FanSpeed.OFF


def test_humidity_overrides_schedule():
    night = datetime(2026, 1, 15, 23, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[75.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE,
    )
    assert speed == FanSpeed.HIGH


def test_no_schedule_returns_off():
    night = datetime(2026, 1, 15, 23, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=None,
    )
    assert speed == FanSpeed.OFF
