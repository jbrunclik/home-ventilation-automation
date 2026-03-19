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
| `webhook_port` | HTTP port for Shelly H&T webhooks | 8090 |
| `sensor_cache_path` | Path for cached webhook sensor data | `/dev/shm/home-ventilation-sensor-cache.json` |
| `humidity_stale_minutes` | Ignore webhook readings older than this | 120 |
| `thresholds.co2_low` | CO2 ppm threshold for LOW speed | 800 |
| `thresholds.co2_high` | CO2 ppm threshold for HIGH speed | 1200 |
| `thresholds.humidity_low` | Humidity % threshold for LOW speed | 60.0 |
| `thresholds.humidity_high` | Humidity % threshold for HIGH speed | 70.0 |

Each fan section (`[fans.<name>]`) specifies:
- `shelly_host` — IP of the Shelly 2PM Gen4
- `co2_accessories` — Homebridge accessory names for CO2 sensors
- `humidity_accessories` — Homebridge accessory names for humidity sensors
- `humidity_sensor_ids` — Shelly H&T Gen3 device IDs for webhook humidity
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

## Shelly H&T Gen3 Webhook Setup

Shelly H&T Gen3 sensors are battery-powered and spend most of their time in deep sleep. They can't be polled — instead, they wake periodically, push sensor data via HTTP webhook, and go back to sleep.

### How it works

1. The daemon starts an HTTP server on `webhook_port` (default 8090)
2. When a Shelly H&T wakes, it POSTs a `NotifyStatus` payload to `http://<daemon-ip>:8090/webhook/shelly`
3. The daemon extracts humidity (and temperature) from the payload, caches it to disk
4. On each poll cycle, cached webhook humidity is merged with Homebridge humidity for fan decisions
5. If a sensor hasn't reported within `humidity_stale_minutes`, its reading is ignored (returns `None`)

### Registering the webhook on the sensor

**Via Shelly web UI:** Go to the device's web interface → Actions → add a webhook for `temperature.change` and `humidity.change` events pointing to `http://<daemon-ip>:8090/webhook/shelly`.

**Via RPC API:**

```bash
# Register webhook
curl -s "http://<shelly-ip>/rpc/Webhook.Create" \
  -d '{"cid":1,"enable":true,"event":"temperature.change","urls":["http://<daemon-ip>:8090/webhook/shelly"]}'

curl -s "http://<shelly-ip>/rpc/Webhook.Create" \
  -d '{"cid":2,"enable":true,"event":"humidity.change","urls":["http://<daemon-ip>:8090/webhook/shelly"]}'
```

### Finding the device ID

The device ID is the `src` field in webhook payloads (e.g. `shellyhtg3-8cbfeaa633fc`). You can also find it on the device's web UI or by checking the mDNS name.

### Lowering humidity report threshold

By default the H&T only reports when humidity changes by 5%. Lower it for faster response:

```bash
curl -s "http://<shelly-ip>/rpc/Humidity.SetConfig" \
  -d '{"id":0,"config":{"report_thr":1.0}}'
```

### Testing the webhook

```bash
curl -X POST http://localhost:8090/webhook/shelly \
  -H 'Content-Type: application/json' \
  -d '{"src":"shellyhtg3-test","method":"NotifyStatus","params":{"humidity:0":{"rh":65.0},"temperature:0":{"tC":23.5}}}'
```

## Deployment

The daemon runs as a user systemd service. `make deploy` copies config files to `~/.config/home-ventilation/` and installs the service unit.

```bash
make deploy   # install and start
make status   # check status
make logs     # follow logs
make restart  # restart after config change
```
