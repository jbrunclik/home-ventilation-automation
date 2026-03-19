import pytest

from home_ventilation.sensor_cache import SensorCache
from home_ventilation.webhook import create_webhook_app


@pytest.fixture
def sensor_cache(tmp_path):
    return SensorCache(str(tmp_path / "cache.json"), stale_minutes=120)


@pytest.fixture
def webhook_client(sensor_cache, aiohttp_client):
    app = create_webhook_app(sensor_cache)
    return aiohttp_client(app)


async def test_valid_humidity_param(webhook_client, sensor_cache):
    client = await webhook_client
    resp = await client.get("/webhook/shelly", params={"hum": "65.2"})
    assert resp.status == 200

    from datetime import datetime, timezone

    # aiohttp test client uses 127.0.0.1 as remote
    result = sensor_cache.get_humidity("127.0.0.1", datetime.now(timezone.utc))
    assert result == 65.2


async def test_no_humidity_param(webhook_client, sensor_cache):
    client = await webhook_client
    resp = await client.get("/webhook/shelly")
    assert resp.status == 200

    from datetime import datetime, timezone

    result = sensor_cache.get_humidity("127.0.0.1", datetime.now(timezone.utc))
    assert result is None
