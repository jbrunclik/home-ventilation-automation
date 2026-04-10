#include "webhook_server.h"

#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>

static WebServer* server = nullptr;
static WebhookState* g_state = nullptr;
static const FanState* g_fan_state = nullptr;
static const TuyaReading* g_reading = nullptr;
static const History* g_history = nullptr;
static const Config* g_config = nullptr;

#include "html_page.h"

// HTML_PAGE is auto-generated from web/index.html by scripts/embed_html.py

static void handleRoot() {
    server->send_P(200, "text/html", HTML_PAGE);
}

static void handleControl() {
    if (!server->hasArg("action")) {
        server->send(400, "text/plain", "Missing action");
        return;
    }
    String action = server->arg("action");
    if (action == "on") {
        g_state->pending_action = PendingAction::OFF_COOLDOWN;
    } else if (action == "cancel") {
        g_state->pending_action = PendingAction::OFF_IMMEDIATE;
    } else {
        server->send(400, "text/plain", "Unknown action");
        return;
    }
    g_state->reevaluate = true;
    Serial.printf("Control: action=%s\n", action.c_str());
    server->send(200, "text/plain", "OK");
}

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
        if (g_reading->humidity >= 0) doc["humidity"] = g_reading->humidity;
        if (g_reading->pm25 >= 0) doc["pm25"] = g_reading->pm25;
    }

    bool sw_active = false;
    for (int i = 0; i < g_config->switch_input_count; i++) {
        if (g_state->switch_states[i]) { sw_active = true; break; }
    }
    doc["switch_active"] = sw_active;

    String json;
    serializeJsonPretty(doc, json);
    server->send(200, "application/json", json);
}


static void handleHistory() {
    // Build JSON manually to avoid large ArduinoJson allocation
    String json;
    json.reserve(g_history->size() * 68 + 64);
    json += "{\"interval_s\":";
    json += HISTORY_INTERVAL_S;
    json += ",\"count\":";
    json += g_history->size();
    json += ",\"entries\":[";
    for (int i = 0; i < g_history->size(); i++) {
        const HistoryEntry& e = g_history->get(i);
        if (i > 0) json += ',';
        json += "{\"t\":";
        json += e.uptime_s;
        if (e.co2 >= 0) { json += ",\"co2\":"; json += e.co2; }
        if (e.temperature >= 0) { json += ",\"temp\":"; json += e.temperature; }
        if (e.humidity >= 0) { json += ",\"hum\":"; json += e.humidity; }
        if (e.pm25 >= 0) { json += ",\"pm25\":"; json += e.pm25; }
        json += ",\"fan\":";
        json += String(e.fan_speed);
        json += '}';
    }
    json += "]}";
    server->send(200, "application/json", json);
}

void webhookServerSetup(int port, WebhookState* state,
                        const FanState* fan_state, const TuyaReading* reading,
                        const History* history, const Config* config) {
    g_state = state;
    g_fan_state = fan_state;
    g_reading = reading;
    g_history = history;
    g_config = config;

    server = new WebServer(port);
    server->on("/", handleRoot);
    server->on("/api/control", HTTP_POST, handleControl);
    server->on("/api/history", handleHistory);
    server->on("/webhook/shelly", handleWebhook);
    server->on("/status", handleStatus);
    server->begin();
    Serial.printf("Webhook server started on port %d\n", port);
}

void webhookServerLoop() {
    if (server) server->handleClient();
}
