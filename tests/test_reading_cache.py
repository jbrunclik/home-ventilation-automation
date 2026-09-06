from datetime import datetime, timedelta, timezone

from home_ventilation.models import TuyaSensorReading
from home_ventilation.reading_cache import ReadingCache

NOW = datetime(2026, 9, 6, 10, 0, 0, tzinfo=timezone.utc)

STALE_AFTER = 120
FROZEN_AFTER = 1800


def _cache(tmp_path, name="readings.json"):
    return ReadingCache(str(tmp_path / name), STALE_AFTER, FROZEN_AFTER)


def test_first_observation_sets_both_timestamps(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=800), NOW)

    assert cache.read_at("dev1") == NOW
    assert cache.changed_at("dev1") == NOW
    assert cache.is_stale("dev1", NOW) is False


def test_changed_value_advances_both(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=800), NOW)
    later = NOW + timedelta(seconds=30)
    cache.observe("dev1", TuyaSensorReading(co2=815), later)

    assert cache.read_at("dev1") == later
    assert cache.changed_at("dev1") == later


def test_unchanged_value_advances_read_only(tmp_path):
    """The Bibi case: the device answers, but the value never moves."""
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=511), NOW)
    later = NOW + timedelta(seconds=30)
    cache.observe("dev1", TuyaSensorReading(co2=511), later)

    assert cache.read_at("dev1") == later
    assert cache.changed_at("dev1") == NOW


def test_none_reading_advances_neither(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=800), NOW)
    cache.observe("dev1", None, NOW + timedelta(seconds=30))

    assert cache.read_at("dev1") == NOW
    assert cache.changed_at("dev1") == NOW


def test_never_read_is_stale(tmp_path):
    cache = _cache(tmp_path)
    assert cache.is_stale("unknown", NOW) is True
    assert cache.read_at("unknown") is None
    assert cache.changed_at("unknown") is None


def test_unreachable_device_is_stale(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=800), NOW)

    assert cache.is_stale("dev1", NOW + timedelta(seconds=STALE_AFTER - 1)) is False
    assert cache.is_stale("dev1", NOW + timedelta(seconds=STALE_AFTER + 1)) is True


def test_frozen_device_is_stale_while_still_answering(tmp_path):
    """Polled continuously, value never changes -> stale once past the frozen window."""
    cache = _cache(tmp_path)
    reading = TuyaSensorReading(co2=511)
    for offset in range(0, FROZEN_AFTER + 60, 30):
        cache.observe("dev1", reading, NOW + timedelta(seconds=offset))

    end = NOW + timedelta(seconds=FROZEN_AFTER + 60)
    # read_at is current — only changed_at reveals the failure
    assert (end - cache.read_at("dev1")).total_seconds() <= 30
    assert cache.is_stale("dev1", end) is True


def test_frozen_window_is_not_hit_by_normal_stability(tmp_path):
    cache = _cache(tmp_path)
    reading = TuyaSensorReading(co2=511)
    cache.observe("dev1", reading, NOW)
    cache.observe("dev1", reading, NOW + timedelta(seconds=300))

    assert cache.is_stale("dev1", NOW + timedelta(seconds=300)) is False


def test_survives_restart(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=511), NOW)
    cache.observe("dev1", TuyaSensorReading(co2=511), NOW + timedelta(seconds=30))

    reloaded = _cache(tmp_path)
    assert reloaded.read_at("dev1") == NOW + timedelta(seconds=30)
    assert reloaded.changed_at("dev1") == NOW


def test_restart_does_not_reset_a_frozen_sensor(tmp_path):
    """A sensor that died while the daemon was down must still read as stale."""
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=511), NOW)

    reloaded = _cache(tmp_path)
    assert reloaded.is_stale("dev1", NOW + timedelta(seconds=FROZEN_AFTER + 1)) is True


def test_corrupt_file_starts_fresh(tmp_path):
    path = tmp_path / "readings.json"
    path.write_text("{ this is not json")

    cache = ReadingCache(str(path), STALE_AFTER, FROZEN_AFTER)
    assert cache.read_at("dev1") is None

    cache.observe("dev1", TuyaSensorReading(co2=800), NOW)
    assert cache.read_at("dev1") == NOW


def test_missing_file_starts_fresh(tmp_path):
    cache = ReadingCache(str(tmp_path / "nope.json"), STALE_AFTER, FROZEN_AFTER)
    assert cache.read_at("dev1") is None


def test_tracks_devices_independently(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=800), NOW)
    cache.observe("dev2", TuyaSensorReading(co2=511), NOW)

    later = NOW + timedelta(seconds=30)
    cache.observe("dev1", TuyaSensorReading(co2=830), later)
    cache.observe("dev2", TuyaSensorReading(co2=511), later)

    assert cache.changed_at("dev1") == later
    assert cache.changed_at("dev2") == NOW


def test_change_in_any_field_counts(tmp_path):
    cache = _cache(tmp_path)
    cache.observe("dev1", TuyaSensorReading(co2=800, pm25=2.0), NOW)
    later = NOW + timedelta(seconds=30)
    cache.observe("dev1", TuyaSensorReading(co2=800, pm25=3.0), later)

    assert cache.changed_at("dev1") == later
