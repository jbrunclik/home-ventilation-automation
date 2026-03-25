# Home Ventilation Automation

Automated control of bathroom exhaust fans (Ruck EC motors) based on CO2 levels, humidity, and manual wall switches. Monitors 3 bedrooms and 3 bathrooms, controlling 2 Shelly 2PM Gen4 devices.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Tuya CO2 sensors (local API — device ID + local key from [iot.tuya.com](https://iot.tuya.com))
- Shelly 2PM Gen4 devices controlling the Ruck fans
- Shelly H&T Gen3 sensors for humidity (optional)

## Quick Start

```bash
# Install dependencies
make dev

# Copy and edit config
cp config.example.toml config.toml
# Edit config.toml with your device IPs, Tuya keys, etc.

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
| `webhook_host` | Daemon IP for Shelly webhook URLs (required) | — |
| `webhook_port` | HTTP port for Shelly webhooks (humidity + switch inputs) | 8090 |
| `sensor_cache_path` | Path for cached webhook sensor data | `/dev/shm/home-ventilation-sensor-cache.json` |
| `humidity_stale_minutes` | Ignore webhook readings older than this | 120 |
| `thresholds.co2_low` | CO2 ppm threshold for LOW speed | 800 |
| `thresholds.co2_high` | CO2 ppm threshold for HIGH speed | 1200 |
| `thresholds.humidity_low` | Humidity % threshold for LOW speed | 60.0 |
| `thresholds.humidity_high` | Humidity % threshold for HIGH speed | 70.0 |
| `thresholds.co2_hysteresis` | CO2 ppm dead band to prevent toggling near threshold | 50 |
| `thresholds.humidity_hysteresis` | Humidity % dead band to prevent toggling near threshold | 3.0 |

Each fan section (`[fans.<name>]`) specifies:
- `shelly_host` — IP of the Shelly 2PM Gen4
- `humidity_sensor_ips` — Shelly H&T Gen3 IPs for webhook humidity (identified by source IP)
- `switch_inputs` — Shelly input IDs for wall switches

CO2 sensors are configured as named sub-tables under each fan:
```toml
[fans.master_bathroom.co2_sensors.bedroom]
device_id = "abc123def456"
ip = "10.0.0.60"
local_key = "your_local_key"
```

Multiple sensors per fan are supported — the daemon uses the max reading across all sensors.

### Tuya local keys

To get device IDs and local keys for your Tuya CO2 sensors:

1. Create an account at [iot.tuya.com](https://iot.tuya.com)
2. Create a Cloud Project → link your Smart Life account
3. Find each device → copy Device ID and Local Key
4. Or run `uv run python -m tinytuya wizard` with your API credentials

Local keys persist even after unlinking from the IoT platform (they only change if you re-pair the device in Smart Life).

## Fan Speed Mapping

The Shelly 2PM Gen4 controls fan speed via two relays connected to the Ruck EC motor:

| Speed | Relay 0 | Relay 1 |
|---|---|---|
| OFF | off | off |
| LOW | on | off |
| HIGH | off | on |

## Webhook Setup

The daemon runs an HTTP server on `webhook_port` (default 8090) at `/webhook/shelly`. Both Shelly H&T humidity sensors and Shelly 2PM switch inputs push to the same endpoint, distinguished by query parameters.

**All webhook configuration is automated on daemon startup** — the daemon reconciles webhooks, input types, and cover config on each Shelly device based on `config.toml`. Manual setup is only needed if the automation can't reach a device (e.g. battery-powered H&T sensors that are asleep).

### Shelly H&T Gen3 (humidity)

Battery-powered sensors that can't be polled — they wake periodically, push sensor data via webhook, and go back to sleep.

1. When a Shelly H&T wakes, it hits `http://<daemon-ip>:<port>/webhook/shelly?hum=<value>`
2. The daemon caches the humidity to disk
3. On each cycle, cached webhook humidity is used for fan decisions
4. If a sensor hasn't reported within `humidity_stale_minutes`, its reading is ignored (returns `None`)

On startup, the daemon configures each H&T listed in `humidity_sensor_ips`: sets the `humidity.change` webhook URL and lowers the report threshold to 1.0%. If the sensor is asleep, it logs a warning and skips — put the sensor in config mode and restart the daemon to configure it.

#### Manual setup (if needed)

**Webhook** — via Shelly web UI → Actions → add a `humidity.change` action with URL:
```
http://<daemon-ip>:<port>/webhook/shelly?hum=${ev.rh}
```

**Report threshold** — lower from default 5% for faster response:
```bash
curl -s "http://<shelly-ip>/rpc/Humidity.SetConfig" \
  -d '{"id":0,"config":{"report_thr":1.0}}'
```

### Shelly 2PM Gen4 (switch inputs)

Wall switch presses are pushed via webhook instead of polling. On startup, the daemon configures each 2PM: sets cover mode to detached + locked, ensures inputs are type "switch", and reconciles webhooks (creates missing, fixes wrong URLs, deletes stale) based on `switch_inputs` in `config.toml`.

#### Manual setup (if needed)

In the Shelly web UI → Actions, create these actions:

| Event | URL |
|---|---|
| Input 0 `toggle_on` | `http://<daemon-ip>:<port>/webhook/shelly?input_id=0&state=on` |
| Input 0 `toggle_off` | `http://<daemon-ip>:<port>/webhook/shelly?input_id=0&state=off` |
| Input 1 `toggle_on` | `http://<daemon-ip>:<port>/webhook/shelly?input_id=1&state=on` |
| Input 1 `toggle_off` | `http://<daemon-ip>:<port>/webhook/shelly?input_id=1&state=off` |

Only configure the inputs listed in `switch_inputs` for that fan.

#### Testing

```bash
curl "http://localhost:8090/webhook/shelly?input_id=0&state=on"
```

## Standalone Shelly Script (no daemon needed)

If you can't run the Python daemon, [`shelly-scripts/cover-switch-override.js`](shelly-scripts/cover-switch-override.js) runs directly on the Shelly 2PM Gen2+ device — no external server required. Mirrors the Python daemon's architecture: cached state → pure decision logic (`desiredSpeed()`) → idempotent actuation (`applySpeed()`), making it easy to add new inputs like CO2 or humidity.

**Features (priority order):**
1. **Switch override** — toggle → fan runs HIGH for `OVERRIDE_MINUTES` (default 10), then seamlessly transitions to schedule or off
2. **Time-based schedule** — run LOW for first `SCHEDULE_RUN_MINUTES` of each hour during a configurable window (hours + weekdays)
3. Auto-refreshes cover command every 60s to work around 300s auto-stop
4. Detaches physical inputs on startup (`in_mode: "detached"` + `in_locked: true`) so only the script controls the cover

**Setup:**
1. Set wall switch inputs to type **"switch"** (not "button") — required for `"toggle"` events:
   ```bash
   curl "http://<shelly-ip>/rpc/Input.SetConfig" -d '{"id":0,"config":{"type":"switch"}}'
   ```
2. Shelly web UI → Scripts → create new script, paste the contents, enable "Run on startup"
3. Configure the variables at the top:

| Variable | Default | Description |
|---|---|---|
| `OVERRIDE_MINUTES` | 10 | Duration of switch override (HIGH) |
| `INPUT_ID` | 0 | Which input triggers the override (0 or 1) |
| `SCHEDULE_START_HOUR` | 8 | Schedule window start (inclusive) |
| `SCHEDULE_END_HOUR` | 18 | Schedule window end (exclusive) |
| `SCHEDULE_RUN_MINUTES` | 10 | Run first N minutes of each hour |
| `SCHEDULE_DAYS` | `[1,2,3,4,5]` | Active days (0=Sun, 1=Mon, ..., 6=Sat) |

Local time and DST are handled automatically via the device's configured timezone (Settings → Location).

**Limitations:** no sensor-based control (CO2/humidity) yet — architecture is ready, just needs pollers and thresholds in `desiredSpeed()`.

## Deployment

The daemon runs as a user systemd service. `make deploy` installs the systemd unit (templated with the repo path) — config stays in the repo directory.

```bash
make deploy   # install and start
make status   # check status
make logs     # follow logs
make restart  # restart after config change
```
