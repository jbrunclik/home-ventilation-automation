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
| `reconciliation_interval_seconds` | Re-issue cover command to prevent 300s auto-stop | 60 |
| `manual_override_minutes` | Duration of manual override | 15 |
| `webhook_port` | HTTP port for Shelly webhooks (humidity + switch inputs) | 8090 |
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
- `humidity_sensor_ips` — Shelly H&T Gen3 IPs for webhook humidity (identified by source IP)
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

## Webhook Setup

The daemon runs an HTTP server on `webhook_port` (default 8090) at `/webhook/shelly`. Both Shelly H&T humidity sensors and Shelly 2PM switch inputs push to the same endpoint, distinguished by query parameters.

### Shelly H&T Gen3 (humidity)

Battery-powered sensors that can't be polled — they wake periodically, push sensor data via webhook, and go back to sleep.

1. When a Shelly H&T wakes, it hits `http://<daemon-ip>:8090/webhook/shelly?hum=<value>`
2. The daemon caches the humidity to disk
3. On each cycle, cached webhook humidity is merged with Homebridge humidity for fan decisions
4. If a sensor hasn't reported within `humidity_stale_minutes`, its reading is ignored (returns `None`)

#### Registering the webhook on the sensor

**Via Shelly web UI:** Go to the device's web interface → Actions → add a `humidity.change` action with URL:
```
http://<daemon-ip>:8090/webhook/shelly?hum=$humidity
```
Use the `$humidity` template variable to pass the reading as a query parameter. The sensor is identified by its source IP, so no device ID is needed in the URL.

**Via RPC API:**

```bash
curl -s "http://<shelly-ip>/rpc/Webhook.Create" \
  -d '{"cid":1,"enable":true,"event":"humidity.change","urls":["http://<daemon-ip>:8090/webhook/shelly?hum=$humidity"]}'
```

#### Lowering humidity report threshold

By default the H&T only reports when humidity changes by 5%. Lower it for faster response:

```bash
curl -s "http://<shelly-ip>/rpc/Humidity.SetConfig" \
  -d '{"id":0,"config":{"report_thr":1.0}}'
```

#### Testing

```bash
curl "http://localhost:8090/webhook/shelly?hum=65.0"
```

### Shelly 2PM Gen4 (switch inputs)

Wall switch presses are pushed via webhook instead of polling, reducing HTTP traffic from ~4 req/s per device to near-zero. The Shelly 2PM doesn't support `$variable` substitution in action URLs, so you need 4 separate actions (one per input × toggle event) with hardcoded values.

#### Registering the webhooks

In the Shelly web UI → Actions, create these actions:

| Event | URL |
|---|---|
| Input 0 `toggle_on` | `http://<daemon-ip>:8090/webhook/shelly?input_id=0&state=on` |
| Input 0 `toggle_off` | `http://<daemon-ip>:8090/webhook/shelly?input_id=0&state=off` |
| Input 1 `toggle_on` | `http://<daemon-ip>:8090/webhook/shelly?input_id=1&state=on` |
| Input 1 `toggle_off` | `http://<daemon-ip>:8090/webhook/shelly?input_id=1&state=off` |

Only configure the inputs listed in `switch_inputs` for that fan.

#### Testing

```bash
curl "http://localhost:8090/webhook/shelly?input_id=0&state=on"
```

## Standalone Shelly Script (no daemon needed)

If you can't run the Python daemon, [`shelly-scripts/cover-switch-override.js`](shelly-scripts/cover-switch-override.js) runs directly on the Shelly 2PM Gen2+ device — no external server required.

**Features (priority order):**
1. **Switch override** — toggle → fan runs HIGH for `OVERRIDE_MINUTES` (default 10), then falls back to schedule or off
2. **Time-based schedule** — run LOW for first `SCHEDULE_RUN_MINUTES` of each hour during a configurable window (hours + weekdays)
3. Auto-refreshes cover command every 60s to work around 300s auto-stop
4. Configures cover timeouts to 300s and locks physical inputs (`in_locked`) on startup

**Setup:** Shelly web UI → Scripts → create new script, paste the contents, enable "Run on startup". Configure the variables at the top:

| Variable | Default | Description |
|---|---|---|
| `OVERRIDE_MINUTES` | 10 | Duration of switch override (HIGH) |
| `INPUT_ID` | 0 | Which input to listen to (0 or 1) |
| `SCHEDULE_START_HOUR` | 8 | Schedule window start (inclusive) |
| `SCHEDULE_END_HOUR` | 18 | Schedule window end (exclusive) |
| `SCHEDULE_RUN_MINUTES` | 10 | Run first N minutes of each hour |
| `SCHEDULE_DAYS` | `[1,2,3,4,5]` | Active days (0=Sun, 1=Mon, ..., 6=Sat) |

Local time and DST are handled automatically via the device's configured timezone (Settings → Location).

**Limitations:** no sensor-based control (CO2/humidity), no multi-fan coordination.

## Deployment

The daemon runs as a user systemd service. `make deploy` installs the systemd unit (templated with the repo path) — config and `.env` stay in the repo directory.

```bash
make deploy   # install and start
make status   # check status
make logs     # follow logs
make restart  # restart after config change
```
