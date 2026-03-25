from datetime import datetime, timedelta, timezone

from home_ventilation.config import ScheduleConfig
from home_ventilation.fan import decide_speed
from home_ventilation.models import FanSpeed, FanState
from tests.conftest import DEFAULT_THRESHOLDS

SCHEDULE = ScheduleConfig(start_hour=22, end_hour=7, run_minutes=10, speed="low")
SCHEDULE_CAP_ONLY = ScheduleConfig(start_hour=22, end_hour=7, run_minutes=0, max_speed="low")
SCHEDULE_WITH_CAP = ScheduleConfig(
    start_hour=22, end_hour=7, run_minutes=10, speed="low", max_speed="low"
)

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


def test_switch_on_returns_high():
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
    assert new_state.override_until is None  # timer starts on release, not press


def test_switch_stays_on_keeps_high():
    """Switch still ON on subsequent cycles → stays HIGH regardless of sensors."""
    state = _state(prev_switches={0: True})
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
    assert new_state.override_until is None


def test_switch_release_starts_cooldown():
    """Switch released → cooldown timer starts."""
    state = _state(prev_switches={0: True})
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


def test_no_previous_switch_state_switch_on():
    """First poll cycle: no previous state, switch is on → HIGH (level check)."""
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
    assert speed == FanSpeed.HIGH


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


# --- CO2 hysteresis ---


def test_co2_hysteresis_holds_low_in_dead_band():
    """CO2 at 770 (below 800 but above 800-50=750): stays LOW when already LOW."""
    speed, _ = decide_speed(
        co2_values=[770],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.LOW),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_co2_hysteresis_turns_off_below_dead_band():
    """CO2 at 749 (below 800-50=750): turns OFF even when currently LOW."""
    speed, _ = decide_speed(
        co2_values=[749],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.LOW),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_co2_hysteresis_no_effect_when_off():
    """CO2 at 770 when fan is OFF: no hysteresis, stays OFF (below 800)."""
    speed, _ = decide_speed(
        co2_values=[770],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.OFF),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_co2_hysteresis_holds_high_in_dead_band():
    """CO2 at 1180 (below 1200 but above 1200-50=1150): stays HIGH when already HIGH."""
    speed, _ = decide_speed(
        co2_values=[1180],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.HIGH),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


def test_co2_hysteresis_drops_to_low_below_high_dead_band():
    """CO2 at 1149 (below 1200-50=1150): drops to LOW even when currently HIGH."""
    speed, _ = decide_speed(
        co2_values=[1149],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.HIGH),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_co2_hysteresis_no_effect_on_upward_transition():
    """CO2 at 800 when fan is OFF: triggers LOW (upward uses normal threshold)."""
    speed, _ = decide_speed(
        co2_values=[800],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.OFF),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


# --- Humidity hysteresis ---


def test_humidity_hysteresis_holds_low_in_dead_band():
    """Humidity at 58.0 (below 60 but above 60-3=57): stays LOW when already LOW."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[58.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.LOW),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_humidity_hysteresis_turns_off_below_dead_band():
    """Humidity at 56.9 (below 60-3=57): turns OFF even when currently LOW."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[56.9],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.LOW),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_humidity_hysteresis_no_effect_when_off():
    """Humidity at 58.0 when fan is OFF: no hysteresis, stays OFF (below 60)."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[58.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.OFF),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.OFF


def test_humidity_hysteresis_holds_high_in_dead_band():
    """Humidity at 68.0 (below 70 but above 70-3=67): stays HIGH when already HIGH."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[68.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.HIGH),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.HIGH


def test_humidity_hysteresis_drops_to_low_below_high_dead_band():
    """Humidity at 66.9 (below 70-3=67): drops to LOW even when currently HIGH."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[66.9],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.HIGH),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_humidity_hysteresis_no_effect_on_upward_transition():
    """Humidity at 60.0 when fan is OFF: triggers LOW (upward uses normal threshold)."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[60.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.OFF),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


# --- Cross-sensor hysteresis ---


def test_cross_sensor_high_co2_humidity_in_dead_band():
    """Fan HIGH from CO2, humidity at 58 (in dead band 57-60): humidity holds LOW."""
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[58.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.HIGH),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


def test_co2_hysteresis_exact_boundary():
    """CO2 at exactly 750 (=800-50): stays LOW when already LOW (>= effective threshold)."""
    speed, _ = decide_speed(
        co2_values=[750],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(speed=FanSpeed.LOW),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=NOW,
    )
    assert speed == FanSpeed.LOW


# --- max_speed cap ---


def test_max_speed_caps_co2_high_to_low_at_night():
    """CO2 >1200 would normally give HIGH, but max_speed caps to LOW at night."""
    night = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[1500],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE_CAP_ONLY,
    )
    assert speed == FanSpeed.LOW


def test_max_speed_caps_humidity_high_to_low_at_night():
    """Humidity >70 would normally give HIGH, but max_speed caps to LOW at night."""
    night = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[80.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE_CAP_ONLY,
    )
    assert speed == FanSpeed.LOW


def test_max_speed_no_effect_during_day():
    """max_speed doesn't apply outside the schedule window."""
    day = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[1500],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=day,
        schedule=SCHEDULE_CAP_ONLY,
    )
    assert speed == FanSpeed.HIGH


def test_max_speed_switch_override_bypasses_cap():
    """Switch override should bypass the max_speed cap."""
    night = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: True},
        current_state=_state(prev_switches={0: False}),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE_CAP_ONLY,
    )
    assert speed == FanSpeed.HIGH


def test_max_speed_does_not_raise_low_to_high():
    """max_speed=low should not affect a speed that's already LOW."""
    night = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[900],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE_CAP_ONLY,
    )
    assert speed == FanSpeed.LOW


def test_cap_only_no_periodic_run():
    """run_minutes=0 with max_speed: no periodic runs, but cap still applies."""
    night = datetime(2026, 1, 15, 23, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE_CAP_ONLY,
    )
    assert speed == FanSpeed.OFF


def test_schedule_with_cap_periodic_still_works():
    """Schedule with both run_minutes and max_speed: periodic runs still work."""
    night = datetime(2026, 1, 15, 23, 5, 0, tzinfo=timezone.utc)
    speed, _ = decide_speed(
        co2_values=[400],
        humidity_values=[40.0],
        switch_states={0: False},
        current_state=_state(),
        thresholds=DEFAULT_THRESHOLDS,
        override_minutes=OVERRIDE_MINUTES,
        now=night,
        schedule=SCHEDULE_WITH_CAP,
    )
    assert speed == FanSpeed.LOW
