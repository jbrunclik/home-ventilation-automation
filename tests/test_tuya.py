from home_ventilation.models import TuyaSensorReading
from home_ventilation.tuya import _parse_dps


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
