#include "display.h"

#include <M5Unified.h>
#include <WiFi.h>

// Cached state to avoid unnecessary redraws
static int prev_co2 = -999;
static FanSpeed prev_speed = FanSpeed::SPEED_OFF;
static long prev_override_s = -1;  // -1 = no override
static bool prev_wifi = false;

// Catppuccin Mocha palette (RGB565)
static constexpr uint16_t COLOR_BG     = 0x18E5;  // Base #1e1e2e
static constexpr uint16_t COLOR_GREEN  = 0xA714;  // Green #a6e3a1
static constexpr uint16_t COLOR_YELLOW = 0xFF15;  // Yellow #f9e2af
static constexpr uint16_t COLOR_RED    = 0xF455;  // Red #f38ba8
static constexpr uint16_t COLOR_BLUE   = 0x8DBF;  // Blue #89b4fa
static constexpr uint16_t COLOR_GRAY   = 0xA579;  // Subtext0 #a6adc8
static constexpr uint16_t COLOR_TEXT   = 0xCEBE;  // Text #cdd6f4
static constexpr uint16_t COLOR_DIM    = 0x3188;  // Surface0 #313244

static uint16_t co2Color(int co2) {
    if (co2 < 0) return COLOR_GRAY;
    if (co2 < 800) return COLOR_GREEN;
    if (co2 <= 1200) return COLOR_YELLOW;
    return COLOR_RED;
}

static const char* speedLabel(FanSpeed speed) {
    switch (speed) {
        case FanSpeed::SPEED_HIGH: return "HIGH";
        case FanSpeed::SPEED_LOW: return "LOW";
        default: return "OFF";
    }
}

static uint16_t speedColor(FanSpeed speed) {
    switch (speed) {
        case FanSpeed::SPEED_HIGH: return COLOR_RED;
        case FanSpeed::SPEED_LOW: return COLOR_BLUE;
        default: return COLOR_DIM;
    }
}

void displaySetup() {
    M5.Display.setRotation(0);
    M5.Display.fillScreen(COLOR_BG);
    M5.Display.setTextDatum(MC_DATUM);
}

void displayUpdate(const TuyaReading& reading, const FanState& state,
                   bool wifi_connected, unsigned long now_ms) {
    long override_s = -1;
    if (state.override_until_ms != 0 &&
        (long)(now_ms - state.override_until_ms) < 0) {
        override_s = (long)(state.override_until_ms - now_ms) / 1000;
    }

    // Only redraw the bar if just the countdown second changed
    bool bar_changed = (override_s != prev_override_s) ||
                       (state.current_speed != prev_speed);
    bool full_changed = (reading.co2 != prev_co2) ||
                        (wifi_connected != prev_wifi);

    if (!bar_changed && !full_changed) return;

    prev_co2 = reading.co2;
    prev_speed = state.current_speed;
    prev_override_s = override_s;
    prev_wifi = wifi_connected;

    if (!full_changed) {
        // Partial redraw: only the fan bar
        goto draw_bar;
    }

    M5.Display.fillScreen(COLOR_BG);

    // WiFi indicator (top-left corner)
    M5.Display.setTextSize(1);
    M5.Display.setTextDatum(TL_DATUM);
    M5.Display.setTextColor(wifi_connected ? COLOR_GREEN : COLOR_RED, COLOR_BG);
    M5.Display.drawString(wifi_connected ? "WiFi" : "NO WIFI", 2, 2);

    // IP address (top-right corner)
    if (wifi_connected) {
        M5.Display.setTextDatum(TR_DATUM);
        M5.Display.setTextColor(COLOR_GRAY, COLOR_BG);
        M5.Display.drawString(WiFi.localIP().toString().c_str(), 126, 2);
    }

    // CO2 value (large, centered)
    M5.Display.setTextDatum(MC_DATUM);
    if (reading.co2 >= 0) {
        M5.Display.setTextColor(co2Color(reading.co2), COLOR_BG);
        M5.Display.setTextSize(3);
        char co2_str[8];
        snprintf(co2_str, sizeof(co2_str), "%d", reading.co2);
        M5.Display.drawString(co2_str, 64, 48);

        M5.Display.setTextSize(1);
        M5.Display.setTextColor(COLOR_GRAY, COLOR_BG);
        M5.Display.drawString("ppm", 64, 72);
    } else {
        M5.Display.setTextColor(COLOR_GRAY, COLOR_BG);
        M5.Display.setTextSize(2);
        M5.Display.drawString("---", 64, 55);
    }

draw_bar:
    // Fan speed bar (bottom area)
    int bar_y = 90;
    int bar_h = 14;
    M5.Display.fillRect(0, bar_y, 128, bar_h, speedColor(state.current_speed));
    M5.Display.setTextSize(1);
    M5.Display.setTextColor(COLOR_TEXT, speedColor(state.current_speed));
    M5.Display.setTextDatum(MC_DATUM);

    if (override_s >= 0) {
        char label[24];
        snprintf(label, sizeof(label), "MANUAL %ld:%02ld",
                 override_s / 60, override_s % 60);
        M5.Display.drawString(label, 64, bar_y + bar_h / 2);
    } else {
        char label[16];
        snprintf(label, sizeof(label), "FAN %s", speedLabel(state.current_speed));
        M5.Display.drawString(label, 64, bar_y + bar_h / 2);
    }

    // Temperature (small, bottom)
    if (reading.temperature >= 0) {
        M5.Display.setTextDatum(BL_DATUM);
        M5.Display.setTextColor(COLOR_GRAY, COLOR_BG);
        M5.Display.setTextSize(1);
        char temp_str[16];
        snprintf(temp_str, sizeof(temp_str), "%.0fC", reading.temperature);
        M5.Display.drawString(temp_str, 2, 126);
    }

    // PM2.5 (small, bottom-right)
    if (reading.pm25 >= 0) {
        M5.Display.setTextDatum(BR_DATUM);
        M5.Display.setTextColor(COLOR_GRAY, COLOR_BG);
        M5.Display.setTextSize(1);
        char pm_str[16];
        snprintf(pm_str, sizeof(pm_str), "PM%.0f", reading.pm25);
        M5.Display.drawString(pm_str, 126, 126);
    }
}
