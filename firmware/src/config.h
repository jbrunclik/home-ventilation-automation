#pragma once

#include <cstdint>

static constexpr int MAX_SWITCH_INPUTS = 2;

struct ThresholdsConfig {
    int co2_low = 800;
    int co2_high = 1200;
    int co2_hysteresis = 50;
};

struct TuyaSensorConfig {
    char device_id[32] = {};
    char ip[16] = {};
    char local_key[20] = {};  // 16 chars + null
};

struct ScheduleConfig {
    int start_hour = 22;
    int end_hour = 7;
    int run_minutes = 10;
    char speed[8] = "low";
    char max_speed[8] = "";
};

struct Config {
    char wifi_ssid[64] = {};
    char wifi_password[64] = {};
    char timezone[64] = "CET-1CEST,M3.5.0,M10.5.0/3";
    int poll_interval_seconds = 30;
    int reconciliation_interval_seconds = 60;
    int manual_override_minutes = 10;
    int webhook_port = 8090;
    ThresholdsConfig thresholds;
    char shelly_host[16] = {};
    int switch_inputs[MAX_SWITCH_INPUTS] = {};
    int switch_input_count = 0;
    TuyaSensorConfig co2_sensor;
    bool has_co2_sensor = false;
    ScheduleConfig schedule;
    bool has_schedule = false;
};

// Load config from /config.json on LittleFS. Returns true on success.
bool loadConfig(Config& config);
