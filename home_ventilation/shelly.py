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


async def refresh_fan_speed(client: httpx.AsyncClient, host: str, speed: FanSpeed) -> None:
    """Re-issue the current cover command to reset the auto-stop timer.

    Unlike set_fan_speed, this skips the Stop+sleep sequence — just re-sends
    the current command (Open/Close) as a single HTTP request. For OFF, issues
    Cover.Stop directly.
    """
    rpc_method = {
        FanSpeed.OFF: "Cover.Stop",
        FanSpeed.LOW: "Cover.Open",
        FanSpeed.HIGH: "Cover.Close",
    }
    method = rpc_method[speed]
    try:
        resp = await client.get(f"http://{host}/rpc/{method}", params={"id": 0}, timeout=5.0)
        resp.raise_for_status()
    except Exception:
        logger.exception("Failed to refresh %s on %s", speed.value, host)
        raise
    logger.debug("Refreshed fan speed %s on %s", speed.value, host)


async def configure_shelly_device(
    client: httpx.AsyncClient,
    host: str,
    switch_inputs: list[int],
    webhook_host: str,
    webhook_port: int,
) -> None:
    """Configure a Shelly 2PM on daemon start: cover, inputs, and webhooks.

    Best-effort — logs and continues on failure so one unreachable device
    doesn't block the rest.
    """
    try:
        await _configure_cover(client, host)
        await _configure_inputs(client, host)
        await _configure_webhooks(client, host, switch_inputs, webhook_host, webhook_port)
    except Exception:
        logger.exception("Failed to configure Shelly device %s", host)


async def _configure_cover(client: httpx.AsyncClient, host: str, maxtime: float = 300.0) -> None:
    """Set cover to detached + locked with max timeouts.

    in_locked is set in a separate call — firmware ignores it when sent
    together with in_mode (see CLAUDE.md).
    """
    resp = await client.post(
        f"http://{host}/rpc/Cover.SetConfig",
        json={
            "id": 0,
            "config": {
                "maxtime_open": maxtime,
                "maxtime_close": maxtime,
                "in_mode": "detached",
            },
        },
        timeout=5.0,
    )
    resp.raise_for_status()
    resp = await client.post(
        f"http://{host}/rpc/Cover.SetConfig",
        json={"id": 0, "config": {"in_locked": True}},
        timeout=5.0,
    )
    resp.raise_for_status()
    logger.info("Configured cover (detached + locked) on %s", host)


async def _configure_inputs(client: httpx.AsyncClient, host: str) -> None:
    """Ensure both inputs are type 'switch' (required for toggle events)."""
    for input_id in (0, 1):
        resp = await client.get(
            f"http://{host}/rpc/Input.GetConfig",
            params={"id": input_id},
            timeout=5.0,
        )
        resp.raise_for_status()
        if resp.json().get("type") != "switch":
            await client.post(
                f"http://{host}/rpc/Input.SetConfig",
                json={"id": input_id, "config": {"type": "switch"}},
                timeout=5.0,
            )
            logger.info("Set input:%d to switch type on %s", input_id, host)


async def _configure_webhooks(
    client: httpx.AsyncClient,
    host: str,
    switch_inputs: list[int],
    webhook_host: str,
    webhook_port: int,
) -> None:
    """Reconcile webhooks: create missing, fix wrong URLs, delete stale."""
    base_url = f"http://{webhook_host}:{webhook_port}/webhook/shelly"

    # Build desired webhook set
    desired: dict[tuple[int, str], dict] = {}
    for input_id in switch_inputs:
        for state, event in [("on", "input.toggle_on"), ("off", "input.toggle_off")]:
            desired[(input_id, event)] = {
                "cid": input_id,
                "event": event,
                "url": f"{base_url}?input_id={input_id}&state={state}",
                "name": f"Input ({input_id}) {'On' if state == 'on' else 'Off'}",
            }

    # Fetch current webhooks
    resp = await client.get(f"http://{host}/rpc/Webhook.List", timeout=5.0)
    resp.raise_for_status()
    current_hooks = resp.json().get("hooks", [])
    current: dict[tuple[int, str], dict] = {(h["cid"], h["event"]): h for h in current_hooks}

    changes = 0

    # Create missing
    for key, d in desired.items():
        if key not in current:
            await client.post(
                f"http://{host}/rpc/Webhook.Create",
                json={
                    "cid": d["cid"],
                    "enable": True,
                    "event": d["event"],
                    "urls": [d["url"]],
                    "name": d["name"],
                },
                timeout=5.0,
            )
            logger.info("Created webhook %s cid=%d on %s", d["event"], d["cid"], host)
            changes += 1

    # Fix wrong URLs
    for key, d in desired.items():
        if key in current and current[key]["urls"] != [d["url"]]:
            await client.post(
                f"http://{host}/rpc/Webhook.Update",
                json={"id": current[key]["id"], "urls": [d["url"]]},
                timeout=5.0,
            )
            logger.info("Updated webhook %s cid=%d on %s", d["event"], d["cid"], host)
            changes += 1

    # Delete stale
    for key, c in current.items():
        if key not in desired:
            await client.post(
                f"http://{host}/rpc/Webhook.Delete",
                json={"id": c["id"]},
                timeout=5.0,
            )
            logger.info("Deleted stale webhook %s cid=%d on %s", c["event"], c["cid"], host)
            changes += 1

    if changes == 0:
        logger.info("Webhooks already configured on %s", host)
