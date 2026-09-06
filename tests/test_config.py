"""Tests for TOML config loading."""

from pathlib import Path

import pytest

from home_ventilation.config import load_config

ROOT = 'webhook_host = "10.0.0.1"\n'
FAN = '\n[fans.shower]\nshelly_host = "10.0.0.51"\n'
MINIMAL = ROOT + FAN


def _with_root(*lines):
    """Top-level keys must precede any [table], or TOML nests them inside it."""
    return ROOT + "".join(f"{line}\n" for line in lines) + FAN


def _write(tmp_path, body, name="config.toml"):
    path = tmp_path / name
    path.write_text(body)
    return path


class TestValidation:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nope.toml")

    def test_no_fans_raises(self, tmp_path):
        with pytest.raises(ValueError, match="At least one fan"):
            load_config(_write(tmp_path, 'webhook_host = "10.0.0.1"\n'))

    def test_missing_webhook_host_raises(self, tmp_path):
        body = '[fans.shower]\nshelly_host = "10.0.0.51"\n'
        with pytest.raises(ValueError, match="webhook_host is required"):
            load_config(_write(tmp_path, body))


class TestDefaults:
    def test_intervals_and_windows(self, tmp_path):
        cfg = load_config(_write(tmp_path, MINIMAL))

        assert cfg.poll_interval_seconds == 30
        assert cfg.reconciliation_interval_seconds == 60
        assert cfg.manual_override_minutes == 15
        assert cfg.webhook_port == 8090
        assert cfg.humidity_stale_minutes == 120
        assert cfg.frozen_stale_seconds == 1800

    def test_ramdisk_paths(self, tmp_path):
        cfg = load_config(_write(tmp_path, MINIMAL))

        assert cfg.sensor_cache_path == "/dev/shm/home-ventilation-sensor-cache.json"
        assert cfg.reading_cache_path == "/dev/shm/home-ventilation-reading-cache.json"
        assert cfg.status_file_path == "/dev/shm/home-ventilation-status.json"

    def test_threshold_defaults(self, tmp_path):
        cfg = load_config(_write(tmp_path, MINIMAL))

        assert cfg.thresholds.co2_low == 800
        assert cfg.thresholds.co2_high == 1200
        assert cfg.thresholds.co2_hysteresis == 50


class TestOverrides:
    def test_scalar_overrides(self, tmp_path):
        body = _with_root(
            "poll_interval_seconds = 15",
            "frozen_stale_seconds = 600",
            "humidity_stale_minutes = 30",
            "webhook_port = 8002",
        )
        cfg = load_config(_write(tmp_path, body))

        assert cfg.poll_interval_seconds == 15
        assert cfg.frozen_stale_seconds == 600
        assert cfg.humidity_stale_minutes == 30
        assert cfg.webhook_port == 8002

    def test_thresholds_override(self, tmp_path):
        body = MINIMAL + "\n[thresholds]\nco2_low = 700\nco2_high = 1000\n"
        cfg = load_config(_write(tmp_path, body))

        assert cfg.thresholds.co2_low == 700
        assert cfg.thresholds.co2_high == 1000


class TestPathResolution:
    def test_absolute_paths_are_kept(self, tmp_path):
        body = _with_root('reading_cache_path = "/var/lib/readings.json"')
        cfg = load_config(_write(tmp_path, body))

        assert cfg.reading_cache_path == "/var/lib/readings.json"

    @pytest.mark.parametrize(
        ("key", "attr"),
        [
            ("sensor_cache_path", "sensor_cache_path"),
            ("reading_cache_path", "reading_cache_path"),
            ("status_file_path", "status_file_path"),
        ],
    )
    def test_relative_paths_resolve_against_the_config_dir(self, tmp_path, key, attr):
        body = _with_root(f'{key} = "state/file.json"')
        cfg = load_config(_write(tmp_path, body))

        assert getattr(cfg, attr) == str(tmp_path / "state/file.json")
        assert Path(getattr(cfg, attr)).is_absolute()


class TestFans:
    def test_label_defaults_from_the_section_name(self, tmp_path):
        body = 'webhook_host = "10.0.0.1"\n\n[fans.master_bathroom]\nshelly_host = "10.0.0.51"\n'
        cfg = load_config(_write(tmp_path, body))

        assert cfg.fans[0].name == "master_bathroom"
        assert cfg.fans[0].label == "Master Bathroom"

    def test_explicit_label_wins(self, tmp_path):
        body = MINIMAL + 'label = "Sprcha"\n'
        cfg = load_config(_write(tmp_path, body))

        assert cfg.fans[0].label == "Sprcha"

    def test_co2_sensors_are_parsed(self, tmp_path):
        body = (
            MINIMAL
            + """
[fans.shower.co2_sensors.living_room]
device_id = "dev1"
ip = "10.0.0.61"
local_key = "k1"
"""
        )
        cfg = load_config(_write(tmp_path, body))
        sensor = cfg.fans[0].co2_sensors[0]

        assert sensor.device_id == "dev1"
        assert sensor.ip == "10.0.0.61"
        assert sensor.name == "living_room"
        assert sensor.label == "Living Room"  # derived from the key

    def test_sensor_label_can_be_overridden(self, tmp_path):
        body = (
            MINIMAL
            + """
[fans.shower.co2_sensors.viki]
device_id = "dev1"
ip = "10.0.0.61"
local_key = "k1"
label = "Viki's Room"
"""
        )
        cfg = load_config(_write(tmp_path, body))

        assert cfg.fans[0].co2_sensors[0].label == "Viki's Room"

    def test_schedule_is_parsed_when_present(self, tmp_path):
        body = (
            MINIMAL
            + """
[fans.shower.schedule]
start_hour = 22
end_hour = 7
run_minutes = 0
max_speed = "low"
"""
        )
        cfg = load_config(_write(tmp_path, body))
        schedule = cfg.fans[0].schedule

        assert schedule is not None
        assert schedule.start_hour == 22
        assert schedule.run_minutes == 0
        assert schedule.max_speed == "low"

    def test_no_schedule_section_leaves_it_unset(self, tmp_path):
        cfg = load_config(_write(tmp_path, MINIMAL))
        assert cfg.fans[0].schedule is None

    def test_multiple_fans_and_switch_inputs(self, tmp_path):
        body = """
webhook_host = "10.0.0.1"

[fans.shower]
shelly_host = "10.0.0.51"
switch_inputs = [0]
humidity_sensor_ips = ["10.0.0.50"]

[fans.bathroom]
shelly_host = "10.0.0.53"
switch_inputs = [0, 1]
"""
        cfg = load_config(_write(tmp_path, body))

        assert [f.name for f in cfg.fans] == ["shower", "bathroom"]
        assert cfg.fans[0].switch_inputs == [0]
        assert cfg.fans[0].humidity_sensor_ips == ["10.0.0.50"]
        assert cfg.fans[1].switch_inputs == [0, 1]
        assert cfg.fans[1].humidity_sensor_ips == []
