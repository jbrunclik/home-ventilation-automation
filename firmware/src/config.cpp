#include "config.h"

#include <ArduinoJson.h>
#include <LittleFS.h>

static void copyStr(const char* src, char* dst, size_t maxLen) {
    strncpy(dst, src, maxLen - 1);
    dst[maxLen - 1] = '\0';
}

bool loadConfig(Config& config) {
    if (!LittleFS.begin(true)) {
        Serial.println("Failed to mount LittleFS");
        return false;
    }

    File file = LittleFS.open("/config.json", "r");
    if (!file) {
        Serial.println("Failed to open /config.json");
        return false;
    }

    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, file);
    file.close();

    if (err) {
        Serial.printf("JSON parse error: %s\n", err.c_str());
        return false;
    }

    // WiFi
    copyStr(doc["wifi_ssid"] | "", config.wifi_ssid, sizeof(config.wifi_ssid));
    copyStr(doc["wifi_password"] | "", config.wifi_password, sizeof(config.wifi_password));
    copyStr(doc["timezone"] | "CET-1CEST,M3.5.0,M10.5.0/3", config.timezone, sizeof(config.timezone));

    // Timing
    config.poll_interval_seconds = doc["poll_interval_seconds"] | 30;
    config.reconciliation_interval_seconds = doc["reconciliation_interval_seconds"] | 60;
    config.manual_override_minutes = doc["manual_override_minutes"] | 10;
    config.webhook_port = doc["webhook_port"] | 8090;
    config.display_rotation = doc["display_rotation"] | 0;

    // Thresholds
    JsonObject thr = doc["thresholds"];
    if (thr) {
        config.thresholds.co2_low = thr["co2_low"] | 800;
        config.thresholds.co2_high = thr["co2_high"] | 1200;
        config.thresholds.co2_hysteresis = thr["co2_hysteresis"] | 50;
    }

    // Shelly
    copyStr(doc["shelly_host"] | "", config.shelly_host, sizeof(config.shelly_host));

    // Switch inputs
    JsonArray inputs = doc["switch_inputs"];
    config.switch_input_count = 0;
    if (inputs) {
        for (JsonVariant v : inputs) {
            if (config.switch_input_count < MAX_SWITCH_INPUTS) {
                config.switch_inputs[config.switch_input_count++] = v.as<int>();
            }
        }
    }

    // CO2 sensor
    JsonObject sensor = doc["co2_sensor"];
    if (sensor) {
        copyStr(sensor["device_id"] | "", config.co2_sensor.device_id,
                sizeof(config.co2_sensor.device_id));
        copyStr(sensor["ip"] | "", config.co2_sensor.ip, sizeof(config.co2_sensor.ip));
        copyStr(sensor["local_key"] | "", config.co2_sensor.local_key,
                sizeof(config.co2_sensor.local_key));
        config.has_co2_sensor = config.co2_sensor.device_id[0] != '\0';
    }

    // Schedule
    JsonObject sched = doc["schedule"];
    if (sched) {
        config.schedule.start_hour = sched["start_hour"] | 22;
        config.schedule.end_hour = sched["end_hour"] | 7;
        config.schedule.run_minutes = sched["run_minutes"] | 10;
        copyStr(sched["speed"] | "low", config.schedule.speed, sizeof(config.schedule.speed));
        copyStr(sched["max_speed"] | "", config.schedule.max_speed,
                sizeof(config.schedule.max_speed));
        config.has_schedule = true;
    }

    return true;
}

