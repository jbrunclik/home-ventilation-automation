import logging

from aiohttp import web

from home_ventilation.sensor_cache import SensorCache

logger = logging.getLogger(__name__)


async def _handle_shelly_webhook(request: web.Request) -> web.Response:
    sensor_cache: SensorCache = request.app["sensor_cache"]

    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    src = payload.get("src")
    if not src:
        return web.Response(status=400, text="Missing 'src' field")

    logger.debug("Shelly webhook payload from %s: %s", src, payload)

    params = payload.get("params", {})
    humidity_data = params.get("humidity:0")
    temperature_data = params.get("temperature:0")

    humidity = humidity_data.get("rh") if humidity_data else None
    temperature = temperature_data.get("tC") if temperature_data else None

    if humidity is not None:
        sensor_cache.update(src, humidity, temperature)
        logger.info("Webhook: %s humidity=%.1f%% temperature=%s", src, humidity, temperature)
    else:
        logger.info("Webhook: %s notification without humidity data", src)

    return web.Response(text="OK")


def create_webhook_app(sensor_cache: SensorCache) -> web.Application:
    app = web.Application()
    app["sensor_cache"] = sensor_cache
    app.router.add_post("/webhook/shelly", _handle_shelly_webhook)
    return app


async def start_webhook_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
