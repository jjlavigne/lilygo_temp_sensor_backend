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

`pgdata` is the named Docker volume holding all PostgreSQL data. **Always ask Julia
before running anything that would destroy it**, including:

- `docker compose down -v` (the `-v` is the dangerous part)
- `docker volume rm pgdata` / `docker volume prune`
- `docker system prune --volumes`

`docker compose down` without `-v` is safe. When in doubt, prefer `docker compose stop`.
The same caution applies to `grafana-storage`, which holds the manually-configured
Grafana datasource and dashboards (there is no provisioning-as-code to rebuild them from).

## The stack (`docker-compose.yml`)

Three containers, all on the default compose network, all `restart: unless-stopped`:

| Service | Container | Image | Host port | Volumes |
|---|---|---|---|---|
| `mqtt-broker` | `mqtt-broker` | `eclipse-mosquitto:latest` | 1883 | bind-mounts `./mosquitto.conf`, `./pwfile` |
| `telemetry-db` | `telemetry-db` | `postgres:15` | 5432 | named volume `pgdata` |
| `grafana` | `grafana` | `grafana/grafana:latest` | 3000 | named volume `grafana-storage` |

`grafana` declares `depends_on: telemetry-db`. Postgres is configured via environment
in the compose file: user `admin`, password `password123`, database `fleet_data`.

Note: the README claims a "custom virtual network" and that `pgdata` is "mapped to the
host machine" — neither is accurate. Compose uses the default project network, and
`pgdata` is a named volume managed by Docker, not a host bind mount. Trust the compose
file over the README.

## Application code (runs on the host, not in Docker)

- **`backend/ingestion.py`** — subscribes to `fleet/telemetry` on `localhost:1883`,
  validates payloads, inserts into Postgres. Creates the `telemetry` table on startup
  if missing. Run with `python ingestion.py` from `backend/`.
- **`mock-device/mock_publisher.py`** — publishes a synthetic reading every 5 seconds
  as `MOCK-TRUCK-001`. Seattle-area coordinates, 2–6 °C.
- **`mock-device/test_alert.py`** — one-shot publisher of a single out-of-range
  payload (8.5 °C, `TRUCK-TEST-999`) for testing alerting.
- **`firmware/fleet-telemetry-firmware/`** — PlatformIO / ESP32 (`esp32dev`, Arduino
  framework, upload port `COM5`). **The committed copy is stale** — see the deployed
  firmware section below for actual behavior.

Python deps are `paho-mqtt` and `psycopg2-binary`; there is no requirements.txt or
virtualenv checked in.

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

## Boot sequence

1. `docker compose start` (or start the stack in Docker Desktop)
2. `cd backend && python ingestion.py`
3. In another terminal: `cd mock-device && python mock_publisher.py`

Grafana at http://localhost:3000, pointed at `telemetry-db:5432` / `fleet_data`.

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
