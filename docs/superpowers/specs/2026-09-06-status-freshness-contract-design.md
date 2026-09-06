# Status file freshness contract

**Date:** 2026-09-06
**Status:** approved
**Consumer:** `meteo` dashboard — see `meteo/docs/superpowers/specs/2026-09-06-stale-data-indication-design.md`

## Problem

The status file at `/dev/shm/home-ventilation-status.json` cannot express "this
data is old". The dashboard therefore shows dead sensors as healthy readings.

Four concrete defects:

**P1 — `updated_at` measures daemon liveness, not data freshness.**
`write_status` runs on every iteration of the main loop (`daemon.py:204`), but
sensors are only polled every `poll_interval_seconds` (30 s), and the loop also
wakes on every Shelly webhook. `updated_at` is therefore refreshed continuously
whether or not any sensor was read. The consumer's staleness check can never
fire while the daemon is alive.

**P2 — a dead sensor is silently dropped.** `status_writer.py:48-50`:

```python
reading = readings[i] if i < len(readings) else None
if reading is None:
    continue
```

The configured roster is known (`fan_cfg.co2_sensors`) and the failure is known.
The row simply vanishes from the file, and the dashboard cannot distinguish a
dead sensor from one that was never configured.

**P3 — a partially dead sensor is silently dropped.** `status_writer.py:60`
(`if len(entry) > 1`) drops a sensor that connects but returns nothing. A sensor
returning CO2 but no PM2.5 loses just that field, equally silently.

**P5 — stale humidity vanishes.** `SensorCache.get_humidity` returns `None` past
`humidity_stale_minutes` (120), so `status_writer` omits the key entirely. A
Shelly H&T dead for three hours is indistinguishable from a fan with no humidity
sensor. `SensorCache` already stores a per-device timestamp and discards it at
this boundary.

### Observed failure that shaped the design

Sampling the live file three times, 45 s apart, on 2026-09-06:

```
05:45:13  Bedroom 900  Living Room 814  Bibi 511  Viki 1122
05:45:58  Bedroom 901  Living Room 818  Bibi 511  Viki 1136
05:46:43  Bedroom 891  Living Room 818  Bibi 511  Viki 1133
```

`Bibi` is frozen at exactly 511 ppm while every other sensor moves, and reports
`temperature: 0.0, humidity: 0.0, pm25: 0.0`.

Two conclusions:

1. **The device is responding.** A failed poll returns `None` from
   `poll_tuya_sensor` and the row would drop. It answers on the network while its
   sensing element is dead. A "when did we last read this device" timestamp would
   be perfectly fresh. Only "when did this value last change" catches it.
2. **Zeros are a sentinel, not a measurement.** `temperature == 0` and
   `humidity == 0` simultaneously is physically implausible indoors. Those zeros
   currently reach the dashboard, which renders **PM2.5 = 0.0 as green "good"**.

## Contract

`/dev/shm/home-ventilation-status.json`, version 2:

```json
{
  "version": 2,
  "written_at": "2026-09-06T05:46:43.666095+00:00",
  "sensors": [
    {
      "label": "Bedroom",
      "read_at": "2026-09-06T05:46:40.101000+00:00",
      "changed_at": "2026-09-06T05:46:40.101000+00:00",
      "stale": false,
      "ppm": 891,
      "temperature": 26.0,
      "humidity": 46.0,
      "pm25": 2.0
    },
    {
      "label": "Bibi",
      "read_at": "2026-09-06T05:46:40.940000+00:00",
      "changed_at": "2026-09-06T02:11:03.220000+00:00",
      "stale": true,
      "ppm": 511
    }
  ],
  "fans": [
    {
      "label": "Shower",
      "speed": "low",
      "humidity": 51.2,
      "humidity_updated_at": "2026-09-06T05:31:02.000000+00:00",
      "humidity_stale": false
    }
  ]
}
```

Field semantics:

| Field | Meaning |
|---|---|
| `written_at` | When this file was written. Daemon liveness **only**. Never freshness. |
| `read_at` | Last *successful* poll of this device. Absent = never read since daemon start. |
| `changed_at` | Last time any value on this device actually changed. |
| `stale` | The producer's verdict. The consumer trusts it rather than re-deriving. |
| `humidity_updated_at` | From `SensorCache`'s existing per-device timestamp. |
| `humidity_stale` | Past `humidity_stale_minutes`; the value is still emitted. |

Rules:

- **Every configured sensor appears, always**, even when it has never been read.
  The roster comes from `fan_cfg.co2_sensors`. A sensor with no data carries
  `label`, `stale: true`, and no value keys.
