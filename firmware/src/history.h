#pragma once

#include "fan_logic.h"
#include "tuya_client.h"

static constexpr int HISTORY_SIZE = 144;          // entries in circular buffer
static constexpr int HISTORY_INTERVAL_S = 300;    // record every 5 minutes

struct HistoryEntry {
    unsigned long uptime_s = 0;
    int co2 = -1;
    float temperature = -1;
    float humidity = -1;
    float pm25 = -1;
    uint8_t fan_speed = 0;  // 0=off, 1=low, 2=high
};

class History {
   public:
    void record(const TuyaReading& reading, FanSpeed speed, unsigned long uptime_s);
    int size() const { return _count; }
    // Index 0 = oldest, size()-1 = newest
    const HistoryEntry& get(int i) const;

   private:
    HistoryEntry _buf[HISTORY_SIZE];
    int _head = 0;
    int _count = 0;
};
