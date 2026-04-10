#!/usr/bin/env python3
"""Convert a single-fan TOML config to ESP32 JSON config format.

Usage: python toml2json.py config.toml [fan_name] > firmware/data/config.json

If fan_name is omitted and there's only one fan, it's used automatically.
WiFi credentials are prompted interactively (not stored in TOML).
"""

import json
import sys
import tomllib
from pathlib import Path


def convert(toml_path: str, fan_name: str | None = None) -> dict:
    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    fans = raw.get("fans", {})
    if not fans:
        raise SystemExit("No fans found in config")

    if fan_name is None:
        if len(fans) == 1:
            fan_name = next(iter(fans))
        else:
            names = ", ".join(fans.keys())
            raise SystemExit(f"Multiple fans found ({names}). Specify one as the second argument.")

    fan = fans[fan_name]

    # Thresholds (CO2 only for ESP32)
    thr = raw.get("thresholds", {})

    # CO2 sensor (first one, or the only one)
    sensors = fan.get("co2_sensors", {})
    co2_sensor = None
    if sensors:
        name, data = next(iter(sensors.items()))
        co2_sensor = {
            "device_id": data["device_id"],
            "ip": data["ip"],
            "local_key": data["local_key"],
        }

    # Schedule
    sched_raw = fan.get("schedule")
    schedule = None
    if sched_raw:
        schedule = {
            "start_hour": sched_raw.get("start_hour", 22),
            "end_hour": sched_raw.get("end_hour", 7),
            "run_minutes": sched_raw.get("run_minutes", 10),
            "speed": sched_raw.get("speed", "low"),
            "max_speed": sched_raw.get("max_speed", ""),
        }

    result = {
        "wifi_ssid": "CHANGE_ME",
        "wifi_password": "CHANGE_ME",
        "timezone": "CET-1CEST,M3.5.0,M10.5.0/3",
        "poll_interval_seconds": raw.get("poll_interval_seconds", 30),
        "reconciliation_interval_seconds": raw.get("reconciliation_interval_seconds", 60),
        "manual_override_minutes": raw.get("manual_override_minutes", 10),
        "webhook_port": raw.get("webhook_port", 8090),
        "thresholds": {
            "co2_low": thr.get("co2_low", 800),
            "co2_high": thr.get("co2_high", 1200),
            "co2_hysteresis": thr.get("co2_hysteresis", 50),
        },
        "shelly_host": fan.get("shelly_host", ""),
        "switch_inputs": fan.get("switch_inputs", []),
    }

    if co2_sensor:
        result["co2_sensor"] = co2_sensor
    if schedule:
        result["schedule"] = schedule

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(1)

    toml_path = sys.argv[1]
    fan_name = sys.argv[2] if len(sys.argv) > 2 else None
    result = convert(toml_path, fan_name)
    print(json.dumps(result, indent=2))
