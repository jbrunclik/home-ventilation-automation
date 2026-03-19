import logging

from aiohttp import web

from home_ventilation.sensor_cache import SensorCache

logger = logging.getLogger(__name__)


async def _handle_shelly_webhook(request: web.Request) -> web.Response:
    sensor_cache: SensorCache = request.app["sensor_cache"]
    src_ip = request.remote

    hum = request.query.get("hum")

    if hum is not None:
        humidity = float(hum)
        sensor_cache.update(src_ip, humidity)
        logger.info("Webhook: %s humidity=%.1f%%", src_ip, humidity)
    else:
        logger.info("Webhook: %s no humidity data (params: %s)", src_ip, dict(request.query))

    return web.Response(text="OK")


def create_webhook_app(sensor_cache: SensorCache) -> web.Application:
    app = web.Application()
    app["sensor_cache"] = sensor_cache
    app.router.add_route("*", "/webhook/shelly", _handle_shelly_webhook)
    return app


async def start_webhook_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
