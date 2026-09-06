import json
from datetime import datetime, timedelta, timezone

from home_ventilation.config import FanConfig, TuyaDeviceConfig
from home_ventilation.models import FanSpeed, FanState, TuyaSensorReading
from home_ventilation.reading_cache import ReadingCache
from home_ventilation.sensor_cache import SensorCache
from home_ventilation.status_writer import write_status

NOW = datetime(2026, 3, 25, 10, 0, 0, tzinfo=timezone.utc)

STALE_AFTER = 120
FROZEN_AFTER = 1800


def _make_fan_config(name="shower", label="Shower", co2_sensors=None, humidity_ips=None):
    return FanConfig(
        name=name,
        label=label,
        shelly_host="10.0.0.51",
        co2_sensors=co2_sensors or [],
        humidity_sensor_ips=humidity_ips or [],
    )


def _make_sensor(name="bedroom", label="Bedroom", device_id="abc123"):
    return TuyaDeviceConfig(
        device_id=device_id, ip="10.0.0.61", local_key="key", name=name, label=label
    )


def _reading(**kwargs):
    return TuyaSensorReading(**kwargs)


def _caches(tmp_path):
    """Return (sensor_cache, reading_cache) backed by tmp_path."""
    return (
        SensorCache(str(tmp_path / "cache.json"), 120),
        ReadingCache(str(tmp_path / "readings.json"), STALE_AFTER, FROZEN_AFTER),
    )


def _write(tmp_path, fan_configs, fan_states, cached_readings, sensor_cache, reading_cache, now):
    out = tmp_path / "status.json"
    write_status(
        str(out), fan_configs, fan_states, cached_readings, sensor_cache, reading_cache, now
    )
    return json.loads(out.read_text())


def test_basic_status_output(tmp_path):
    sensor = _make_sensor()
    fan_cfg = _make_fan_config(co2_sensors=[sensor], humidity_ips=["10.0.0.50"])
    fan_states = {"shower": FanState(current_speed=FanSpeed.LOW)}
    reading = _reading(co2=850, temperature=22.0, humidity=48.0, pm25=12.0)
    cached_readings = {"shower": [reading]}

    sensor_cache, reading_cache = _caches(tmp_path)
    sensor_cache.update("10.0.0.50", 65.5)
    reading_cache.observe(sensor.device_id, reading, NOW)

    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert data["version"] == 2
    assert data["written_at"] == "2026-03-25T10:00:00+00:00"

    fan = data["fans"][0]
    assert fan["label"] == "Shower"
    assert fan["speed"] == "low"
    assert fan["humidity"] == 65.5
    assert fan["humidity_stale"] is False

    sensor_out = data["sensors"][0]
    assert sensor_out["label"] == "Bedroom"
    assert sensor_out["stale"] is False
    assert sensor_out["ppm"] == 850
    assert sensor_out["temperature"] == 22.0
    assert sensor_out["humidity"] == 48.0
    assert sensor_out["pm25"] == 12.0
    assert sensor_out["read_at"] == "2026-03-25T10:00:00+00:00"
    assert sensor_out["changed_at"] == "2026-03-25T10:00:00+00:00"


def test_never_read_sensor_is_reported_stale_not_dropped(tmp_path):
    """A configured sensor always appears, so a dead one is distinguishable
    from one that was never configured."""
    sensor = _make_sensor()
    fan_cfg = _make_fan_config(co2_sensors=[sensor])
    fan_states = {"shower": FanState()}
    cached_readings = {"shower": [None]}

    sensor_cache, reading_cache = _caches(tmp_path)
    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert data["sensors"] == [{"label": "Bedroom", "stale": True}]


def test_frozen_sensor_is_stale_with_its_last_value(tmp_path):
    """The Bibi case: still answering, value pinned, reported stale but visible."""
    sensor = _make_sensor(label="Bibi")
    fan_cfg = _make_fan_config(co2_sensors=[sensor])
    fan_states = {"shower": FanState()}
    frozen = _reading(co2=511)
    cached_readings = {"shower": [frozen]}

    sensor_cache, reading_cache = _caches(tmp_path)
    for offset in range(0, FROZEN_AFTER + 60, 30):
        reading_cache.observe(sensor.device_id, frozen, NOW + timedelta(seconds=offset))

    later = NOW + timedelta(seconds=FROZEN_AFTER + 60)
    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, later
    )

    out = data["sensors"][0]
    assert out["stale"] is True
    assert out["ppm"] == 511  # value kept so the dashboard can show what it was


def test_unreachable_sensor_keeps_last_value_and_is_stale(tmp_path):
    sensor = _make_sensor()
    fan_cfg = _make_fan_config(co2_sensors=[sensor])
    fan_states = {"shower": FanState()}
    reading = _reading(co2=850)
    cached_readings = {"shower": [reading]}

    sensor_cache, reading_cache = _caches(tmp_path)
    reading_cache.observe(sensor.device_id, reading, NOW)

    later = NOW + timedelta(seconds=STALE_AFTER + 1)
    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, later
    )

    assert data["sensors"][0]["stale"] is True
    assert data["sensors"][0]["ppm"] == 850


