"""Tests for the Shelly 2PM cover-mode fan control client.

Cover mode is what prevents both motor relays from energizing at once. The
sequencing assertions here are safety invariants, not style preferences — see
the motor-burnout warning in CLAUDE.md.
"""

import httpx
import pytest

from home_ventilation.models import FanSpeed
from home_ventilation.shelly import (
    get_cover_status,
    get_switch_inputs,
    refresh_fan_speed,
    set_fan_speed,
)

HOST = "10.0.0.53"


def _client(handler):
    """Build an AsyncClient backed by a recording mock transport."""
    calls: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler)), calls


def _ok(payload=None):
    return lambda request: httpx.Response(200, json=payload or {})


def _paths(calls):
    return [c.url.path for c in calls]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """The 0.5s stop-transition delay is asserted separately, not waited on."""
    slept = []

    async def _sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("home_ventilation.shelly.asyncio.sleep", _sleep)
    return slept


class TestSetFanSpeed:
    @pytest.mark.parametrize(
        ("speed", "expected"),
        [
            (FanSpeed.LOW, "/rpc/Cover.Open"),
            (FanSpeed.HIGH, "/rpc/Cover.Close"),
        ],
    )
    async def test_always_stops_before_switching(self, speed, expected):
        """Cover cannot move directly between Open and Close."""
        client, calls = _client(_ok())
        async with client:
            await set_fan_speed(client, HOST, speed)

        assert _paths(calls) == ["/rpc/Cover.Stop", expected]

    async def test_off_issues_stop_only(self):
        client, calls = _client(_ok())
        async with client:
            await set_fan_speed(client, HOST, FanSpeed.OFF)

        assert _paths(calls) == ["/rpc/Cover.Stop"]

    async def test_waits_between_stop_and_the_new_command(self, no_sleep):
        client, _ = _client(_ok())
        async with client:
            await set_fan_speed(client, HOST, FanSpeed.HIGH)

        assert no_sleep == [0.5]

    async def test_off_does_not_wait(self, no_sleep):
        client, _ = _client(_ok())
        async with client:
            await set_fan_speed(client, HOST, FanSpeed.OFF)

        assert no_sleep == []

    async def test_targets_cover_id_zero(self):
        client, calls = _client(_ok())
        async with client:
            await set_fan_speed(client, HOST, FanSpeed.LOW)

        assert all(c.url.params["id"] == "0" for c in calls)

    async def test_failure_propagates_to_the_caller(self):
        client, _ = _client(lambda r: httpx.Response(500))
        async with client:
            with pytest.raises(httpx.HTTPStatusError):
                await set_fan_speed(client, HOST, FanSpeed.LOW)

    async def test_never_opens_and_closes_in_one_call(self):
        """Both relays energizing together burns out the motor."""
        client, calls = _client(_ok())
        async with client:
            await set_fan_speed(client, HOST, FanSpeed.HIGH)

        paths = _paths(calls)
        assert not ("/rpc/Cover.Open" in paths and "/rpc/Cover.Close" in paths)


class TestRefreshFanSpeed:
    @pytest.mark.parametrize(
        ("speed", "expected"),
        [
            (FanSpeed.OFF, "/rpc/Cover.Stop"),
            (FanSpeed.LOW, "/rpc/Cover.Open"),
            (FanSpeed.HIGH, "/rpc/Cover.Close"),
        ],
    )
    async def test_reissues_a_single_command(self, speed, expected):
        """Refresh resets the 300s auto-stop; it must not stop the fan first."""
        client, calls = _client(_ok())
        async with client:
            await refresh_fan_speed(client, HOST, speed)

        assert _paths(calls) == [expected]

    async def test_does_not_sleep(self, no_sleep):
        client, _ = _client(_ok())
        async with client:
            await refresh_fan_speed(client, HOST, FanSpeed.LOW)

        assert no_sleep == []

    async def test_failure_propagates(self):
        client, _ = _client(lambda r: httpx.Response(503))
        async with client:
            with pytest.raises(httpx.HTTPStatusError):
                await refresh_fan_speed(client, HOST, FanSpeed.LOW)


class TestGetCoverStatus:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("opening", FanSpeed.LOW),
            ("closing", FanSpeed.HIGH),
            ("stopped", FanSpeed.OFF),
            ("open", FanSpeed.OFF),
            ("unknown-state", FanSpeed.OFF),
        ],
    )
    async def test_maps_cover_state_to_speed(self, state, expected):
        client, _ = _client(_ok({"state": state}))
        async with client:
            assert await get_cover_status(client, HOST) == expected

    async def test_unreachable_device_reads_as_off(self):
        client, _ = _client(lambda r: httpx.Response(500))
        async with client:
            assert await get_cover_status(client, HOST) == FanSpeed.OFF

    async def test_missing_state_key_reads_as_off(self):
        client, _ = _client(_ok({}))
        async with client:
            assert await get_cover_status(client, HOST) == FanSpeed.OFF


class TestGetSwitchInputs:
    async def test_reads_both_inputs(self):
        def handler(request):
            input_id = request.url.params["id"]
            return httpx.Response(200, json={"state": input_id == "0"})

        client, calls = _client(handler)
        async with client:
            result = await get_switch_inputs(client, HOST)

        assert result == {0: True, 1: False}
        assert len(calls) == 2

    async def test_one_failing_input_does_not_lose_the_other(self):
        def handler(request):
            if request.url.params["id"] == "0":
                return httpx.Response(500)
            return httpx.Response(200, json={"state": True})

        client, _ = _client(handler)
        async with client:
            result = await get_switch_inputs(client, HOST)

        assert result == {1: True}

    async def test_all_failing_yields_empty(self):
        client, _ = _client(lambda r: httpx.Response(500))
        async with client:
            assert await get_switch_inputs(client, HOST) == {}
