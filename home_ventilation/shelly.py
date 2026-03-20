import asyncio
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


async def get_cover_status(client: httpx.AsyncClient, host: str) -> FanSpeed:
    """Read cover state from Shelly 2PM and derive fan speed.

    Cover mode is used to prevent both relays from being on simultaneously.
    Open = relay 0 (LOW), Close = relay 1 (HIGH), Stopped = OFF.
    """
    try:
        resp = await client.get(
            f"http://{host}/rpc/Cover.GetStatus",
            params={"id": 0},
            timeout=5.0,
        )
        resp.raise_for_status()
        state = resp.json().get("state", "stopped")
    except Exception:
        logger.exception("Failed to read cover status from %s", host)
        return FanSpeed.OFF

    if state == "opening":
        return FanSpeed.LOW
    if state == "closing":
        return FanSpeed.HIGH
    return FanSpeed.OFF


async def set_fan_speed(client: httpx.AsyncClient, host: str, speed: FanSpeed) -> None:
    """Set fan speed via Shelly 2PM Gen4 cover mode.

    Cover mode prevents both relays from being on simultaneously.
    OFF:  Cover.Stop
    LOW:  Cover.Open  (relay 0)
    HIGH: Cover.Close (relay 1)
    """
    rpc_method = {
        FanSpeed.OFF: "Cover.Stop",
        FanSpeed.LOW: "Cover.Open",
        FanSpeed.HIGH: "Cover.Close",
    }

    method = rpc_method[speed]

    async def _rpc(m: str) -> None:
        resp = await client.get(f"http://{host}/rpc/{m}", params={"id": 0}, timeout=5.0)
        resp.raise_for_status()

    try:
        # Stop first — cover can't switch directly between Open and Close.
        # Brief delay needed for the device to complete the stop transition.
        await _rpc("Cover.Stop")
        if speed != FanSpeed.OFF:
            await asyncio.sleep(0.5)
            await _rpc(method)
    except Exception:
        logger.exception("Failed to set %s on %s", speed.value, host)
        raise

    logger.debug("Set fan speed to %s on %s", speed.value, host)


async def configure_cover_timeouts(
    client: httpx.AsyncClient, host: str, maxtime: float = 300.0
) -> None:
    """Set cover max open/close times to the maximum (300s).

    Called on daemon start to ensure the fan doesn't auto-stop too quickly.
    The daemon re-issues commands every cycle, so this is a safety net.
    """
    try:
        resp = await client.post(
            f"http://{host}/rpc/Cover.SetConfig",
            json={
                "id": 0,
                "config": {"maxtime_open": maxtime, "maxtime_close": maxtime},
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        logger.info("Configured cover timeouts to %.0fs on %s", maxtime, host)
    except Exception:
        logger.exception("Failed to configure cover timeouts on %s", host)
