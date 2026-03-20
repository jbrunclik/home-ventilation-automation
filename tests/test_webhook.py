import asyncio
from datetime import datetime, timezone

import pytest

from home_ventilation.sensor_cache import SensorCache
from home_ventilation.webhook import create_webhook_app


@pytest.fixture
def sensor_cache(tmp_path):
    return SensorCache(str(tmp_path / "cache.json"), stale_minutes=120)


@pytest.fixture
def switch_store():
    return {}


@pytest.fixture
def reevaluate():
    return asyncio.Event()


@pytest.fixture
def webhook_client(sensor_cache, switch_store, reevaluate, aiohttp_client):
    app = create_webhook_app(sensor_cache, switch_store, reevaluate)
    return aiohttp_client(app)


# --- Humidity webhook tests ---


async def test_valid_humidity_param(webhook_client, sensor_cache, reevaluate):
    client = await webhook_client
    resp = await client.get("/webhook/shelly", params={"hum": "65.2"})
    assert resp.status == 200

    result = sensor_cache.get_humidity("127.0.0.1", datetime.now(timezone.utc))
    assert result == 65.2
    assert reevaluate.is_set()


async def test_no_recognized_param(webhook_client, sensor_cache, reevaluate):
    client = await webhook_client
    resp = await client.get("/webhook/shelly")
    assert resp.status == 200

    result = sensor_cache.get_humidity("127.0.0.1", datetime.now(timezone.utc))
    assert result is None
    assert not reevaluate.is_set()


# --- Switch input webhook tests ---


async def test_valid_input_params(webhook_client, switch_store, reevaluate):
    client = await webhook_client
    resp = await client.get("/webhook/shelly", params={"input_id": "0", "state": "on"})
    assert resp.status == 200
    assert switch_store["127.0.0.1"] == {0: True}
    assert reevaluate.is_set()


async def test_input_state_off(webhook_client, switch_store, reevaluate):
    client = await webhook_client
    resp = await client.get("/webhook/shelly", params={"input_id": "1", "state": "off"})
    assert resp.status == 200
    assert switch_store["127.0.0.1"] == {1: False}
    assert reevaluate.is_set()


async def test_input_missing_state(webhook_client, switch_store, reevaluate):
    client = await webhook_client
    resp = await client.get("/webhook/shelly", params={"input_id": "0"})
    assert resp.status == 200
    assert "127.0.0.1" not in switch_store
    assert not reevaluate.is_set()


async def test_input_invalid_input_id(webhook_client, switch_store, reevaluate):
    client = await webhook_client
    resp = await client.get("/webhook/shelly", params={"input_id": "abc", "state": "on"})
    assert resp.status == 200
    assert "127.0.0.1" not in switch_store
    assert not reevaluate.is_set()


async def test_multiple_inputs_same_host(webhook_client, switch_store):
    client = await webhook_client
    await client.get("/webhook/shelly", params={"input_id": "0", "state": "on"})
    await client.get("/webhook/shelly", params={"input_id": "1", "state": "off"})
    assert switch_store["127.0.0.1"] == {0: True, 1: False}
