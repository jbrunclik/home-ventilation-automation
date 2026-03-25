import asyncio
import logging
import signal
import time
from datetime import datetime

import httpx

from home_ventilation.config import Config
from home_ventilation.fan import decide_speed
from home_ventilation.models import FanSpeed, FanState, TuyaSensorReading
from home_ventilation.sensor_cache import SensorCache
from home_ventilation.status_writer import write_status
from home_ventilation.shelly import (
    configure_humidity_sensor,
    configure_shelly_device,
    get_switch_inputs,
    refresh_fan_speed,
    set_fan_speed,
)
from home_ventilation.tuya import configure_tuya_sensor, poll_tuya_sensor
from home_ventilation.webhook import create_webhook_app, start_webhook_server

logger = logging.getLogger(__name__)


_SHUTDOWN_TIMEOUT_SECONDS = 10


def _compute_wait_timeout(
    poll_interval: float,
    reconciliation_interval: float,
    last_sensor_poll: float,
    last_command_times: dict[str, float],
    now_monotonic: float,
) -> float:
    """Compute sleep duration until the next poll or reconciliation deadline."""
    time_to_next_poll = poll_interval - (now_monotonic - last_sensor_poll)
    time_to_next_reconciliation = reconciliation_interval
    for t in last_command_times.values():
        remaining = reconciliation_interval - (now_monotonic - t)
        time_to_next_reconciliation = min(time_to_next_reconciliation, remaining)
    return max(0.0, min(time_to_next_poll, time_to_next_reconciliation))


