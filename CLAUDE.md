# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Status: prototype

This is a **prototype**, and the `telemetry` table holds a mix of two data sources —
do not assume a given row is one or the other:

- **Synthetic** — `mock-device/mock_publisher.py` (`MOCK-TRUCK-001`) and
  `mock-device/test_alert.py` (`TRUCK-TEST-999`). Test fixtures, not measurements.
- **Real** — the deployed LilyGO (`TRUCK-LILYGO-001`) now reads a physical DS18B20
  probe and a real battery voltage. These are genuine readings.

Filter by `device_id` before drawing any conclusion from the data or a Grafana panel.

## ⚠️ The committed firmware is NOT what's deployed

`firmware/fleet-telemetry-firmware/src/main.cpp` in this repo is an **obsolete mock
version** — it fabricates temperatures with `random()`, loops every 10 s, and connects
to MQTT without credentials. The firmware actually running on the hardware is
substantially different (see below) and lives outside this repo.

Do not treat the committed firmware as a description of device behavior, and do not
"fix" the backend to match it. The real source needs to be committed here; until then
this file is the reference for what the device does.

## ⚠️ Never delete the `pgdata` volume without asking

The volume holding all PostgreSQL data. **Always ask Julia before running anything
that would destroy it**, including:

- `docker compose down -v` (the `-v` is the dangerous part)
- `docker volume rm` / `docker volume prune`
- `docker system prune --volumes`

**The real volume names are prefixed by the compose project**, which the compose file
does not show:

| In `docker-compose.yml` | Actual Docker volume |
|---|---|
| `pgdata` | `fleet-telemetry-pipeline_pgdata` |
| `grafana-storage` | `fleet-telemetry-pipeline_grafana-storage` |

Mounting the unprefixed name does not fail — Docker silently creates a **new empty
volume** with that name, which looks like the real one and contains nothing. If a
backup or mount comes back suspiciously empty, this is why. Always confirm against
`docker volume ls` first.

`docker compose down` without `-v` is safe. When in doubt, prefer `docker compose stop`.
The same caution applies to `grafana-storage`, which holds the manually-configured
Grafana datasource and dashboards (there is no provisioning-as-code to rebuild them from).

## The stack (`docker-compose.yml`)

Three containers, all on the default compose network, all `restart: unless-stopped`:

Five services, all `restart: unless-stopped`:

| Service | Image / build | Host port | Notes |
|---|---|---|---|
| `mqtt-broker` | `eclipse-mosquitto:latest` | 1883 | bind-mounts `./mosquitto/` read-only |
| `telemetry-db` | `postgres:15` | 5432 | volume `pgdata`; has a `pg_isready` healthcheck |
| `ingestion` | built from `./backend` | — | waits for the DB healthcheck before starting |
| `grafana` | `grafana/grafana:latest` | 3000 | volume `grafana-storage` |
| `fleet-simulator` | built from `./mock-device` | — | **profile `sim`** — never starts by default |

`ingestion` and `fleet-simulator` reach the others by **Docker service name**
(`mqtt-broker`, `telemetry-db`), not `localhost` — inside a container `localhost` is
the container itself. Both scripts read config from environment variables with
localhost defaults, so the same file also runs directly on the VM for debugging.

The simulator sits behind a Compose profile deliberately: synthetic data should never
appear in a system being presented as real unless someone explicitly asked for it.

Note: the README claims a "custom virtual network" and that `pgdata` is "mapped to the
host machine" — neither is accurate. Compose uses the default project network, and
`pgdata` is a named volume managed by Docker, not a host bind mount. Trust the compose
file over the README.

## Application code

- **`backend/ingestion.py`** — subscribes to `fleet/telemetry`, validates payloads,
  inserts into Postgres. Creates `telemetry` and `rejected_readings` on startup if
  missing. Runs as the `ingestion` container.
