# Home Ventilation Automation

Automated control of bathroom exhaust fans (Ruck EC motors) based on CO2 levels, humidity, and manual wall switches. Monitors 3 bedrooms and 3 bathrooms, controlling 2 Shelly 2PM Gen4 devices.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Homebridge with Config UI X running (CO2 + humidity accessories)
- Shelly 2PM Gen4 devices controlling the Ruck fans

## Quick Start

```bash
# Install dependencies
make dev

# Copy and edit config
cp config.example.toml config.toml
cp .env.example .env
# Edit config.toml with your device IPs and accessory names
# Edit .env with your Homebridge credentials

# Run tests
make test

# Run locally
uv run home-ventilation --config config.toml

# Deploy as systemd user service on target machine
make deploy
```

## Configuration

### `config.toml`

| Key | Description | Default |
|---|---|---|
| `poll_interval_seconds` | Sensor polling interval | 30 |
| `manual_override_minutes` | Duration of manual override | 15 |
| `thresholds.co2_low` | CO2 ppm threshold for LOW speed | 800 |
| `thresholds.co2_high` | CO2 ppm threshold for HIGH speed | 1200 |
| `thresholds.humidity_low` | Humidity % threshold for LOW speed | 60.0 |
| `thresholds.humidity_high` | Humidity % threshold for HIGH speed | 70.0 |

Each fan section (`[fans.<name>]`) specifies:
- `shelly_host` — IP of the Shelly 2PM Gen4
- `co2_accessories` — Homebridge accessory names for CO2 sensors
- `humidity_accessories` — Homebridge accessory names for humidity sensors
- `switch_inputs` — Shelly input IDs for wall switches

### `.env`

```
HOMEBRIDGE_USERNAME=admin
HOMEBRIDGE_PASSWORD=admin
```

## Fan Speed Mapping

The Shelly 2PM Gen4 controls fan speed via two relays connected to the Ruck EC motor:

| Speed | Relay 0 | Relay 1 |
|---|---|---|
| OFF | off | off |
| LOW | on | off |
| HIGH | off | on |

## Deployment

The daemon runs as a user systemd service. `make deploy` copies config files to `~/.config/home-ventilation/` and installs the service unit.

```bash
make deploy   # install and start
make status   # check status
make logs     # follow logs
make restart  # restart after config change
```
