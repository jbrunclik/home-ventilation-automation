import asyncio
import logging

from aiohttp import web

from home_ventilation.sensor_cache import SensorCache

logger = logging.getLogger(__name__)


async def _handle_shelly_webhook(request: web.Request) -> web.Response:
    sensor_cache: SensorCache = request.app["sensor_cache"]
    switch_store: dict[str, dict[int, bool]] = request.app["switch_store"]
    reevaluate: asyncio.Event = request.app["reevaluate"]
    src_ip = request.remote

    # Dispatch by query params: humidity vs switch input
    hum = request.query.get("hum")
    input_id_raw = request.query.get("input_id")

    if hum is not None:
        humidity = float(hum)
        sensor_cache.update(src_ip, humidity)
        logger.info("Webhook: %s humidity=%.1f%%", src_ip, humidity)
        reevaluate.set()
    elif input_id_raw is not None:
        state_raw = request.query.get("state")
        if state_raw is None:
            logger.warning("Webhook: %s input_id=%s but no state param", src_ip, input_id_raw)
            return web.Response(text="OK")

        try:
            input_id = int(input_id_raw)
        except ValueError:
            logger.warning("Webhook: %s invalid input_id=%r", src_ip, input_id_raw)
            return web.Response(text="OK")

        state = state_raw.lower() == "on"
        if src_ip not in switch_store:
            switch_store[src_ip] = {}
        switch_store[src_ip][input_id] = state

        logger.info("Webhook: %s input_id=%d state=%s", src_ip, input_id, state)
        reevaluate.set()
    else:
        logger.info("Webhook: %s unrecognized params: %s", src_ip, dict(request.query))

    return web.Response(text="OK")


def create_webhook_app(
    sensor_cache: SensorCache,
    switch_store: dict[str, dict[int, bool]],
    reevaluate: asyncio.Event,
) -> web.Application:
    app = web.Application()
    app["sensor_cache"] = sensor_cache
    app["switch_store"] = switch_store
    app["reevaluate"] = reevaluate
    app.router.add_route("*", "/webhook/shelly", _handle_shelly_webhook)
    return app


async def start_webhook_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