def test_partial_reading_omits_absent_fields(tmp_path):
    """Absent means no reading. A value is never emitted as 0 to mean missing."""
    sensor = _make_sensor()
    fan_cfg = _make_fan_config(co2_sensors=[sensor])
    fan_states = {"shower": FanState()}
    reading = _reading(co2=850)
    cached_readings = {"shower": [reading]}

    sensor_cache, reading_cache = _caches(tmp_path)
    reading_cache.observe(sensor.device_id, reading, NOW)

    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    out = data["sensors"][0]
    assert out["ppm"] == 850
    assert "temperature" not in out
    assert "humidity" not in out
    assert "pm25" not in out


def test_missing_humidity_omitted(tmp_path):
    fan_cfg = _make_fan_config(humidity_ips=["10.0.0.50"])
    fan_states = {"shower": FanState(current_speed=FanSpeed.HIGH)}
    cached_readings: dict[str, list[TuyaSensorReading | None]] = {"shower": []}

    sensor_cache, reading_cache = _caches(tmp_path)
    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert data["fans"] == [{"label": "Shower", "speed": "high"}]


def test_stale_humidity_is_reported_not_dropped(tmp_path):
    """A Shelly H&T dead for hours must not look like an unconfigured sensor."""
    fan_cfg = _make_fan_config(humidity_ips=["10.0.0.50"])
    fan_states = {"shower": FanState(current_speed=FanSpeed.LOW)}
    cached_readings: dict[str, list[TuyaSensorReading | None]] = {"shower": []}

    sensor_cache, reading_cache = _caches(tmp_path)
    sensor_cache.update("10.0.0.50", 65.5, now=NOW)

    later = NOW + timedelta(minutes=200)  # past humidity_stale_minutes=120
    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, later
    )

    fan = data["fans"][0]
    assert fan["humidity"] == 65.5
    assert fan["humidity_stale"] is True
    assert "humidity_updated_at" in fan


def test_humidity_reports_max_not_average(tmp_path):
    """Status humidity should use max() to match fan.py decision logic."""
    fan_cfg = _make_fan_config(humidity_ips=["10.0.0.50", "10.0.0.52"])
    fan_states = {"shower": FanState(current_speed=FanSpeed.LOW)}
    cached_readings: dict[str, list[TuyaSensorReading | None]] = {"shower": []}

    sensor_cache, reading_cache = _caches(tmp_path)
    sensor_cache.update("10.0.0.50", 60.0)
    sensor_cache.update("10.0.0.52", 70.0)

    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert data["fans"][0]["humidity"] == 70.0
    assert data["fans"][0]["humidity_stale"] is False


def test_multiple_fans_and_sensors(tmp_path):
    sensor1 = _make_sensor("bedroom", "Bedroom", device_id="dev1")
    sensor2 = _make_sensor("living_room", "Living Room", device_id="dev2")
    fan1 = _make_fan_config("shower", "Shower", [sensor1], ["10.0.0.50"])
    fan2 = _make_fan_config("bathroom", "Bathroom", [sensor2], ["10.0.0.52"])

    fan_states = {
        "shower": FanState(current_speed=FanSpeed.LOW),
        "bathroom": FanState(current_speed=FanSpeed.OFF),
    }
    r1 = _reading(co2=850, temperature=22.0)
    r2 = _reading(co2=480, pm25=8.0)
    cached_readings = {"shower": [r1], "bathroom": [r2]}

    sensor_cache, reading_cache = _caches(tmp_path)
    sensor_cache.update("10.0.0.50", 65.5)
    sensor_cache.update("10.0.0.52", 58.2)
    reading_cache.observe("dev1", r1, NOW)
    reading_cache.observe("dev2", r2, NOW)

    data = _write(
        tmp_path, [fan1, fan2], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert [f["label"] for f in data["fans"]] == ["Shower", "Bathroom"]
    assert [s["label"] for s in data["sensors"]] == ["Bedroom", "Living Room"]
    assert all(s["stale"] is False for s in data["sensors"])


def test_one_dead_sensor_among_healthy_ones(tmp_path):
    healthy = _make_sensor("bedroom", "Bedroom", device_id="dev1")
    dead = _make_sensor("bibi", "Bibi", device_id="dev2")
    fan_cfg = _make_fan_config(co2_sensors=[healthy, dead])
    fan_states = {"shower": FanState()}
    r1 = _reading(co2=850)
    cached_readings = {"shower": [r1, None]}

    sensor_cache, reading_cache = _caches(tmp_path)
    reading_cache.observe("dev1", r1, NOW)

    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    by_label = {s["label"]: s for s in data["sensors"]}
    assert by_label["Bedroom"]["stale"] is False
    assert by_label["Bibi"]["stale"] is True
    assert "ppm" not in by_label["Bibi"]


def test_atomic_write_no_partial(tmp_path):
    """Status file should not exist in a half-written state."""
    fan_cfg = _make_fan_config()
    fan_states = {"shower": FanState()}
    cached_readings: dict[str, list[TuyaSensorReading | None]] = {"shower": []}
    sensor_cache, reading_cache = _caches(tmp_path)

    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert "fans" in data
    assert "sensors" in data
    assert "written_at" in data


def test_updated_at_alias_kept_for_v1_consumers(tmp_path):
    fan_cfg = _make_fan_config()
    fan_states = {"shower": FanState()}
    cached_readings: dict[str, list[TuyaSensorReading | None]] = {"shower": []}
    sensor_cache, reading_cache = _caches(tmp_path)

    data = _write(
        tmp_path, [fan_cfg], fan_states, cached_readings, sensor_cache, reading_cache, NOW
    )

    assert data["updated_at"] == data["written_at"]