- **Absent value key means "no reading"**, and the consumer dashes it. A value is
  never emitted as `0` to mean "missing".
- `version: 2` lets the consumer reject a file written by an older daemon rather
  than misread it.

### Staleness verdict

`stale` is true when any of:

1. `read_at` is absent, or older than `SENSOR_STALE_MULTIPLIER (4) × poll_interval_seconds`
   → 120 s at the default 30 s cadence. Catches unreachable devices.
2. `changed_at` is older than `FROZEN_STALE_SECONDS` (1800, i.e. 30 min).
   Catches the Bibi case — responsive device, dead sensing element.
3. The reading carries no values at all.

The two multipliers are separate on purpose. A device that has not been *read* in
two minutes is broken; a value that has not *moved* in two minutes is completely
normal. 30 minutes is chosen against observed behaviour: healthy CO2 readings
above move every single 45 s sample, so any real sensor resets `changed_at`
continuously. PM2.5 quantises to whole µg/m³ and can legitimately hold, which is
why `changed_at` tracks *any* field changing, not each field independently.

### Implausible value rule

In `_parse_dps`, when `temperature == 0 and humidity == 0`, treat temperature,
humidity **and** pm25 as absent. CO2 is kept — on the observed device it still
returns a (frozen) plausible number, and rule 2 catches that independently.

Scoped narrowly to the simultaneous-zero case so a genuine 0 °C reading with a
plausible humidity is never discarded. Logged once per device per transition, not
every poll.

## Components

**`home_ventilation/reading_cache.py`** — new. `ReadingCache`, mirroring the
existing `SensorCache` in shape and persistence style.

```python
class ReadingCache:
    """Track per-device read and change times for Tuya sensor readings."""

    def observe(self, device_id: str, reading: TuyaSensorReading | None,
                now: datetime) -> None
    def read_at(self, device_id: str) -> datetime | None
    def changed_at(self, device_id: str) -> datetime | None
```

Persisted to `/dev/shm/home-ventilation-reading-cache.json` so a daemon restart
does not reset every device to "just changed" and mask a sensor that died while
the daemon was down. Same atomic-write and load-failure handling as
`SensorCache`.

Equality for "changed" compares the whole `TuyaSensorReading` tuple. `None`
readings do not update either timestamp — they mean "no successful read".

**`home_ventilation/tuya.py`** — `_parse_dps` gains the implausible-zero rule.

**`home_ventilation/daemon.py`** — feeds `ReadingCache` after each poll, passes
it to `write_status`. Instantiated alongside `SensorCache`.

**`home_ventilation/status_writer.py`** — emits the v2 shape, iterating the
configured roster rather than the readings list.

**`home_ventilation/config.py`** — `reading_cache_path`, defaulting to
`/dev/shm/home-ventilation-reading-cache.json`; `frozen_stale_seconds`,
defaulting to 1800.

## Testing

`tests/test_reading_cache.py` — new:

- read/change timestamps advance correctly
- an unchanged reading advances `read_at` but not `changed_at`
- a `None` reading advances neither
- round-trips through disk; a corrupt file starts fresh

`tests/test_status_writer.py` — extended:

- a configured sensor that has never been read appears with `stale: true`
- a frozen reading (unchanged past `frozen_stale_seconds`) is `stale: true`
- a healthy reading is `stale: false` and carries all values
- humidity past `humidity_stale_minutes` is emitted with `humidity_stale: true`
- no value key is ever `0` as a stand-in for missing

`tests/test_tuya.py` — extended:

- `temperature == 0 and humidity == 0` drops temp/humidity/pm25, keeps co2
- a genuine `0.0` temperature with plausible humidity is preserved

Time is controlled by passing `now` explicitly, matching the existing tests.

## Out of scope

- **P7 — fan speed is intent, not reality.** `status_writer.py:33` reports the
  decided speed; a failed `set_fan_speed` shows "high" on a stopped fan.
  Deferred by explicit decision; needs a confirmed-state concept in the daemon.
- **P6 — `/dev/shm` is wiped on reboot**, so the consumer sees a missing file
  rather than a stale one. Deferred by explicit decision.

## Compatibility

The consumer ships after this. Between the two deploys the dashboard reads a v2
file with v1 logic: `sensors` and `fans` keep their existing keys and types, so
it degrades to today's behaviour rather than breaking. Newly-emitted dead sensors
appear as rows with no values, which v1 templates already guard with
`{% if sensor.ppm is defined %}`.
