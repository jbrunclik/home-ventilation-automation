import asyncio
import logging
import signal
import time
from datetime import datetime, timezone

import httpx

from home_ventilation.config import Config
from home_ventilation.fan import decide_speed
from home_ventilation.homebridge import HomebridgeClient
from home_ventilation.models import FanSpeed, FanState
from home_ventilation.sensor_cache import SensorCache
from home_ventilation.shelly import configure_cover_timeouts, get_switch_inputs, set_fan_speed
from home_ventilation.webhook import create_webhook_app, start_webhook_server

logger = logging.getLogger(__name__)


_SHUTDOWN_TIMEOUT_SECONDS = 10


async def run(config: Config) -> None:
    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()

    def _request_shutdown():
        if main_task and not main_task.done():
            main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_shutdown)

    hb = HomebridgeClient(
        host=config.homebridge.host,
        port=config.homebridge.port,
        username=config.homebridge.username,
        password=config.homebridge.password,
    )

    shelly_client = httpx.AsyncClient(timeout=10.0)

    sensor_cache = SensorCache(config.sensor_cache_path, config.humidity_stale_minutes)
    webhook_app = create_webhook_app(sensor_cache)
    webhook_runner = await start_webhook_server(webhook_app, config.webhook_port)

    # Per-fan state
    fan_states: dict[str, FanState] = {fan.name: FanState() for fan in config.fans}

    # Cached sensor readings per fan
    cached_co2: dict[str, list[int | None]] = {fan.name: [] for fan in config.fans}
    cached_humidity: dict[str, list[float | None]] = {fan.name: [] for fan in config.fans}
    last_sensor_poll = 0.0  # force immediate first sensor read

    # Configure cover timeouts on startup
    for fan_cfg in config.fans:
        if fan_cfg.shelly_host:
            await configure_cover_timeouts(shelly_client, fan_cfg.shelly_host)

    logger.info(
        "Starting ventilation daemon (sensors every %ds, switches every %ds, webhook port %d),"
        " %d fan(s)",
        config.poll_interval_seconds,
        config.switch_poll_interval_seconds,
        config.webhook_port,
        len(config.fans),
    )

    try:
        while True:
            now = datetime.now(timezone.utc)
            monotonic_now = time.monotonic()

            # Read sensors if enough time has passed
            read_sensors = (monotonic_now - last_sensor_poll) >= config.poll_interval_seconds
            if read_sensors:
                last_sensor_poll = monotonic_now

            for fan_cfg in config.fans:
                try:
                    state = fan_states[fan_cfg.name]

                    # Poll Homebridge on the slow cadence (network I/O)
                    if read_sensors:
                        co2_values: list[int | None] = []
                        for acc_name in fan_cfg.co2_accessories:
                            co2_values.append(await hb.get_co2(acc_name))
                        cached_co2[fan_cfg.name] = co2_values

                        hb_humidity: list[float | None] = []
                        for acc_name in fan_cfg.humidity_accessories:
                            hb_humidity.append(await hb.get_humidity(acc_name))
                        cached_humidity[fan_cfg.name] = hb_humidity

                    # Webhook humidity: read fresh every cycle (in-memory lookup)
                    webhook_humidity = [
                        sensor_cache.get_humidity(ip, now) for ip in fan_cfg.humidity_sensor_ips
                    ]
                    humidity_values = cached_humidity[fan_cfg.name] + webhook_humidity

                    # Read switch inputs every cycle (fast)
                    if fan_cfg.shelly_host:
                        switch_states = await get_switch_inputs(shelly_client, fan_cfg.shelly_host)
                        relevant_switches = {
                            k: v for k, v in switch_states.items() if k in fan_cfg.switch_inputs
                        }
                    else:
                        relevant_switches = {}

                    # Decide speed
                    new_speed, new_state = decide_speed(
                        co2_values=cached_co2[fan_cfg.name],
                        humidity_values=humidity_values,
                        switch_states=relevant_switches,
                        current_state=state,
                        thresholds=config.thresholds,
                        override_minutes=config.manual_override_minutes,
                        now=now,
                    )

                    # Log on change, debug otherwise
                    if new_speed != state.current_speed:
                        logger.info(
                            "[%s] Speed change: %s -> %s (CO2=%s, humidity=%s)",
                            fan_cfg.name,
                            state.current_speed.value,
                            new_speed.value,
                            cached_co2[fan_cfg.name],
                            humidity_values,
                        )
                    elif read_sensors:
                        logger.debug(
                            "[%s] Speed unchanged: %s (CO2=%s, humidity=%s)",
                            fan_cfg.name,
                            new_speed.value,
                            cached_co2[fan_cfg.name],
                            humidity_values,
                        )

                    # Always re-issue to prevent cover mode auto-stop timeout
                    if fan_cfg.shelly_host:
                        await set_fan_speed(shelly_client, fan_cfg.shelly_host, new_speed)

                    fan_states[fan_cfg.name] = new_state

                except Exception:
                    logger.exception("[%s] Error in poll cycle", fan_cfg.name)

            await asyncio.sleep(config.switch_poll_interval_seconds)

    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down")
        # Remove signal handlers so a second signal force-kills immediately
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)

        await webhook_runner.cleanup()
        await shelly_client.aclose()
        await hb.close()

        # Turn off all fans on shutdown (with timeout)
        try:
            async with asyncio.timeout(_SHUTDOWN_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(timeout=5.0) as client:
                    for fan_cfg in config.fans:
                        if not fan_cfg.shelly_host:
                            continue
                        try:
                            await set_fan_speed(client, fan_cfg.shelly_host, FanSpeed.OFF)
                            logger.info("[%s] Turned off on shutdown", fan_cfg.name)
                        except Exception:
                            logger.exception("[%s] Failed to turn off on shutdown", fan_cfg.name)
        except TimeoutError:
            logger.warning("Timed out turning off fans during shutdown")
