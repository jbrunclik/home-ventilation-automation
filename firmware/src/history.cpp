#include "history.h"

void History::record(const TuyaReading& reading, FanSpeed speed, unsigned long uptime_s) {
    _buf[_head] = {uptime_s, reading.co2, reading.temperature,
                   reading.humidity, reading.pm25, speed != FanSpeed::SPEED_OFF};
    _head = (_head + 1) % HISTORY_SIZE;
    if (_count < HISTORY_SIZE) _count++;
}

const HistoryEntry& History::get(int i) const {
    int idx = (_count < HISTORY_SIZE) ? i : (_head + i) % HISTORY_SIZE;
    return _buf[idx];
}
