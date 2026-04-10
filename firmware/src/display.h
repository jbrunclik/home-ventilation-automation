#pragma once

#include "fan_logic.h"
#include "history.h"
#include "tuya_client.h"

void displaySetup(int rotation = 0);

// Update display with current state. Only redraws on change.
// wifi_rssi: current RSSI in dBm, or 0 if disconnected.
void displayUpdate(const TuyaReading& reading, const FanState& state,
                   int wifi_rssi, unsigned long now_ms,
                   const History& history);
