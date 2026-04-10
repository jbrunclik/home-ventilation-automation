# Home Ventilation Automation

Automated control of bathroom exhaust fans (Ruck EC motors) based on CO2 levels, humidity, and manual wall switches. Runs as a Python daemon on "goldfinger" via user systemd unit.

## Architecture

- **CO2 data**: Tuya air quality sensors via local API (tinytuya, port 6668, protocol 3.5, AES-encrypted)
- **Humidity data**: Shelly H&T Gen3 webhook push (battery-powered, no polling)
- **Fan control**: Shelly 2PM Gen4 HTTP API (Gen2+ RPC, cover mode: `/rpc/Cover.Open`, `/rpc/Cover.Close`, `/rpc/Cover.Stop`)
- **Switch input**: Shelly 2PM webhook push (`/webhook/shelly?input_id=N&state=on|off`) — 4 actions per device (input × toggle_on/off, no variable substitution)
- **Config**: `config.toml` (thresholds, IPs, Tuya device keys)

### Event-driven loop (three timing layers)
| Layer | Interval | Purpose |
|---|---|---|
| Webhook (instant) | Push from Shelly | Switch input changes + humidity updates |
| Sensor poll (30s) | `poll_interval_seconds` | CO2 from Tuya sensors (local API) |
| Reconciliation (60s) | `reconciliation_interval_seconds` | Re-issue cover command to prevent 300s auto-stop |

The main loop awaits an `asyncio.Event` with reconciliation timeout — webhooks and sensor polls set the event to wake it immediately.

### Fan speed via Shelly 2PM cover mode
- OFF: `Cover.Stop` (both relays off)
- LOW: `Cover.Open` (relay 0)
- HIGH: `Cover.Close` (relay 1)
- **CRITICAL: Shelly MUST stay in cover mode — NEVER switch to relay/switch mode.** Cover mode enforces mutual exclusion (only one relay on at a time). If both relays energize simultaneously, both motor windings activate and the motor burns out.

### Decision priority (highest → lowest)
1. Manual switch ON → HIGH while held; cooldown timer starts on release
2. Humidity: >70% → HIGH, 60–70% → LOW (capped by `max_speed` during schedule window)
3. CO2: >1200 ppm → HIGH, 800–1200 ppm → LOW, <800 → OFF (capped by `max_speed` during schedule window)
4. Time-based schedule (per-fan, optional) → configurable speed (`run_minutes=0` disables periodic runs)

Hysteresis: thresholds 2–3 have a dead band (`co2_hysteresis`, `humidity_hysteresis`) to prevent toggling when a sensor hovers near a boundary. The "turn on" threshold is unchanged; the "turn off" threshold is lowered by the hysteresis margin when the fan is already at/above the guarded speed (e.g. OFF→LOW at 800 ppm, LOW→OFF at 750 ppm with `co2_hysteresis=50`).

### Tuya CO2 sensors
- Category `co2bj` (AIR_DETECTOR), protocol 3.5
- DP 2 = `co2_value` (ppm), DP 18 = `temperature` (°C), DP 19 = `humidity` (%), DP 101 = `pm25` (µg/m³)
- DP 13 = `alarm_switch`, DP 17 = `alarm_bright`, DP 108 = `screen_sleep`
- tinytuya is synchronous — all calls wrapped with `asyncio.to_thread()`
- On startup: alarm disabled (DP 13 → False, DP 17 → 0)
- Local key retrieved once from Tuya IoT Developer Platform, stored in `config.toml`

## Commands

```bash
make dev       # install all deps (uv sync)
make lint      # ruff check + format check
make format    # ruff format + auto-fix
make test      # pytest
make deploy    # install systemd unit, enable service
make logs      # follow journald logs
make status    # systemctl status
make restart   # systemctl restart
```

## Module Map

| Module | Responsibility |
|---|---|
| `config.py` | TOML loading → frozen dataclasses |
| `models.py` | `FanSpeed` enum, `FanState` dataclass |
| `fan.py` | Pure decision logic (no I/O) |
| `tuya.py` | Tuya local API client (sensor polling + device config) |
| `shelly.py` | Shelly Gen2+ RPC client (relays + inputs + cover refresh + device setup) |
| `webhook.py` | aiohttp webhook server (humidity + switch input from Shelly devices) |
| `status_writer.py` | Atomic JSON status snapshot for external consumers (dashboard) |
| `daemon.py` | Event-driven main loop, orchestration |
| `__main__.py` | CLI entry point |
| `shelly-scripts/cover-switch-override.js` | Standalone Shelly script — same decision logic, runs on-device |
| `firmware/` | ESP32 standalone controller (M5Stack AtomS3R) — full daemon port for apartments without a server |
| `firmware/src/fan_logic.cpp` | C++ port of `fan.py` decision logic (CO2 only, no humidity) |
| `firmware/src/tuya_client.cpp` | Tuya protocol 3.5 client (TCP + AES-GCM via Rhys Weatherley Crypto lib) |
| `firmware/src/shelly_client.cpp` | Shelly HTTP API client (cover control + device config + script removal) |
| `firmware/src/display.cpp` | 128x128 IPS display — CO2 readout, fan status, live override countdown |

## Conventions

- Python 3.12+, async/await with httpx
- Pure decision logic in `fan.py` (easy to test, no I/O)
- Ruff for linting/formatting, line-length 99
- Tests focus on `fan.py` decision logic
- When changing config options: update `config.example.toml`, `CLAUDE.md`, and decision priority list
- Shelly cover input isolation: use `in_mode: "detached"` + `in_locked: true` in **separate** `Cover.SetConfig` calls (firmware ignores `in_locked` when sent with `in_mode`)
- Wall toggle switches require Shelly input type `"switch"` (not `"button"`) to generate `"toggle"` events
- Shelly webhook URL template variables use `${token}` syntax (e.g. `${ev.rh}` for humidity). `$variable` shorthand (e.g. `$humidity`) does NOT work — it gets sent literally
- Firmware `FanSpeed` enum uses `SPEED_OFF`, `SPEED_LOW`, `SPEED_HIGH` — Arduino defines `LOW`/`HIGH` as macros, so bare names cause compilation errors
