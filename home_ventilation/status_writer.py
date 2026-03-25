import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from home_ventilation.config import FanConfig
from home_ventilation.models import FanState, TuyaSensorReading
from home_ventilation.sensor_cache import SensorCache

logger = logging.getLogger(__name__)


def write_status(
    path: str,
    fan_configs: list[FanConfig],
    fan_states: dict[str, FanState],
    cached_readings: dict[str, list[TuyaSensorReading | None]],
    sensor_cache: SensorCache,
    now: datetime,
) -> None:
    """Write a JSON status snapshot for external consumers (e.g. dashboard).

    Uses atomic write (write to temp file then rename) to prevent readers
    from seeing partial data.
    """
    fans = []
    for fan_cfg in fan_configs:
        state = fan_states.get(fan_cfg.name)
        speed = state.current_speed.value if state else "off"

        # Average humidity across all sensors for this fan
        humidity = None
        hum_values = [sensor_cache.get_humidity(ip, now) for ip in fan_cfg.humidity_sensor_ips]
        valid_hum = [v for v in hum_values if v is not None]
        if valid_hum:
            humidity = round(sum(valid_hum) / len(valid_hum), 1)

        entry: dict = {"label": fan_cfg.label, "speed": speed}
        if humidity is not None:
            entry["humidity"] = humidity
        fans.append(entry)

    sensors = []
    for fan_cfg in fan_configs:
        readings = cached_readings.get(fan_cfg.name, [])
        for i, sensor in enumerate(fan_cfg.co2_sensors):
            reading = readings[i] if i < len(readings) else None
            if reading is None:
                continue
            entry: dict = {"label": sensor.label}
            if reading.co2 is not None:
                entry["ppm"] = reading.co2
            if reading.temperature is not None:
                entry["temperature"] = reading.temperature
            if reading.humidity is not None:
                entry["humidity"] = reading.humidity
            if reading.pm25 is not None:
                entry["pm25"] = reading.pm25
            if len(entry) > 1:  # has data beyond label
                sensors.append(entry)

    status = {
        "fans": fans,
        "sensors": sensors,
        "updated_at": now.astimezone(timezone.utc).isoformat(),
    }

    target = Path(path)
    try:
        # Atomic write: temp file in same directory, then rename
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp", prefix=".status-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(status, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        except BaseException:
            # Clean up temp file on any error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:
        logger.warning("Failed to write status to %s", path, exc_info=True)
