#include "fan_logic.h"

#include <cstring>

const char* fanSpeedStr(FanSpeed speed) {
    switch (speed) {
        case FanSpeed::SPEED_OFF: return "off";
        case FanSpeed::SPEED_LOW: return "low";
        case FanSpeed::SPEED_HIGH: return "high";
    }
    return "off";
}

static FanSpeed speedFromStr(const char* s) {
    if (strcmp(s, "high") == 0) return FanSpeed::SPEED_HIGH;
    if (strcmp(s, "low") == 0) return FanSpeed::SPEED_LOW;
    return FanSpeed::SPEED_OFF;
}

// Check if current hour falls within schedule window (handles midnight wrap).
static bool inScheduleWindow(const ScheduleConfig& sched, int hour) {
    if (sched.start_hour > sched.end_hour) {
        return hour >= sched.start_hour || hour < sched.end_hour;
    }
    return hour >= sched.start_hour && hour < sched.end_hour;
}

// Check if periodic run is active (inside window AND within run_minutes).
static bool isScheduleActive(const ScheduleConfig& sched, int hour, int minute) {
    return sched.run_minutes > 0 && inScheduleWindow(sched, hour) && minute < sched.run_minutes;
}

// Cap speed to schedule.max_speed when inside the schedule window.
static FanSpeed applyMaxSpeed(FanSpeed speed, const ScheduleConfig* sched, int hour) {
    if (!sched || sched->max_speed[0] == '\0') return speed;
    if (!inScheduleWindow(*sched, hour)) return speed;
    FanSpeed cap = speedFromStr(sched->max_speed);
    if (speed == FanSpeed::SPEED_HIGH && cap == FanSpeed::SPEED_LOW) return FanSpeed::SPEED_LOW;
    return speed;
}

// Unsigned millis() comparison that handles 49-day rollover.
static bool millisBefore(unsigned long a, unsigned long b) {
    return (long)(a - b) < 0;
}

DecisionResult decideSpeed(
    int co2_value,
    const bool* switch_states,
    int switch_count,
    const FanState& current_state,
    const ThresholdsConfig& thresholds,
    int override_minutes,
    unsigned long now_ms,
    const struct tm& now_time,
    const ScheduleConfig* schedule
) {
    FanState ns;
    ns.has_previous = true;
    for (int i = 0; i < switch_count && i < MAX_SWITCHES; i++) {
        ns.previous_switch_states[i] = switch_states[i];
    }

    unsigned long override_until = current_state.override_until_ms;

    // 1a. Any switch currently ON → HIGH (no timer)
    bool any_on = false;
    for (int i = 0; i < switch_count; i++) {
        if (switch_states[i]) { any_on = true; break; }
    }
    if (any_on) {
        ns.current_speed = FanSpeed::SPEED_HIGH;
        ns.override_until_ms = 0;
        return {FanSpeed::SPEED_HIGH, ns};
    }

    // 1b. Detect switch release (falling edge) → start cooldown timer
    if (current_state.has_previous) {
        for (int i = 0; i < switch_count && i < MAX_SWITCHES; i++) {
            if (current_state.previous_switch_states[i] && !switch_states[i]) {
                override_until = now_ms + (unsigned long)override_minutes * 60UL * 1000UL;
                break;
            }
        }
    }

    // Override still active?
    if (override_until != 0 && millisBefore(now_ms, override_until)) {
        ns.current_speed = FanSpeed::SPEED_HIGH;
        ns.override_until_ms = override_until;
        return {FanSpeed::SPEED_HIGH, ns};
    }

    // Clear expired override
    override_until = 0;

    // 2. CO2 check with hysteresis
    FanSpeed current_speed = current_state.current_speed;
    if (co2_value >= 0) {
        int eff_co2_high = thresholds.co2_high;
        int eff_co2_low = thresholds.co2_low;
        if (current_speed == FanSpeed::SPEED_HIGH) {
            eff_co2_high -= thresholds.co2_hysteresis;
        }
        if (current_speed == FanSpeed::SPEED_LOW || current_speed == FanSpeed::SPEED_HIGH) {
            eff_co2_low -= thresholds.co2_hysteresis;
        }

        FanSpeed speed = FanSpeed::SPEED_OFF;
        bool has_speed = false;
        if (co2_value > eff_co2_high) {
            speed = FanSpeed::SPEED_HIGH;
            has_speed = true;
        } else if (co2_value >= eff_co2_low) {
            speed = FanSpeed::SPEED_LOW;
            has_speed = true;
        }

        if (has_speed) {
            int hour = now_time.tm_hour;
            speed = applyMaxSpeed(speed, schedule, hour);
            ns.current_speed = speed;
            ns.override_until_ms = override_until;
            return {speed, ns};
        }
    }

    // 3. Time-based schedule
    if (schedule && isScheduleActive(*schedule, now_time.tm_hour, now_time.tm_min)) {
        FanSpeed speed = speedFromStr(schedule->speed);
        ns.current_speed = speed;
        ns.override_until_ms = override_until;
        return {speed, ns};
    }

    // 4. Default: OFF
    ns.current_speed = FanSpeed::SPEED_OFF;
    ns.override_until_ms = override_until;
    return {FanSpeed::SPEED_OFF, ns};
}
