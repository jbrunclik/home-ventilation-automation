#include "webhook_server.h"

#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>

static WebServer* server = nullptr;
static WebhookState* g_state = nullptr;
static const FanState* g_fan_state = nullptr;
static const TuyaReading* g_reading = nullptr;
static const Config* g_config = nullptr;

static void handleWebhook() {
    // Switch event: ?input_id=N&state=on|off
    if (server->hasArg("input_id") && server->hasArg("state")) {
        int input_id = server->arg("input_id").toInt();
        bool on = server->arg("state").equalsIgnoreCase("on");

        if (input_id >= 0 && input_id < MAX_SWITCH_INPUTS) {
            g_state->switch_states[input_id] = on;
            g_state->reevaluate = true;
            Serial.printf("Webhook: switch input %d → %s\n", input_id, on ? "ON" : "OFF");
        }
        server->send(200, "text/plain", "OK");
        return;
    }

    // Unknown params
    Serial.printf("Webhook: unrecognized params: %s\n", server->uri().c_str());
    server->send(200, "text/plain", "OK");
}

static void handleStatus() {
    JsonDocument doc;
    doc["uptime_seconds"] = millis() / 1000;
    doc["wifi_rssi"] = WiFi.RSSI();
    doc["fan_speed"] = fanSpeedStr(g_fan_state->current_speed);

    if (g_fan_state->override_until_ms != 0) {
        long remaining = (long)(g_fan_state->override_until_ms - millis());
        doc["override_remaining_seconds"] = remaining > 0 ? remaining / 1000 : 0;
    }

    if (g_reading->valid) {
        doc["co2_ppm"] = g_reading->co2;
        if (g_reading->temperature >= 0) doc["temperature"] = g_reading->temperature;
        if (g_reading->pm25 >= 0) doc["pm25"] = g_reading->pm25;
    }

    String json;
    serializeJsonPretty(doc, json);
    server->send(200, "application/json", json);
}

void webhookServerSetup(int port, WebhookState* state,
                        const FanState* fan_state, const TuyaReading* reading,
                        const Config* config) {
    g_state = state;
    g_fan_state = fan_state;
    g_reading = reading;
    g_config = config;

    server = new WebServer(port);
    server->on("/webhook/shelly", handleWebhook);
    server->on("/status", handleStatus);
    server->begin();
    Serial.printf("Webhook server started on port %d\n", port);
}

void webhookServerLoop() {
    if (server) server->handleClient();
}