- **`mock-device/fleet_simulator.py`** — the 20-sensor fleet. Two modes: `live`
  (publishes over MQTT, exercising the real pipeline) and `--backfill-hours N`
  (writes history straight to Postgres, because ingestion stamps `recorded_at` with
  the server clock and history cannot be replayed through MQTT). `--setup-db`
  registers devices. Runs as the `fleet-simulator` container under profile `sim`.
- **`mock-device/mock_publisher.py`** — *legacy*, superseded by the simulator. Single
  device, and it never sends MQTT credentials so the broker rejects it.
- **`mock-device/test_alert.py`** — *legacy*, one-shot 8.5 °C payload as
  `TRUCK-TEST-999`, a device not registered in `devices`, so it will not appear in
  any company-scoped panel.
- **`firmware/fleet-telemetry-firmware/`** — PlatformIO / ESP32 (`esp32dev`, Arduino
  framework, upload port `COM5`). **The committed copy is stale** — see the deployed
  firmware section below for actual behavior.

Python deps are `paho-mqtt` and `psycopg2-binary`; there is no requirements.txt or
virtualenv checked in.

## ⚠️ Grafana reads as `grafana_viewer` — new tables need an explicit GRANT

The Grafana datasource does not connect as `admin`. It uses a read-only role,
`grafana_viewer`, which is good practice and also a tripwire: **a table created by
`admin` is invisible to Grafana until it is granted.** The symptom is an alert rule or
panel failing with `permission denied for table X (SQLSTATE 42501)` while the identical
query works fine in `psql -U admin`.

A default privilege is now in place so tables `admin` creates from here on are granted
automatically:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA public
  GRANT SELECT ON TABLES TO grafana_viewer;
```

Tables created *before* that still need `GRANT SELECT ON <table> TO grafana_viewer;`.

## Multi-tenancy: the `devices` table

Company and site live in `devices`, keyed on `device_id` — **never in the MQTT payload**.
A device that reports its own tenant could claim to be another company's, which stops
being a bug and becomes a breach once customers share one database.

| Column | Purpose |
|---|---|
| `device_id` | PK, matches `telemetry.device_id` |
| `company`, `site` | Tenant and location; the alert grouping labels |
| `temp_min_c`, `temp_max_c` | That company's safe band — Plymouth 2–6, Nikky USA −23–−18 |
| `expected_interval_s` | Feeds the staleness alert |
| `is_simulated` | False only for `TRUCK-LILYGO-001` |

Adding a company is rows in this table plus a block in `fleet_simulator.py` — no code
or dashboard changes. Every panel and alert reads limits from here.

## Alerting (live, in Grafana)

Two rules in folder **Fleet Monitoring**, group `Slack Integration`, evaluating every 10s:

- **Fleet Temperature Excursion** — per device, both directions, compared against that
  device's own company limits. Fires on `excursion_c > 0`.
- **Fleet Sensor Offline** — per device, fires when silence exceeds
  `3 × expected_interval_s` (60s floor). Catches what a temperature rule cannot: a dead
  sensor produces no rows, so a threshold rule has nothing to evaluate.

Both use **simplified routing** (`notification_settings.receiver`) straight to the
existing `Slack Integration` contact point, grouped by `alertname, company, site`. They
do **not** go through the global notification policy tree.

> **Never provision alerting from files here.** Grafana's alerting provisioning
> *replaces* the notification config wholesale, which would destroy the working Slack
> contact point (its webhook is encrypted in `grafana.db` and cannot be read back).
> Edit rules via the API with the `X-Disable-Provenance: true` header — that keeps them
> editable in the UI instead of locking them as read-only.

A broken probe surfaces as **offline**, not as a temperature alert: its −127 °C readings
are rejected by ingestion, so it simply stops producing rows.

## Telemetry payload and schema

Published JSON:

```json
{"device_id": "...", "timestamp": "...", "temperature_c": 4.2,
 "lat": 47.6, "lon": -122.3, "battery_pct": 92}
