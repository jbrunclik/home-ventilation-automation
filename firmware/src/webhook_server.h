#pragma once

#include "config.h"
#include "fan_logic.h"
#include "tuya_client.h"

// Shared state between webhook server and main loop
struct WebhookState {
    volatile bool reevaluate = false;
    bool switch_states[MAX_SWITCH_INPUTS] = {};
};

void webhookServerSetup(int port, WebhookState* state,
                        const FanState* fan_state, const TuyaReading* reading,
                        const Config* config);
void webhookServerLoop();
