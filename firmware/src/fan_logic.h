#pragma once

#include <cstdint>
#include <ctime>

#include "config.h"

enum class FanSpeed : uint8_t { SPEED_OFF, SPEED_LOW, SPEED_HIGH };

const char* fanSpeedStr(FanSpeed speed);

static constexpr int MAX_SWITCHES = MAX_SWITCH_INPUTS;

struct FanState {
    FanSpeed current_speed = FanSpeed::SPEED_OFF;
    unsigned long override_until_ms = 0;  // millis() timestamp, 0 = no override
    bool previous_switch_states[MAX_SWITCHES] = {};
    bool has_previous = false;
};

struct DecisionResult {
    FanSpeed speed;
    FanState new_state;
};

// Pure decision logic — no I/O. Port of fan.py:decide_speed().
// Priority: switch ON → override cooldown → CO2 → schedule → OFF
DecisionResult decideSpeed(
    int co2_value,                      // -1 = no reading
    const bool* switch_states,          // array of switch states
    int switch_count,                   // number of switches
    const FanState& current_state,
    const ThresholdsConfig& thresholds,
    int override_minutes,
    unsigned long now_ms,               // millis()
    const struct tm& now_time,          // wall clock for schedule
    const ScheduleConfig* schedule      // nullptr = no schedule
);