async def run(config: Config) -> None:
    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()

    def _request_shutdown():
        if main_task and not main_task.done():
            main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_shutdown)

    shelly_client = httpx.AsyncClient(timeout=10.0)

    # Shared state for webhook-driven switch inputs
    switch_store: dict[str, dict[int, bool]] = {}
    reevaluate = asyncio.Event()

    sensor_cache = SensorCache(config.sensor_cache_path, config.humidity_stale_minutes)
    webhook_app = create_webhook_app(sensor_cache, switch_store, reevaluate)
    webhook_runner = await start_webhook_server(webhook_app, config.webhook_port)

    # Per-fan state
    fan_states: dict[str, FanState] = {fan.name: FanState() for fan in config.fans}

    # Track last command time per fan for reconciliation
    last_command_time: dict[str, float] = {fan.name: 0.0 for fan in config.fans}

    # Cached sensor readings per fan
    cached_readings: dict[str, list[TuyaSensorReading | None]] = {
        fan.name: [] for fan in config.fans
    }
    last_sensor_poll = 0.0  # force immediate first sensor read

    # Configure devices on startup
    for fan_cfg in config.fans:
        if fan_cfg.shelly_host:
            await configure_shelly_device(
                shelly_client,
                fan_cfg.shelly_host,
                fan_cfg.switch_inputs,
                config.webhook_host,
                config.webhook_port,
            )
            try:
                initial_switches = await get_switch_inputs(shelly_client, fan_cfg.shelly_host)
                switch_store[fan_cfg.shelly_host] = initial_switches
                logger.info("[%s] Seeded switch state: %s", fan_cfg.name, initial_switches)
            except Exception:
                logger.exception("[%s] Failed to seed switch state", fan_cfg.name)
                switch_store[fan_cfg.shelly_host] = {}
        for sensor_ip in fan_cfg.humidity_sensor_ips:
            await configure_humidity_sensor(
                shelly_client, sensor_ip, config.webhook_host, config.webhook_port
            )
        for sensor in fan_cfg.co2_sensors:
            await configure_tuya_sensor(sensor.device_id, sensor.ip, sensor.local_key)

    logger.info(
        "Starting ventilation daemon (sensors every %ds, reconciliation every %ds,"
        " webhook port %d), %d fan(s)",
        config.poll_interval_seconds,
        config.reconciliation_interval_seconds,
        config.webhook_port,
        len(config.fans),
    )

    try:
        while True:
            now = datetime.now().astimezone()  # aware local time for schedule checks
            monotonic_now = time.monotonic()

            # Read sensors if enough time has passed
            read_sensors = (monotonic_now - last_sensor_poll) >= config.poll_interval_seconds
            if read_sensors:
                last_sensor_poll = monotonic_now

            for fan_cfg in config.fans:
                try:
                    state = fan_states[fan_cfg.name]

                    # Poll Tuya sensors on the slow cadence (network I/O)
                    if read_sensors:
                        readings: list[TuyaSensorReading | None] = []
                        for sensor in fan_cfg.co2_sensors:
                            readings.append(
                                await poll_tuya_sensor(
                                    sensor.device_id, sensor.ip, sensor.local_key
                                )
                            )
                        cached_readings[fan_cfg.name] = readings

                    # Webhook humidity: read fresh every cycle (in-memory lookup)
                    humidity_values = [
                        sensor_cache.get_humidity(ip, now) for ip in fan_cfg.humidity_sensor_ips
                    ]

                    # Read switch states from webhook store (no HTTP)
                    if fan_cfg.shelly_host:
                        all_switches = switch_store.get(fan_cfg.shelly_host, {})
                        relevant_switches = {
                            k: v for k, v in all_switches.items() if k in fan_cfg.switch_inputs
                        }
                    else:
                        relevant_switches = {}

                    # Extract CO2 values for fan control (other readings are display-only)
                    co2_values = [r.co2 if r else None for r in cached_readings[fan_cfg.name]]

                    # Decide speed
                    new_speed, new_state = decide_speed(
                        co2_values=co2_values,
                        humidity_values=humidity_values,
                        switch_states=relevant_switches,
                        current_state=state,
                        thresholds=config.thresholds,
                        override_minutes=config.manual_override_minutes,
                        now=now,
                        schedule=fan_cfg.schedule,
                    )

                    speed_changed = new_speed != state.current_speed
                    elapsed = monotonic_now - last_command_time[fan_cfg.name]
                    needs_reconciliation = elapsed >= config.reconciliation_interval_seconds

                    if fan_cfg.shelly_host and (speed_changed or needs_reconciliation):
                        if speed_changed:
                            logger.info(
                                "[%s] Speed change: %s -> %s (CO2=%s, humidity=%s)",
                                fan_cfg.name,
                                state.current_speed.value,
                                new_speed.value,
                                co2_values,
                                humidity_values,
                            )
                            await set_fan_speed(shelly_client, fan_cfg.shelly_host, new_speed)
                        else:
                            logger.debug(
                                "[%s] Reconciliation: re-issuing %s",
                                fan_cfg.name,
                                new_speed.value,
                            )
                            await refresh_fan_speed(shelly_client, fan_cfg.shelly_host, new_speed)
                        last_command_time[fan_cfg.name] = monotonic_now
                    elif read_sensors:
                        logger.debug(
                            "[%s] Speed unchanged: %s (CO2=%s, humidity=%s)",
                            fan_cfg.name,
                            new_speed.value,
                            co2_values,
                            humidity_values,
                        )

                    fan_states[fan_cfg.name] = new_state

                except Exception:
                    logger.exception("[%s] Error in control cycle", fan_cfg.name)

            # Write status snapshot for external consumers (best-effort)
            write_status(
                config.status_file_path,
                config.fans,
                fan_states,
                cached_readings,
                sensor_cache,
                now,
            )

            # Wait for webhook event or next scheduled action (poll / reconciliation)
            timeout = _compute_wait_timeout(
                config.poll_interval_seconds,
                config.reconciliation_interval_seconds,
                last_sensor_poll,
                last_command_time,
                time.monotonic(),
            )
            try:
                await asyncio.wait_for(reevaluate.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass  # scheduled tick (poll or reconciliation)
            reevaluate.clear()

    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down")
        # Remove signal handlers so a second signal force-kills immediately
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)

        await webhook_runner.cleanup()
        await shelly_client.aclose()

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
