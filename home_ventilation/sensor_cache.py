import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    humidity: float
    timestamp: datetime


class SensorCache:
    def __init__(self, cache_path: str, stale_minutes: int):
        self._path = Path(cache_path)
        self._stale_minutes = stale_minutes
        self._readings: dict[str, SensorReading] = {}
        self._load()

    def update(self, device_id: str, humidity: float, now: datetime | None = None) -> None:
        self._readings[device_id] = SensorReading(
            humidity=humidity,
            timestamp=now or datetime.now(timezone.utc),
        )
        self._save()

    def get_humidity(self, device_id: str, now: datetime) -> float | None:
        reading = self._readings.get(device_id)
        if reading is None:
            return None
        age_minutes = (now - reading.timestamp).total_seconds() / 60
        if age_minutes > self._stale_minutes:
            return None
        return reading.humidity

    def get_reading(self, device_id: str) -> SensorReading | None:
        """Return the raw reading with no staleness filter.

        Fan control uses ``get_humidity``, which drops stale values so they
        cannot influence a decision. Status reporting needs the value *and* its
        age, so a dead sensor can be shown as stale rather than vanishing.
        """
        return self._readings.get(device_id)

    def is_stale(self, device_id: str, now: datetime) -> bool:
        reading = self._readings.get(device_id)
        if reading is None:
            return True
        return (now - reading.timestamp).total_seconds() / 60 > self._stale_minutes

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            for device_id, entry in data.items():
                self._readings[device_id] = SensorReading(
                    humidity=entry["humidity"],
                    timestamp=datetime.fromisoformat(entry["timestamp"]),
                )
            logger.info(
                "Loaded %d cached sensor readings from %s", len(self._readings), self._path
            )
        except Exception:
            logger.warning("Failed to load sensor cache from %s, starting fresh", self._path)

    def _save(self) -> None:
        data = {}
        for device_id, reading in self._readings.items():
            data[device_id] = {
                "humidity": reading.humidity,
                "timestamp": reading.timestamp.isoformat(),
            }
        try:
            self._path.write_text(json.dumps(data, indent=2) + "\n")
        except Exception:
            logger.warning("Failed to save sensor cache to %s", self._path)
