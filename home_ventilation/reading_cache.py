import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from home_ventilation.models import TuyaSensorReading

logger = logging.getLogger(__name__)

# A device not read in this many poll intervals is unreachable.
SENSOR_STALE_MULTIPLIER = 4


@dataclass
class ReadingEntry:
    reading: TuyaSensorReading
    read_at: datetime
    changed_at: datetime


class ReadingCache:
    """Track when each Tuya sensor was last read and last actually changed.

    Two timestamps, because they catch different failures. ``read_at`` catches a
    device that stopped answering. ``changed_at`` catches a device that still
    answers while its sensing element is dead — observed in the field as a
    sensor frozen at a fixed ppm while every other sensor moved.
    """

    def __init__(self, cache_path: str, stale_after_seconds: int, frozen_after_seconds: int):
        self._path = Path(cache_path)
        self._stale_after_seconds = stale_after_seconds
        self._frozen_after_seconds = frozen_after_seconds
        self._entries: dict[str, ReadingEntry] = {}
        self._load()

    def observe(self, device_id: str, reading: TuyaSensorReading | None, now: datetime) -> None:
        """Record a poll result. A ``None`` reading advances neither timestamp."""
        if reading is None:
            return

        previous = self._entries.get(device_id)
        changed_at = now
        if previous is not None and previous.reading == reading:
            changed_at = previous.changed_at

        self._entries[device_id] = ReadingEntry(
            reading=reading,
            read_at=now,
            changed_at=changed_at,
        )
        self._save()

    def read_at(self, device_id: str) -> datetime | None:
        entry = self._entries.get(device_id)
        return entry.read_at if entry else None

    def changed_at(self, device_id: str) -> datetime | None:
        entry = self._entries.get(device_id)
        return entry.changed_at if entry else None

    def is_stale(self, device_id: str, now: datetime) -> bool:
        """True when the device is unreachable, frozen, or has never been read."""
        entry = self._entries.get(device_id)
        if entry is None:
            return True
        if (now - entry.read_at).total_seconds() > self._stale_after_seconds:
            return True
        return (now - entry.changed_at).total_seconds() > self._frozen_after_seconds

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            for device_id, entry in data.items():
                self._entries[device_id] = ReadingEntry(
                    reading=TuyaSensorReading(**entry["reading"]),
                    read_at=datetime.fromisoformat(entry["read_at"]),
                    changed_at=datetime.fromisoformat(entry["changed_at"]),
                )
            logger.info("Loaded %d cached readings from %s", len(self._entries), self._path)
        except Exception:
            self._entries = {}
            logger.warning("Failed to load reading cache from %s, starting fresh", self._path)

    def _save(self) -> None:
        data = {}
        for device_id, entry in self._entries.items():
            data[device_id] = {
                "reading": {
                    "co2": entry.reading.co2,
                    "temperature": entry.reading.temperature,
                    "humidity": entry.reading.humidity,
                    "pm25": entry.reading.pm25,
                },
                "read_at": entry.read_at.isoformat(),
                "changed_at": entry.changed_at.isoformat(),
            }
        try:
            self._path.write_text(json.dumps(data, indent=2) + "\n")
        except Exception:
            logger.warning("Failed to save reading cache to %s", self._path)
