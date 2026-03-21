from home_ventilation.config import ThresholdsConfig


DEFAULT_THRESHOLDS = ThresholdsConfig(
    co2_low=800,
    co2_high=1200,
    humidity_low=60.0,
    humidity_high=70.0,
    co2_hysteresis=50,
    humidity_hysteresis=3.0,
)
