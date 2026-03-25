import json
from datetime import datetime, timezone

from home_ventilation.config import FanConfig, TuyaDeviceConfig
from home_ventilation.models import FanSpeed, FanState
from home_ventilation.sensor_cache import SensorCache
from home_ventilation.status_writer import write_status

NOW = datetime(2026, 3, 25, 10, 0, 0, tzinfo=timezone.utc)


def _make_fan_config(name="shower", label="Shower", co2_sensors=None, humidity_ips=None):
    return FanConfig(
        name=name,
        label=label,
        shelly_host="10.0.0.51",
        co2_sensors=co2_sensors or [],
        humidity_sensor_ips=humidity_ips or [],
    )


def _make_sensor(name="bedroom", label="Bedroom"):
    return TuyaDeviceConfig(
        device_id="abc123", ip="10.0.0.61", local_key="key", name=name, label=label
    )


def test_basic_status_output(tmp_path):
    sensor = _make_sensor()
    fan_cfg = _make_fan_config(co2_sensors=[sensor], humidity_ips=["10.0.0.50"])
    fan_states = {"shower": FanState(current_speed=FanSpeed.LOW)}
    cached_co2 = {"shower": [850]}

    cache = SensorCache(str(tmp_path / "cache.json"), 120)
    cache.update("10.0.0.50", 65.5)

    out = tmp_path / "status.json"
    write_status(str(out), [fan_cfg], fan_states, cached_co2, cache, NOW)

    data = json.loads(out.read_text())
    assert data["fans"] == [{"label": "Shower", "speed": "low", "humidity": 65.5}]
    assert data["co2"] == [{"label": "Bedroom", "ppm": 850}]
    assert data["updated_at"] == "2026-03-25T10:00:00+00:00"


def test_null_co2_skipped(tmp_path):
    sensor = _make_sensor()
    fan_cfg = _make_fan_config(co2_sensors=[sensor])
    fan_states = {"shower": FanState()}
    cached_co2 = {"shower": [None]}

    cache = SensorCache(str(tmp_path / "cache.json"), 120)
    out = tmp_path / "status.json"
    write_status(str(out), [fan_cfg], fan_states, cached_co2, cache, NOW)

    data = json.loads(out.read_text())
    assert data["co2"] == []


def test_missing_humidity_omitted(tmp_path):
    fan_cfg = _make_fan_config(humidity_ips=["10.0.0.50"])
    fan_states = {"shower": FanState(current_speed=FanSpeed.HIGH)}
    cached_co2 = {"shower": []}

    cache = SensorCache(str(tmp_path / "cache.json"), 120)
    # No humidity update -> no value in cache
    out = tmp_path / "status.json"
    write_status(str(out), [fan_cfg], fan_states, cached_co2, cache, NOW)

    data = json.loads(out.read_text())
    assert data["fans"] == [{"label": "Shower", "speed": "high"}]
    assert "humidity" not in data["fans"][0]


def test_multiple_fans_and_sensors(tmp_path):
    sensor1 = _make_sensor("bedroom", "Bedroom")
    sensor2 = _make_sensor("living_room", "Living Room")
    fan1 = _make_fan_config("shower", "Shower", [sensor1], ["10.0.0.50"])
    fan2 = _make_fan_config("bathroom", "Bathroom", [sensor2], ["10.0.0.52"])

    fan_states = {
        "shower": FanState(current_speed=FanSpeed.LOW),
        "bathroom": FanState(current_speed=FanSpeed.OFF),
    }
    cached_co2 = {"shower": [850], "bathroom": [480]}

    cache = SensorCache(str(tmp_path / "cache.json"), 120)
    cache.update("10.0.0.50", 65.5)
    cache.update("10.0.0.52", 58.2)

    out = tmp_path / "status.json"
    write_status(str(out), [fan1, fan2], fan_states, cached_co2, cache, NOW)

    data = json.loads(out.read_text())
    assert len(data["fans"]) == 2
    assert len(data["co2"]) == 2
    assert data["fans"][0]["label"] == "Shower"
    assert data["fans"][1]["label"] == "Bathroom"
    assert data["co2"][0]["label"] == "Bedroom"
    assert data["co2"][1]["label"] == "Living Room"


def test_atomic_write_no_partial(tmp_path):
    """Status file should not exist in a half-written state."""
    fan_cfg = _make_fan_config()
    fan_states = {"shower": FanState()}
    cached_co2 = {"shower": []}
    cache = SensorCache(str(tmp_path / "cache.json"), 120)

    out = tmp_path / "status.json"
    write_status(str(out), [fan_cfg], fan_states, cached_co2, cache, NOW)

    # File should be valid JSON
    data = json.loads(out.read_text())
    assert "fans" in data
    assert "co2" in data
    assert "updated_at" in data
