from home_ventilation.models import TuyaSensorReading
from home_ventilation.tuya import _has_zero_sentinel, _parse_dps


def test_all_dps_present():
    dps = {"2": 850, "18": 22, "19": 48, "101": 12}
    assert _parse_dps(dps) == TuyaSensorReading(
        co2=850, temperature=22.0, humidity=48.0, pm25=12.0
    )


def test_co2_only():
    dps = {"2": 750, "13": False, "17": 0}
    assert _parse_dps(dps) == TuyaSensorReading(co2=750)


def test_no_sensor_dps():
    dps = {"13": False, "17": 0, "108": False}
    assert _parse_dps(dps) is None


def test_empty_dps():
    assert _parse_dps({}) is None


def test_partial_dps():
    dps = {"18": 20, "101": 30}
    assert _parse_dps(dps) == TuyaSensorReading(temperature=20.0, pm25=30.0)


def test_zero_temperature_and_humidity_dropped():
    """Observed sentinel: the sensing element is dead but the device answers.

    Zeros previously reached the dashboard, rendering PM2.5 0.0 as a healthy
    reading. CO2 is kept — the reading cache catches it being frozen.
    """
    dps = {"2": 511, "18": 0, "19": 0, "101": 0}
    assert _parse_dps(dps) == TuyaSensorReading(co2=511)


def test_zero_temperature_with_plausible_humidity_is_kept():
    dps = {"2": 800, "18": 0, "19": 45}
    assert _parse_dps(dps) == TuyaSensorReading(co2=800, temperature=0.0, humidity=45.0)


def test_zero_humidity_with_plausible_temperature_is_kept():
    dps = {"2": 800, "18": 21, "19": 0}
    assert _parse_dps(dps) == TuyaSensorReading(co2=800, temperature=21.0, humidity=0.0)


def test_zero_sentinel_with_no_co2_yields_no_reading():
    dps = {"18": 0, "19": 0, "101": 0}
    assert _parse_dps(dps) is None


def test_zero_sentinel_detection():
    assert _has_zero_sentinel({"18": 0, "19": 0}) is True
    assert _has_zero_sentinel({"18": 0, "19": 45}) is False
    assert _has_zero_sentinel({"2": 800}) is False
