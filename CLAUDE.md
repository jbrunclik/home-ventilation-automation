# Home Ventilation Automation

Automated control of bathroom exhaust fans (Ruck EC motors) based on CO2 levels, humidity, and manual wall switches. Runs as a Python daemon on "goldfinger" via user systemd unit.

## Architecture

- **Sensor data**: Homebridge Config UI X REST API (`/api/accessories`) — CO2 (Tuya via Smart Life) and humidity (Shelly H&T)
- **Fan control**: Shelly 2PM Gen4 HTTP API (Gen2+ RPC, cover mode: `/rpc/Cover.Open`, `/rpc/Cover.Close`, `/rpc/Cover.Stop`)
- **Switch input**: Shelly 2PM webhook push (`/webhook/shelly?input_id=N&state=on|off`) — 4 actions per device (input × toggle_on/off, no variable substitution)
- **Config**: `config.toml` (thresholds, IPs) + `.env` (Homebridge credentials)

### Event-driven loop (three timing layers)
| Layer | Interval | Purpose |
|---|---|---|
| Webhook (instant) | Push from Shelly | Switch input changes + humidity updates |
| Sensor poll (30s) | `poll_interval_seconds` | CO2 + humidity from Homebridge |
| Reconciliation (60s) | `reconciliation_interval_seconds` | Re-issue cover command to prevent 300s auto-stop |

The main loop awaits an `asyncio.Event` with reconciliation timeout — webhooks and sensor polls set the event to wake it immediately.

### Fan speed via Shelly 2PM cover mode
- OFF: `Cover.Stop` (both relays off)
- LOW: `Cover.Open` (relay 0)
- HIGH: `Cover.Close` (relay 1)
- Cover mode prevents both relays from being on simultaneously (motor protection)

### Decision priority (highest → lowest)
1. Manual switch press → HIGH for configurable cooldown
2. Humidity: >70% → HIGH, 60–70% → LOW
3. CO2: >1200 ppm → HIGH, 800–1200 ppm → LOW, <800 → OFF
4. Time-based schedule (per-fan, optional) → configurable speed

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
| `config.py` | TOML + env var loading → frozen dataclasses |
| `models.py` | `FanSpeed` enum, `FanState` dataclass |
| `fan.py` | Pure decision logic (no I/O) |
| `homebridge.py` | Homebridge REST API client (sensors) |
| `shelly.py` | Shelly Gen2+ RPC client (relays + inputs + cover refresh) |
| `webhook.py` | aiohttp webhook server (humidity + switch input from Shelly devices) |
| `daemon.py` | Event-driven main loop, orchestration |
| `__main__.py` | CLI entry point |

## Conventions

- Python 3.12+, async/await with httpx
- Pure decision logic in `fan.py` (easy to test, no I/O)
- Ruff for linting/formatting, line-length 99
- Tests focus on `fan.py` decision logic
- When changing config options: update `config.example.toml`, `CLAUDE.md`, and decision priority list