```

Table `telemetry`: `id SERIAL PK`, `device_id`, `recorded_at`, `temperature_c`
(all NOT NULL), plus nullable `latitude`, `longitude`, `battery_pct`.

Two things to know before touching ingestion:

- **`recorded_at` is server-side.** `ingestion.py` writes `datetime.now(utc)` and
  ignores the publisher's `timestamp` field entirely. The firmware doesn't send one at all.
- **Only `device_id` and `temperature_c` are required.** Location and battery are
  optional by design (commit `db47aa0`) — the LilyGO can send partial payloads when
  it has no GPS fix.

## Temperature validation — deliberately loosened

`ingestion.py` currently accepts −40 °C to 101 °C. The real cold-chain threshold
(−23 °C to −18 °C) sits directly above it, commented out, per commit `28f2b8a`
("uncomment when done testing"). **Don't "fix" this by enabling the strict threshold.**
It would drop the mock publisher's 2–6 °C data *and* every real DS18B20 reading — those
bounds are for frozen goods, while this pipeline targets chilled produce at 2–6 °C. The
real bounds are still pending confirmation from the company.

The current −40/101 range does still catch a disconnected probe's −127 °C, so it isn't
merely permissive.

## Deployed firmware (`TRUCK-LILYGO-001`) — actual behavior

Documented from the source running on the board. **Not yet committed to this repo.**

**Sensors — both readings are real.**
- DS18B20 temperature probe on **GPIO 25** via OneWire/DallasTemperature. GPIO 25 was
  chosen specifically to avoid the cellular modem power key.
- Battery on **GPIO 35** (ADC). `voltage = (raw / 4095.0) * 3.3 * 2.0` for the divider,
  then linearly mapped 3.2 V → 0 % and 4.2 V → 100 %.

**Duty cycle: one reading per hour, then deep sleep.** `loop()` does not loop — it
publishes once, waits 1 s for the radio to flush, then `esp_deep_sleep_start()` with a
`TIME_TO_SLEEP` of 3600 s. On wake the chip restarts from `setup()`. Practical effect:
**expect one row per hour from this device**, not a stream. A gap of under an hour is
normal and is not an outage.

Deep sleep is also the failure path — 30 failed WiFi attempts (~15 s) or 3 failed MQTT
attempts (~15 s) both sleep for an hour rather than retrying. A device that can't reach
the broker goes quiet for an hour at a time.

**Power:** the cellular modem is force-disabled at boot (GPIO 4 driven LOW) to save
battery. The board is on WiFi, not cellular, despite being a T-SIM7000G.

**It sends no GPS.** `lat` and `lon` are commented out of the payload, so
`latitude`/`longitude` are **NULL for every real device row**. This is why those
columns are nullable (commit `db47aa0`) — it's expected, not a bug to fix.

**Network:** connects with `FRAME_SSID`/`FRAME_PASS`; `WIFI_SSID`, `HOMEWIFI_SSID`, and
`HOTSPOT_SSID` are alternates commented out in `config.h`. It pings the broker host at
`10.80.149.11` before connecting as a reachability check — this is a different network
from the `172.29.96.1` WSL address in the committed `config.h`. Also sets
`client.setBufferSize(512)`.

**A disconnected DS18B20 reads −127 °C**, which the backend's −40/101 bounds reject with
"Abnormal temperature detected." That's working as intended — sensor failure shows up as
dropped messages and a gap in the data, not as a bogus row. Keep that in mind when
changing the bounds.

## Running the stack

Everything is containerized. **There are no Python processes to start by hand.**

```bash
docker compose up -d                    # broker, database, ingestion, Grafana
docker compose --profile sim up -d      # ...plus the 20 simulated sensors
```

Everything is `restart: unless-stopped`, so it comes back after a VM reboot on its own.

```bash
docker compose ps                       # what is running
docker compose logs -f ingestion        # follow the pipeline
docker compose logs -f fleet-simulator  # expect "published 20/20"
docker compose stop fleet-simulator     # silence synthetic data, keep the rest
docker compose restart ingestion        # after editing ingestion.py, plus --build
```

Rebuild after changing Python: `docker compose up -d --build`.

The physical board publishes on its own once powered and in range of the broker —
nothing to start for it.

Dashboard: http://localhost:3000/d/fleet-command-center/fleet-command-center

**Shutting down:** `docker compose stop` is fine. **Never `docker compose down -v`.**
Expect one offline alert per simulated device roughly 15 minutes after stopping the
simulator — that is the staleness rule working correctly, not a fault.

## Timing: two speeds on purpose

| | Interval | Staleness alert after |
|---|---|---|
| Simulated fleet | 300s (5 min) | ~15 min |
| `TRUCK-LILYGO-001` | 5s | 60s (the floor) |

The fleet is slow because that is what real reefer telemetry does — cellular data and
battery both cost money — and because ~5,800 rows/day is manageable where 15-second
reporting was ~115,000. The board is fast because it is the only thing an audience
watches change, and it has to react while the probe is still in the water.

Both are single constants at the top of `fleet_simulator.py`, overridable via
`PUBLISH_INTERVAL_S` / `REAL_DEVICE_INTERVAL_S`.

**Consequence for queries:** no fixed time window can serve both a 5-second and a
300-second reporter. Every alert and panel uses `DISTINCT ON (device_id) ... ORDER BY
recorded_at DESC` — each device's most recent reading — instead of a fixed window. A
query like `WHERE recorded_at > now() - interval '90 seconds'` looks correct and
silently excludes the entire simulated fleet.

## Simulated failures recover on their own

Faults are not permanent. Each scripted failure has a duration, after which the device
returns to normal — a door gets closed, a truck leaves the dead zone. Without this, a
simulator left running re-notifies Slack every 5 minutes forever. It also gives the
demo a better story: the alert fires *and* clears.

Schedules are expressed as multiples of `PUBLISH_INTERVAL_S`, so the same script plays
out over ~45 minutes at 300s or under three minutes at a 15s test interval.

## Auth: `mock_publisher.py` is the one client missing credentials

`mosquitto.conf` sets `allow_anonymous false` with a `password_file`.

- `ingestion.py`, `test_alert.py` — send credentials via `username_pw_set` ✅
- Deployed firmware — sends them via `client.connect(DEVICE_ID, MQTT_USER, MQTT_PASS)` ✅
- `mock-device/mock_publisher.py` — **sends none**, so the broker should reject it ❌

If mock data stops flowing, check this first: the publisher fails at the broker without
an obvious error locally. The fix is a `username_pw_set` call matching `ingestion.py`.

The firmware's `reconnect()` decodes PubSubClient state codes to plain English on
serial — `4` is bad credentials, `5` is unauthorized. Useful when debugging the board.

## Source control

The whole project is one git repo rooted at the project directory — not just
`backend/`. Remote is `origin` → `github.com/jjlavigne/lilygo_temp_sensor_backend`.
Tracked: `docker-compose.yml`, `mosquitto.conf`, `pwfile`, `.vscode/settings.json`,
both Python services, and the firmware source.

`firmware/.../.pio/` is correctly ignored via `firmware/fleet-telemetry-firmware/.gitignore`,
so build artifacts (`.o`, `.elf`, `.bin`) are **not** in the repo. Still skip that
directory when searching — it's large build output, not source.

## ⚠️ Secrets are in plaintext AND pushed to the remote

These are tracked files, so they have been pushed to GitHub:

- `firmware/fleet-telemetry-firmware/src/config.h` — WiFi SSID + password
- `pwfile` — Mosquitto password hash
- `backend/ingestion.py`, `mock-device/test_alert.py` — MQTT user/password
- `docker-compose.yml` — Postgres password

There is no root `.gitignore`. If the GitHub repo is public these credentials are
public; they need rotating and moving to env vars / a gitignored `.env` before
anything else ships. **Do not add further secrets to tracked files** — flag it instead.
