#pragma once

#include "config.h"
#include "fan_logic.h"

// Set fan speed via Shelly 2PM cover mode (Stop first, 500ms delay, then Open/Close).
bool shellySetFanSpeed(const char* host, FanSpeed speed);

// Re-issue current cover command without Stop (reconciliation).
bool shellyRefreshFanSpeed(const char* host, FanSpeed speed);

// Read switch input states from Shelly. Returns count of states read.
int shellyGetSwitchInputs(const char* host, bool* states, int count);

// Configure cover: detached + locked, maxtime 300s.
bool shellyConfigureCover(const char* host);

// Ensure both inputs are type "switch" for toggle events.
bool shellyConfigureInputs(const char* host);

// Reconcile webhooks: create missing, fix wrong URLs, delete stale.
bool shellyConfigureWebhooks(const char* host, const int* switch_inputs,
                             int input_count, const char* esp_ip, int port);

// Stop and delete all scripts from the Shelly (removes cover-switch-override.js etc).
bool shellyRemoveScripts(const char* host);
