#include "display.h"

#include <M5Unified.h>
#include <WiFi.h>

static M5Canvas canvas(&M5.Display);

// Cached state to avoid unnecessary redraws
static int prev_co2 = -999;
static FanSpeed prev_speed = FanSpeed::SPEED_OFF;
static long prev_override_s = -1;  // -1 = no override
static int prev_rssi = 1;  // impossible value to force first draw
static int prev_hist_count = -1;

// Catppuccin Mocha palette (RGB565)
static constexpr uint16_t COLOR_BG     = TFT_BLACK;
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

void displaySetup(int rotation) {
    M5.Display.setRotation(rotation);
    M5.Display.fillScreen(COLOR_BG);
    canvas.createSprite(128, 128);
    canvas.setTextDatum(MC_DATUM);
}

static void drawSparkline(const History& history, int x, int y, int w, int h) {
    int n = history.size();
    if (n < 2) return;

    // Find min/max for scaling
    int mn = 9999, mx = 0;
    for (int i = 0; i < n; i++) {
        int v = history.get(i).co2;
        if (v < 0) continue;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
    }
    if (mx <= mn) { mx = mn + 100; }

    // Draw filled area from bottom up
    for (int i = 0; i < n; i++) {
        int v = history.get(i).co2;
        if (v < 0) continue;
        int px = x + (i * (w - 1)) / (n - 1);
        int bar_h = ((v - mn) * (h - 2)) / (mx - mn);
        if (bar_h < 1) bar_h = 1;
        int bar_top = y + h - bar_h;
        canvas.drawFastVLine(px, bar_top, bar_h, 0x422B);  // Surface1 #45475a
    }
}

// RSSI to 0-4 bar count: 0=disconnected, 1=weak, 4=excellent
static int rssiToBars(int rssi) {
    if (rssi == 0) return 0;    // disconnected
    if (rssi >= -55) return 4;  // excellent
    if (rssi >= -67) return 3;  // good
    if (rssi >= -75) return 2;  // fair
    return 1;                   // weak
}

static void drawRssiBars(int rssi) {
    int bars = rssiToBars(rssi);
    int x = 1, y = 2;
    uint16_t active = bars >= 3 ? COLOR_GREEN : (bars == 2 ? COLOR_YELLOW : COLOR_RED);
    for (int i = 0; i < 4; i++) {
        int bar_h = 3 + i * 2;  // heights: 3, 5, 7, 9
        int bar_y = y + (9 - bar_h);
        uint16_t color = (i < bars) ? active : COLOR_DIM;
        canvas.fillRect(x + i * 4, bar_y, 3, bar_h, color);
    }
}

void displayUpdate(const TuyaReading& reading, const FanState& state,
                   int wifi_rssi, unsigned long now_ms,
                   const History& history) {
    long override_s = -1;
    if (state.override_until_ms != 0 &&
        (long)(now_ms - state.override_until_ms) < 0) {
        override_s = (long)(state.override_until_ms - now_ms) / 1000;
    }

    // Only redraw the bar if just the countdown second changed
    bool bar_changed = (override_s != prev_override_s) ||
                       (state.current_speed != prev_speed);
    bool full_changed = (reading.co2 != prev_co2) ||
                        (rssiToBars(wifi_rssi) != rssiToBars(prev_rssi)) ||
                        (history.size() != prev_hist_count);

    if (!bar_changed && !full_changed) return;

    prev_co2 = reading.co2;
    prev_speed = state.current_speed;
    prev_override_s = override_s;
    prev_rssi = wifi_rssi;
    prev_hist_count = history.size();

    // Compose entire frame in sprite, then push once (no flicker)
    canvas.fillSprite(COLOR_BG);

    // CO2 sparkline behind the reading (y: 14..85)
    drawSparkline(history, 0, 14, 128, 72);

    // WiFi RSSI bars (top-left) + IP address (top-right)
    drawRssiBars(wifi_rssi);
    if (wifi_rssi != 0) {
        canvas.setTextSize(1);
        canvas.setTextDatum(TR_DATUM);
        canvas.setTextColor(COLOR_GRAY, COLOR_BG);
        canvas.drawString(WiFi.localIP().toString().c_str(), 126, 2);
    }

    // CO2 value (large, centered)
    canvas.setTextDatum(MC_DATUM);
    if (reading.co2 >= 0) {
        canvas.setTextColor(co2Color(reading.co2), COLOR_BG);
        canvas.setTextSize(3);
        char co2_str[8];
        snprintf(co2_str, sizeof(co2_str), "%d", reading.co2);
        canvas.drawString(co2_str, 64, 48);

        canvas.setTextSize(1);
        canvas.setTextColor(COLOR_GRAY, COLOR_BG);
        canvas.drawString("ppm", 64, 72);
    } else {
        canvas.setTextColor(COLOR_GRAY, COLOR_BG);
        canvas.setTextSize(2);
        canvas.drawString("---", 64, 55);
    }

    // Fan speed bar (bottom area)
    int bar_y = 90;
    int bar_h = 14;
    canvas.fillRect(0, bar_y, 128, bar_h, speedColor(state.current_speed));
    canvas.setTextSize(1);
    canvas.setTextColor(COLOR_TEXT, speedColor(state.current_speed));
    canvas.setTextDatum(MC_DATUM);

    if (override_s >= 0) {
        char label[24];
        snprintf(label, sizeof(label), "MANUAL %ld:%02ld",
                 override_s / 60, override_s % 60);
        canvas.drawString(label, 64, bar_y + bar_h / 2);
    } else {
        char label[16];
        snprintf(label, sizeof(label), "FAN %s", speedLabel(state.current_speed));
        canvas.drawString(label, 64, bar_y + bar_h / 2);
    }

    // Temperature (small, bottom)
    if (reading.temperature >= 0) {
        canvas.setTextDatum(BL_DATUM);
        canvas.setTextColor(COLOR_GRAY, COLOR_BG);
        canvas.setTextSize(1);
        char temp_str[16];
        snprintf(temp_str, sizeof(temp_str), "%.0fC", reading.temperature);
        canvas.drawString(temp_str, 2, 126);
    }

    // PM2.5 (small, bottom-right)
    if (reading.pm25 >= 0) {
        canvas.setTextDatum(BR_DATUM);
        canvas.setTextColor(COLOR_GRAY, COLOR_BG);
        canvas.setTextSize(1);
        char pm_str[16];
        snprintf(pm_str, sizeof(pm_str), "PM%.0f", reading.pm25);
        canvas.drawString(pm_str, 126, 126);
    }

    canvas.pushSprite(0, 0);
}
