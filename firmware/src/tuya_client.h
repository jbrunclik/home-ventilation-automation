#pragma once

#include "config.h"

struct TuyaReading {
    int co2 = -1;           // ppm, -1 = no data
    float temperature = -1;  // celsius
    float humidity = -1;    // %, DP 19
    float pm25 = -1;        // ug/m3
    bool valid = false;
};

// Poll CO2 sensor via Tuya protocol 3.5 (TCP + AES-GCM).
// Opens a fresh TCP connection, negotiates session key, queries status, closes.
// Returns true if reading is valid.
bool tuyaPollSensor(const TuyaSensorConfig& config, TuyaReading& out);

// Configure sensor on startup: disable alarm (DP 13), dim screen (DP 17),
// disable screen sleep (DP 108).
bool tuyaConfigureSensor(const TuyaSensorConfig& config);
