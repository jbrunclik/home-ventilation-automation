from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class FanSpeed(Enum):
    OFF = "off"
    LOW = "low"
    HIGH = "high"


@dataclass
class FanState:
    current_speed: FanSpeed = FanSpeed.OFF
    override_until: datetime | None = None
    previous_switch_states: dict[int, bool] | None = None
