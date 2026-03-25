import asyncio
import logging

import tinytuya

from home_ventilation.models import TuyaSensorReading

logger = logging.getLogger(__name__)

# Tuya data point IDs for AIR_DETECTOR (category co2bj)
DP_CO2_VALUE = "2"
DP_ALARM_SWITCH = "13"
DP_ALARM_BRIGHT = "17"
DP_TEMPERATURE = "18"
DP_HUMIDITY = "19"
DP_PM25 = "101"
DP_SCREEN_SLEEP = "108"

PROTOCOL_VERSION = 3.5
SOCKET_TIMEOUT = 5


def _connect(device_id: str, ip: str, local_key: str) -> tinytuya.Device:
    d = tinytuya.Device(device_id, ip, local_key, version=PROTOCOL_VERSION)
    d.set_socketTimeout(SOCKET_TIMEOUT)
    return d


def _parse_dps(dps: dict) -> TuyaSensorReading | None:
    """Extract sensor values from Tuya DPS dict."""
    co2_raw = dps.get(DP_CO2_VALUE)
    temp_raw = dps.get(DP_TEMPERATURE)
    hum_raw = dps.get(DP_HUMIDITY)
    pm25_raw = dps.get(DP_PM25)

    co2 = int(co2_raw) if co2_raw is not None else None
    temperature = float(temp_raw) if temp_raw is not None else None
    humidity = float(hum_raw) if hum_raw is not None else None
    pm25 = float(pm25_raw) if pm25_raw is not None else None

    if co2 is None and temperature is None and humidity is None and pm25 is None:
        return None
    return TuyaSensorReading(co2=co2, temperature=temperature, humidity=humidity, pm25=pm25)


def _poll_sensor_sync(device_id: str, ip: str, local_key: str) -> TuyaSensorReading | None:
    d = _connect(device_id, ip, local_key)
    status = d.status()
    if "Error" in status:
        logger.warning("Tuya device %s (%s): %s", device_id, ip, status["Error"])
        return None
    dps = status.get("dps", {})
    reading = _parse_dps(dps)
    if reading is None:
        logger.warning("Tuya device %s (%s): no sensor data in response", device_id, ip)
    return reading


async def poll_tuya_sensor(device_id: str, ip: str, local_key: str) -> TuyaSensorReading | None:
    """Read all sensor values from a Tuya air quality sensor via local API."""
    try:
        return await asyncio.to_thread(_poll_sensor_sync, device_id, ip, local_key)
    except Exception:
        logger.exception("Failed to poll sensor %s (%s)", device_id, ip)
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
