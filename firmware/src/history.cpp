#include "history.h"

void History::record(const TuyaReading& reading, FanSpeed speed, unsigned long uptime_s) {
    HistoryEntry entry;
    entry.uptime_s = uptime_s;
    entry.co2 = reading.co2;
    entry.temperature = reading.temperature;
    entry.humidity = reading.humidity;
    entry.pm25 = reading.pm25;
    entry.fan_on = (speed != FanSpeed::SPEED_OFF);
    _buf[_head] = entry;
    _head = (_head + 1) % HISTORY_SIZE;
    if (_count < HISTORY_SIZE) _count++;
}

const HistoryEntry& History::get(int i) const {
    int idx = (_count < HISTORY_SIZE) ? i : (_head + i) % HISTORY_SIZE;
    return _buf[idx];
}
