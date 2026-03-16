import logging

import httpx

from home_ventilation.models import FanSpeed

logger = logging.getLogger(__name__)


async def get_switch_inputs(client: httpx.AsyncClient, host: str) -> dict[int, bool]:
    """Read switch input states from Shelly 2PM Gen4."""
    results = {}
    for input_id in (0, 1):
        try:
            resp = await client.get(
                f"http://{host}/rpc/Input.GetStatus",
                params={"id": input_id},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
            results[input_id] = bool(data.get("state", False))
        except Exception:
            logger.exception("Failed to read switch input %d from %s", input_id, host)
    return results


async def get_relay_status(client: httpx.AsyncClient, host: str) -> FanSpeed:
    """Read current relay states and derive fan speed."""
    states = {}
    for relay_id in (0, 1):
        try:
            resp = await client.get(
                f"http://{host}/rpc/Switch.GetStatus",
                params={"id": relay_id},
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
            states[relay_id] = bool(data.get("output", False))
        except Exception:
            logger.exception("Failed to read relay %d from %s", relay_id, host)
            return FanSpeed.OFF

    relay0 = states.get(0, False)
    relay1 = states.get(1, False)

    if relay0 and not relay1:
        return FanSpeed.LOW
    if not relay0 and relay1:
        return FanSpeed.HIGH
    return FanSpeed.OFF


async def set_fan_speed(client: httpx.AsyncClient, host: str, speed: FanSpeed) -> None:
    """Set fan speed via Shelly 2PM Gen4 relays.

    OFF:  both relays off
    LOW:  relay 0 on, relay 1 off
    HIGH: relay 0 off, relay 1 on
    """
    relay_states = {
        FanSpeed.OFF: {0: False, 1: False},
        FanSpeed.LOW: {0: True, 1: False},
        FanSpeed.HIGH: {0: False, 1: True},
    }

    targets = relay_states[speed]

    for relay_id, on in targets.items():
        try:
            resp = await client.get(
                f"http://{host}/rpc/Switch.Set",
                params={"id": relay_id, "on": str(on).lower()},
                timeout=5.0,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to set relay %d to %s on %s", relay_id, on, host)
            raise

    logger.info("Set fan speed to %s on %s", speed.value, host)
