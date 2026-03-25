import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ThresholdsConfig:
    co2_low: int = 800
    co2_high: int = 1200
    humidity_low: float = 60.0
    humidity_high: float = 70.0
    co2_hysteresis: int = 50
    humidity_hysteresis: float = 3.0


@dataclass(frozen=True)
class TuyaDeviceConfig:
    device_id: str
    ip: str
    local_key: str


@dataclass(frozen=True)
class ScheduleConfig:
    start_hour: int = 22
    end_hour: int = 7
    run_minutes: int = 10
    speed: str = "low"


@dataclass(frozen=True)
class FanConfig:
    name: str
    shelly_host: str = ""
    co2_sensors: list[TuyaDeviceConfig] = field(default_factory=list)
    switch_inputs: list[int] = field(default_factory=list)
    humidity_sensor_ips: list[str] = field(default_factory=list)
    schedule: ScheduleConfig | None = None


@dataclass(frozen=True)
class Config:
    poll_interval_seconds: int
    reconciliation_interval_seconds: int
    manual_override_minutes: int
    thresholds: ThresholdsConfig
    fans: list[FanConfig]
    webhook_host: str
    webhook_port: int = 8090
    sensor_cache_path: str = "/dev/shm/home-ventilation-sensor-cache.json"
    humidity_stale_minutes: int = 120


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    thresholds = ThresholdsConfig(**raw.get("thresholds", {}))

    fans_raw = raw.get("fans", {})
    if not fans_raw:
        raise ValueError("At least one fan must be configured in [fans.*]")

    fans = []
    for name, fan_data in fans_raw.items():
        sched_raw = fan_data.get("schedule")

        co2_sensors = []
        for sensor_name, sensor_data in fan_data.get("co2_sensors", {}).items():
            co2_sensors.append(
                TuyaDeviceConfig(
                    device_id=sensor_data["device_id"],
                    ip=sensor_data["ip"],
                    local_key=sensor_data["local_key"],
                )
            )

        fans.append(
            FanConfig(
                name=name,
                shelly_host=fan_data.get("shelly_host", ""),
                co2_sensors=co2_sensors,
                switch_inputs=fan_data.get("switch_inputs", []),
                humidity_sensor_ips=fan_data.get("humidity_sensor_ips", []),
                schedule=ScheduleConfig(**sched_raw) if sched_raw else None,
            )
        )

    # Resolve sensor_cache_path: use absolute as-is, resolve relative to config dir
    cache_path_raw = raw.get("sensor_cache_path", "/dev/shm/home-ventilation-sensor-cache.json")
    cache_path = Path(cache_path_raw)
    if not cache_path.is_absolute():
        cache_path = path.parent / cache_path

    webhook_host = raw.get("webhook_host")
    if not webhook_host:
        raise ValueError("webhook_host is required in config")

    return Config(
        poll_interval_seconds=raw.get("poll_interval_seconds", 30),
        reconciliation_interval_seconds=raw.get("reconciliation_interval_seconds", 60),
        manual_override_minutes=raw.get("manual_override_minutes", 15),
        thresholds=thresholds,
        fans=fans,
        webhook_host=webhook_host,
        webhook_port=raw.get("webhook_port", 8090),
        sensor_cache_path=str(cache_path),
        humidity_stale_minutes=raw.get("humidity_stale_minutes", 120),
    )
