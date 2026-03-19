import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ThresholdsConfig:
    co2_low: int = 800
    co2_high: int = 1200
    humidity_low: float = 60.0
    humidity_high: float = 70.0


@dataclass(frozen=True)
class HomebridgeConfig:
    host: str
    port: int = 8581
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class FanConfig:
    name: str
    shelly_host: str
    co2_accessories: list[str]
    humidity_accessories: list[str]
    switch_inputs: list[int]
    humidity_sensor_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    poll_interval_seconds: int
    switch_poll_interval_seconds: int
    manual_override_minutes: int
    thresholds: ThresholdsConfig
    homebridge: HomebridgeConfig
    fans: list[FanConfig]
    webhook_port: int = 8090
    sensor_cache_path: str = "/dev/shm/home-ventilation-sensor-cache.json"
    humidity_stale_minutes: int = 120


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    thresholds = ThresholdsConfig(**raw.get("thresholds", {}))

    hb_raw = raw.get("homebridge", {})
    username = os.environ.get("HOMEBRIDGE_USERNAME", "")
    password = os.environ.get("HOMEBRIDGE_PASSWORD", "")
    if not username or not password:
        raise ValueError(
            "HOMEBRIDGE_USERNAME and HOMEBRIDGE_PASSWORD environment variables are required"
        )
    homebridge = HomebridgeConfig(
        host=hb_raw["host"],
        port=hb_raw.get("port", 8581),
        username=username,
        password=password,
    )

    fans_raw = raw.get("fans", {})
    if not fans_raw:
        raise ValueError("At least one fan must be configured in [fans.*]")

    fans = []
    for name, fan_data in fans_raw.items():
        fans.append(
            FanConfig(
                name=name,
                shelly_host=fan_data["shelly_host"],
                co2_accessories=fan_data.get("co2_accessories", []),
                humidity_accessories=fan_data.get("humidity_accessories", []),
                switch_inputs=fan_data.get("switch_inputs", []),
                humidity_sensor_ids=fan_data.get("humidity_sensor_ids", []),
            )
        )

    # Resolve sensor_cache_path: use absolute as-is, resolve relative to config dir
    cache_path_raw = raw.get("sensor_cache_path", "/dev/shm/home-ventilation-sensor-cache.json")
    cache_path = Path(cache_path_raw)
    if not cache_path.is_absolute():
        cache_path = path.parent / cache_path

    return Config(
        poll_interval_seconds=raw.get("poll_interval_seconds", 30),
        switch_poll_interval_seconds=raw.get("switch_poll_interval_seconds", 1),
        manual_override_minutes=raw.get("manual_override_minutes", 15),
        thresholds=thresholds,
        homebridge=homebridge,
        fans=fans,
        webhook_port=raw.get("webhook_port", 8090),
        sensor_cache_path=str(cache_path),
        humidity_stale_minutes=raw.get("humidity_stale_minutes", 120),
    )
