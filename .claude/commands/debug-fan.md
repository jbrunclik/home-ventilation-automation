Diagnose fan control issues. Walk through the decision logic for a specific fan.

1. Read the current `config.example.toml` (or `config.toml` if it exists) to understand the fan configuration
2. Trace through `home_ventilation/fan.py:decide_speed()` with the user's reported sensor values
3. Explain what speed the fan should be at and why, based on the priority rules:
   - Priority 1: Manual override (switch press → HIGH for override duration)
   - Priority 2: Humidity (>70% → HIGH, 60-70% → LOW)
   - Priority 3: CO2 (>1200 ppm → HIGH, 800-1200 ppm → LOW, <800 → OFF)
4. If the user reports unexpected behavior, check the relevant API client code in `homebridge.py` or `shelly.py`

Ask the user: Which fan is misbehaving, and what sensor values are you seeing?
