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


async def test_valid_humidity_payload(webhook_client, sensor_cache):
    client = await webhook_client
    payload = {
        "src": "shellyhtg3-test",
        "method": "NotifyStatus",
        "params": {
            "ts": 1710000000.00,
            "humidity:0": {"rh": 65.2},
            "temperature:0": {"tC": 23.5, "tF": 74.3},
        },
    }
    resp = await client.post("/webhook/shelly", json=payload)
    assert resp.status == 200

    from datetime import datetime, timezone

    result = sensor_cache.get_humidity("shellyhtg3-test", datetime.now(timezone.utc))
    assert result == 65.2


async def test_temperature_only_payload(webhook_client, sensor_cache):
    client = await webhook_client
    payload = {
        "src": "shellyhtg3-test",
        "method": "NotifyStatus",
        "params": {
            "ts": 1710000000.00,
            "temperature:0": {"tC": 23.5},
        },
    }
    resp = await client.post("/webhook/shelly", json=payload)
    assert resp.status == 200

    from datetime import datetime, timezone

    # No humidity data, so cache should not have a reading
    result = sensor_cache.get_humidity("shellyhtg3-test", datetime.now(timezone.utc))
    assert result is None


async def test_invalid_json_returns_400(webhook_client):
    client = await webhook_client
    resp = await client.post(
        "/webhook/shelly",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


async def test_missing_src_returns_400(webhook_client):
    client = await webhook_client
    payload = {"method": "NotifyStatus", "params": {}}
    resp = await client.post("/webhook/shelly", json=payload)
    assert resp.status == 400
