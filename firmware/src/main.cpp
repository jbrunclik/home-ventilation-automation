#include <ArduinoOTA.h>
#include <M5Unified.h>
#include <WiFi.h>
#include <time.h>

#include "config.h"
#include "display.h"
#include "fan_logic.h"
#include "history.h"
#include "shelly_client.h"
#include "tuya_client.h"
#include "webhook_server.h"

static Config config;
static FanState fan_state;
static TuyaReading last_reading;
static WebhookState webhook_state;
static History history;

static unsigned long last_sensor_poll = 0;
static unsigned long last_command_time = 0;
static unsigned long last_history_record = 0;
static bool first_loop = true;

// Button state for M5Stack physical button
static unsigned long btn_press_start = 0;
static bool btn_was_pressed = false;
static bool btn_long_fired = false;

static void connectWiFi() {
    Serial.printf("Connecting to %s", config.wifi_ssid);
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setTextDatum(MC_DATUM);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(TFT_WHITE);
    M5.Display.drawString("Connecting...", 64, 55);

    WiFi.mode(WIFI_STA);
    WiFi.begin(config.wifi_ssid, config.wifi_password);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 60) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\nConnected: %s\n", WiFi.localIP().toString().c_str());
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.drawString(WiFi.localIP().toString().c_str(), 64, 55);
        delay(1000);
    } else {
        Serial.println("\nWiFi connection failed!");
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setTextColor(TFT_RED);
        M5.Display.drawString("WiFi FAILED", 64, 55);
        delay(3000);
        ESP.restart();
    }
}

static void syncNTP() {
    configTzTime(config.timezone, "pool.ntp.org", "time.nist.gov");
    Serial.print("Waiting for NTP sync");
    struct tm timeinfo;
    int attempts = 0;
    while (!getLocalTime(&timeinfo) && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    if (getLocalTime(&timeinfo)) {
        Serial.printf("\nTime: %02d:%02d:%02d\n",
                      timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    } else {
        Serial.println("\nNTP sync failed (schedule will be disabled until synced)");
    }
}

static void setupOTA() {
    ArduinoOTA.setHostname("ventilation");
    ArduinoOTA.onStart([]() {
        Serial.println("OTA update starting...");
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setTextDatum(MC_DATUM);
        M5.Display.setTextSize(1);
        M5.Display.setTextColor(TFT_YELLOW);
        M5.Display.drawString("OTA UPDATE", 64, 55);
    });
    ArduinoOTA.onEnd([]() { Serial.println("\nOTA done"); });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        Serial.printf("OTA: %u%%\r", (progress / (total / 100)));
    });
    ArduinoOTA.onError([](ota_error_t error) {
        Serial.printf("OTA error[%u]\n", error);
    });
    ArduinoOTA.begin();
}

static void configureDevices() {
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setTextDatum(MC_DATUM);
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(TFT_WHITE);
    M5.Display.drawString("Configuring...", 64, 55);

    if (config.shelly_host[0]) {
        // Remove any existing scripts (e.g. cover-switch-override.js)
        shellyRemoveScripts(config.shelly_host);

        // Configure cover mode
        shellyConfigureCover(config.shelly_host);
        shellyConfigureInputs(config.shelly_host);

        // Configure webhooks pointing to this ESP32
        String my_ip = WiFi.localIP().toString();
        shellyConfigureWebhooks(config.shelly_host, config.switch_inputs,
                                config.switch_input_count,
                                my_ip.c_str(), config.webhook_port);

        // Seed initial switch states
        bool states[MAX_SWITCH_INPUTS] = {};
        shellyGetSwitchInputs(config.shelly_host, states, config.switch_input_count);
        for (int i = 0; i < config.switch_input_count; i++) {
            webhook_state.switch_states[config.switch_inputs[i]] = states[i];
        }
    }

    if (config.has_co2_sensor) {
        tuyaConfigureSensor(config.co2_sensor);
    }
}

void setup() {
    auto cfg = M5.config();
    M5.begin(cfg);

    Serial.begin(115200);
    Serial.println("\n=== Ventilation Controller ===");

    displaySetup();

    // Load config
    if (!loadConfig(config)) {
        Serial.println("FATAL: failed to load config");
        M5.Display.fillScreen(TFT_BLACK);
        M5.Display.setTextDatum(MC_DATUM);
        M5.Display.setTextColor(TFT_RED);
        M5.Display.setTextSize(1);
        M5.Display.drawString("CONFIG ERROR", 64, 55);
        while (true) delay(1000);
    }
    Serial.println("Config loaded");

    connectWiFi();
    syncNTP();
    setupOTA();
    configureDevices();

    // Start webhook server
    webhookServerSetup(config.webhook_port, &webhook_state,
                       &fan_state, &last_reading, &history, &config);

    Serial.println("Ready");
}

