# Home Ventilation Automation

Automated control of bathroom exhaust fans (Ruck EC motors) based on CO2 levels, humidity, and manual wall switches. Runs as a Python daemon on "goldfinger" via user systemd unit.

## Architecture

- **Sensor data**: Homebridge Config UI X REST API (`/api/accessories`) — CO2 (Tuya via Smart Life) and humidity (Shelly H&T)
- **Fan control**: Shelly 2PM Gen4 HTTP API (Gen2+ RPC: `/rpc/Switch.Set`, `/rpc/Input.GetStatus`)
- **Config**: `config.toml` (thresholds, IPs) + `.env` (Homebridge credentials)

### Fan speed via Shelly 2PM relays
- OFF: both relays off
- LOW: relay 0 on, relay 1 off
- HIGH: relay 0 off, relay 1 on
- Never both on simultaneously

### Decision priority (highest → lowest)
1. Manual switch press → HIGH for configurable cooldown
2. Humidity: >70% → HIGH, 60–70% → LOW
3. CO2: >1200 ppm → HIGH, 800–1200 ppm → LOW, <800 → OFF

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
| `shelly.py` | Shelly Gen2+ RPC client (relays + inputs) |
| `daemon.py` | Async main loop, orchestration |
| `__main__.py` | CLI entry point |

## Conventions

- Python 3.12+, async/await with httpx
- Pure decision logic in `fan.py` (easy to test, no I/O)
- Ruff for linting/formatting, line-length 99
- Tests focus on `fan.py` decision logic
