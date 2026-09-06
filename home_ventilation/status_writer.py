import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from home_ventilation.config import FanConfig
from home_ventilation.models import FanState, TuyaSensorReading
from home_ventilation.reading_cache import ReadingCache
from home_ventilation.sensor_cache import SensorCache

logger = logging.getLogger(__name__)


STATUS_VERSION = 2


def _fan_humidity(
    fan_cfg: FanConfig, sensor_cache: SensorCache, now: datetime
) -> tuple[float, datetime, bool] | None:
    """Pick the humidity reading to report for a fan, with its age.

    Prefers the highest fresh reading, matching the decision logic in fan.py.
    When every sensor is stale it reports the most recent one anyway, flagged —
    a sensor that died three hours ago should read as stale, not vanish.
    """
    readings = [
        (ip, reading)
        for ip, reading in (
            (ip, sensor_cache.get_reading(ip)) for ip in fan_cfg.humidity_sensor_ips
        )
        if reading is not None
    ]
    if not readings:
        return None

    fresh = [(ip, r) for ip, r in readings if not sensor_cache.is_stale(ip, now)]
    if fresh:
        _, chosen = max(fresh, key=lambda pair: pair[1].humidity)
        return round(chosen.humidity, 1), chosen.timestamp, False

    _, chosen = max(readings, key=lambda pair: pair[1].timestamp)
    return round(chosen.humidity, 1), chosen.timestamp, True


def write_status(
    path: str,
    fan_configs: list[FanConfig],
    fan_states: dict[str, FanState],
    cached_readings: dict[str, list[TuyaSensorReading | None]],
    sensor_cache: SensorCache,
    reading_cache: ReadingCache,
    now: datetime,
) -> None:
    """Write a JSON status snapshot for external consumers (e.g. dashboard).

    Uses atomic write (write to temp file then rename) to prevent readers
    from seeing partial data.

    Every configured sensor appears in the output, always — a sensor that has
    never been read is reported as stale rather than omitted, so consumers can
    tell a dead sensor from one that was never configured. An absent value key
    means "no reading"; a value is never emitted as 0 to mean missing.
    """
    fans = []
    for fan_cfg in fan_configs:
        state = fan_states.get(fan_cfg.name)
        speed = state.current_speed.value if state else "off"

        entry: dict = {"label": fan_cfg.label, "speed": speed}
        humidity = _fan_humidity(fan_cfg, sensor_cache, now)
        if humidity is not None:
            value, updated_at, is_stale = humidity
            entry["humidity"] = value
            entry["humidity_updated_at"] = updated_at.astimezone(timezone.utc).isoformat()
            entry["humidity_stale"] = is_stale
        fans.append(entry)

    sensors = []
    for fan_cfg in fan_configs:
        readings = cached_readings.get(fan_cfg.name, [])
        for i, sensor in enumerate(fan_cfg.co2_sensors):
            reading = readings[i] if i < len(readings) else None
            entry = {
                "label": sensor.label,
                "stale": reading_cache.is_stale(sensor.device_id, now),
            }

            read_at = reading_cache.read_at(sensor.device_id)
            if read_at is not None:
                entry["read_at"] = read_at.astimezone(timezone.utc).isoformat()
            changed_at = reading_cache.changed_at(sensor.device_id)
            if changed_at is not None:
                entry["changed_at"] = changed_at.astimezone(timezone.utc).isoformat()

            if reading is not None:
                if reading.co2 is not None:
                    entry["ppm"] = reading.co2
                if reading.temperature is not None:
                    entry["temperature"] = reading.temperature
                if reading.humidity is not None:
                    entry["humidity"] = reading.humidity
                if reading.pm25 is not None:
                    entry["pm25"] = reading.pm25
            sensors.append(entry)

    status = {
        "version": STATUS_VERSION,
        "fans": fans,
        "sensors": sensors,
        # Daemon liveness only. This is written every loop iteration, including
        # webhook wakeups, so it says nothing about how fresh the readings are —
        # per-sensor read_at/changed_at carry that.
        "written_at": now.astimezone(timezone.utc).isoformat(),
        # Deprecated alias for written_at, kept so a consumer still running
        # v1 logic degrades cleanly across the deploy window. Remove once
        # every consumer reads version 2.
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
