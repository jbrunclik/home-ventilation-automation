#pragma once

#include "config.h"
#include "fan_logic.h"
#include "history.h"
#include "tuya_client.h"

enum class PendingAction { NONE, TURN_ON, OFF_COOLDOWN, OFF_IMMEDIATE };

// Shared state between webhook server and main loop
struct WebhookState {
    volatile bool reevaluate = false;
    bool switch_states[MAX_SWITCH_INPUTS] = {};
    volatile PendingAction pending_action = PendingAction::NONE;
};

void webhookServerSetup(int port, WebhookState* state,
                        const FanState* fan_state, const TuyaReading* reading,
                        const History* history, const Config* config);
void webhookServerLoop();