void loop() {
    M5.update();
    ArduinoOTA.handle();
    webhookServerLoop();

    unsigned long now = millis();

    // Physical button handling
    // Short press: OFF→ON, ON→off with cooldown
    // Long press (3s): ON→off immediately
    bool btn_down = M5.BtnA.isPressed();
    if (btn_down && !btn_was_pressed) {
        btn_press_start = now;
        btn_long_fired = false;
    }
    if (btn_down && !btn_long_fired && (now - btn_press_start) >= 3000) {
        // Long press — ignored (no action)
        btn_long_fired = true;
    }
    if (!btn_down && btn_was_pressed && !btn_long_fired) {
        // Short press: toggle between cooldown and auto
        if (fan_state.override_until_ms != 0) {
            webhook_state.pending_action = PendingAction::OFF_IMMEDIATE;
            Serial.println("Button: short press → cancel cooldown");
        } else {
            webhook_state.pending_action = PendingAction::OFF_COOLDOWN;
            Serial.println("Button: short press → on with cooldown");
        }
        webhook_state.reevaluate = true;
    }
    btn_was_pressed = btn_down;

    // Sensor poll
    bool sensor_updated = false;
    unsigned long poll_interval_ms = (unsigned long)config.poll_interval_seconds * 1000UL;
    if (first_loop || (now - last_sensor_poll) >= poll_interval_ms) {
        if (config.has_co2_sensor) {
            TuyaReading reading;
            if (tuyaPollSensor(config.co2_sensor, reading)) {
                last_reading = reading;
                sensor_updated = true;
            }
        }
        last_sensor_poll = now;
    }

    // Reconciliation check
    unsigned long reconciliation_ms = (unsigned long)config.reconciliation_interval_seconds * 1000UL;
    bool reconciliation_due = (now - last_command_time) >= reconciliation_ms;

    // Apply pending action from button or web control
    if (webhook_state.pending_action != PendingAction::NONE) {
        switch (webhook_state.pending_action) {
            case PendingAction::OFF_COOLDOWN:
                fan_state.override_until_ms =
                    now + (unsigned long)config.manual_override_minutes * 60UL * 1000UL;
                break;
            case PendingAction::OFF_IMMEDIATE:
                fan_state.override_until_ms = 0;
                break;
            default: break;
        }
        webhook_state.pending_action = PendingAction::NONE;
    }

    // Evaluate decision logic
    if (first_loop || sensor_updated || webhook_state.reevaluate || reconciliation_due) {
        struct tm timeinfo;
        bool has_time = getLocalTime(&timeinfo);

        // Build switch states array for the configured inputs
        bool switches[MAX_SWITCH_INPUTS] = {};
        for (int i = 0; i < config.switch_input_count; i++) {
            int id = config.switch_inputs[i];
            if (id >= 0 && id < MAX_SWITCH_INPUTS) {
                switches[i] = webhook_state.switch_states[id];
            }
        }

        struct tm empty_time = {};
        DecisionResult result = decideSpeed(
            last_reading.valid ? last_reading.co2 : -1,
            switches,
            config.switch_input_count,
            fan_state,
            config.thresholds,
            config.manual_override_minutes,
            now,
            has_time ? timeinfo : empty_time,
            config.has_schedule ? &config.schedule : nullptr
        );

        bool speed_changed = (result.speed != fan_state.current_speed);

        if (config.shelly_host[0] && (speed_changed || reconciliation_due)) {
            if (speed_changed) {
                Serial.printf("Speed: %s → %s\n",
                              fanSpeedStr(fan_state.current_speed),
                              fanSpeedStr(result.speed));
                shellySetFanSpeed(config.shelly_host, result.speed);
            } else {
                shellyRefreshFanSpeed(config.shelly_host, result.speed);
            }
            last_command_time = now;
        }

        fan_state = result.new_state;
        webhook_state.reevaluate = false;
        first_loop = false;
    }

    // Record history every HISTORY_INTERVAL_S seconds
    if (last_reading.valid &&
        (last_history_record == 0 ||
         (now - last_history_record) >= (unsigned long)HISTORY_INTERVAL_S * 1000UL)) {
        history.record(last_reading, fan_state.current_speed, now / 1000UL);
        last_history_record = now;
    }

    // Update display
    displayUpdate(last_reading, fan_state, WiFi.status() == WL_CONNECTED, now);
}
