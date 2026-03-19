from datetime import datetime, timedelta, timezone

from home_ventilation.sensor_cache import SensorCache

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
STALE_MINUTES = 120


def test_update_and_get(tmp_path):
    cache = SensorCache(str(tmp_path / "cache.json"), STALE_MINUTES)
    cache.update("sensor-1", 65.2, 23.5)
    result = cache.get_humidity("sensor-1", datetime.now(timezone.utc))
    assert result == 65.2


def test_unknown_device_returns_none(tmp_path):
    cache = SensorCache(str(tmp_path / "cache.json"), STALE_MINUTES)
    assert cache.get_humidity("nonexistent", NOW) is None


def test_stale_reading_returns_none(tmp_path):
    cache = SensorCache(str(tmp_path / "cache.json"), STALE_MINUTES)
    cache.update("sensor-1", 65.2, 23.5)
    future = datetime.now(timezone.utc) + timedelta(minutes=STALE_MINUTES + 1)
    assert cache.get_humidity("sensor-1", future) is None


def test_fresh_reading_returns_value(tmp_path):
    cache = SensorCache(str(tmp_path / "cache.json"), STALE_MINUTES)
    cache.update("sensor-1", 70.0, None)
    soon = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert cache.get_humidity("sensor-1", soon) == 70.0


def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "cache.json")
    cache1 = SensorCache(path, STALE_MINUTES)
    cache1.update("sensor-1", 65.2, 23.5)
    cache1.update("sensor-2", 70.0, None)

    # New instance loads from disk
    cache2 = SensorCache(path, STALE_MINUTES)
    now = datetime.now(timezone.utc)
    assert cache2.get_humidity("sensor-1", now) == 65.2
    assert cache2.get_humidity("sensor-2", now) == 70.0


def test_missing_cache_file(tmp_path):
    cache = SensorCache(str(tmp_path / "nonexistent.json"), STALE_MINUTES)
    assert cache.get_humidity("sensor-1", NOW) is None


def test_corrupt_cache_file(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("not valid json {{{")
    cache = SensorCache(str(path), STALE_MINUTES)
    assert cache.get_humidity("sensor-1", NOW) is None
