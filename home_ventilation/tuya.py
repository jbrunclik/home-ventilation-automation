import asyncio
import logging

import tinytuya

logger = logging.getLogger(__name__)

# Tuya data point IDs for AIR_DETECTOR (category co2bj)
DP_CO2_VALUE = "2"
DP_ALARM_SWITCH = "13"
DP_ALARM_BRIGHT = "17"
DP_SCREEN_SLEEP = "108"

PROTOCOL_VERSION = 3.5
SOCKET_TIMEOUT = 5


def _connect(device_id: str, ip: str, local_key: str) -> tinytuya.Device:
    d = tinytuya.Device(device_id, ip, local_key, version=PROTOCOL_VERSION)
    d.set_socketTimeout(SOCKET_TIMEOUT)
    return d


def _poll_co2_sync(device_id: str, ip: str, local_key: str) -> int | None:
    d = _connect(device_id, ip, local_key)
    status = d.status()
    if "Error" in status:
        logger.warning("Tuya device %s (%s): %s", device_id, ip, status["Error"])
        return None
    dps = status.get("dps", {})
    raw = dps.get(DP_CO2_VALUE)
    if raw is None:
        logger.warning("Tuya device %s (%s): no CO2 value in response", device_id, ip)
        return None
    return int(raw)


async def poll_co2_sensor(device_id: str, ip: str, local_key: str) -> int | None:
    """Read CO2 ppm from a Tuya air quality sensor via local API."""
    try:
        return await asyncio.to_thread(_poll_co2_sync, device_id, ip, local_key)
    except Exception:
        logger.exception("Failed to poll CO2 from %s (%s)", device_id, ip)
        return None


def _configure_sync(device_id: str, ip: str, local_key: str) -> None:
    d = _connect(device_id, ip, local_key)

    # Disable alarm sound/LED, keep display always on
    d.set_value(DP_ALARM_SWITCH, False)
    d.set_value(DP_ALARM_BRIGHT, 0)
    d.set_value(DP_SCREEN_SLEEP, False)

    logger.info("Configured Tuya sensor %s (%s): alarm off, screen sleep off", device_id, ip)


async def configure_tuya_sensor(device_id: str, ip: str, local_key: str) -> None:
    """Configure a Tuya CO2 sensor on daemon startup (best-effort)."""
    try:
        await asyncio.to_thread(_configure_sync, device_id, ip, local_key)
    except Exception:
        logger.exception("Failed to configure Tuya sensor %s (%s)", device_id, ip)
