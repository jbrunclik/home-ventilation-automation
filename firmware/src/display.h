#pragma once

#include "fan_logic.h"
#include "tuya_client.h"

void displaySetup();

// Update display with current state. Only redraws on change.
void displayUpdate(const TuyaReading& reading, const FanState& state,
                   bool wifi_connected, unsigned long now_ms);
