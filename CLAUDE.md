# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Where things are written down

- **`docs/competitor-analysis.md`** — what SmartSense actually does at Plymouth,
  observed from the live account. Their configuration gaps, their reporting
  features, and where we are genuinely ahead or behind.
- **`docs/roadmap.md`** — candidate changes, ranked, marked parity vs advantage.
- **`presentation/`** — the pitch deck and its generator.
- **`grafana/queries.md`** — every dashboard and alert query.

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

## ⚠️ Units: Celsius stored, Fahrenheit displayed

**Storage is Celsius, always.** The DS18B20 reports Celsius, the firmware sends
Celsius, the payload field is `temperature_c`, and `devices.temp_min_c` /
`temp_max_c` are Celsius. Do not convert stored values or add Fahrenheit columns —
mixing units in storage is how silent bugs get made, and every incoming reading would
need converting forever after.

**Grafana panels convert in SQL.** Two different conversions, and using the wrong one
is not obvious from looking at the output:

| Quantity | Conversion |
|---|---|
| An absolute temperature | `c * 9.0/5.0 + 32` |
| A **difference** (e.g. `excursion_c`) | `c * 9.0/5.0` — **no offset** |

Applying `+32` to a delta would report every perfectly healthy device as 32 degrees
out of range.

**Grafana's `fahrenheit` unit does not convert anything** — it only changes the label.
Setting it without converting in SQL displays Celsius numbers with °F beside them.
Always do the arithmetic in the query, then set the unit to match.

Alert *conditions* stay unit-agnostic (`excursion > 0` is true in either scale), so
thresholds never need touching when display units change.

## Dashboard: status first, history second

The fleet dashboard opens with **Needs Attention** — only units currently out of
range, offline, or never heard from. Empty means healthy, and it says so. Nothing
stays there after recovering.

That is deliberate contrast with SmartSense, whose front page lists incidents that
persist until manually acknowledged; theirs currently shows 15, most long since
resolved (`docs/competitor-analysis.md`). A monitoring screen should answer *what
is wrong now*, not *what has ever been wrong*.

Supporting panels answer questions their interface cannot:

- **Watch List** — units still inside their limits but with under a quarter of
  their safe range left, so "nearly in trouble" is visible before it becomes an
  alert. Uses `LEAST(max - reading, reading - min)`, which works despite each
  company having different limits.

  **The threshold is a proportion of the band, not a fixed number of degrees.**
  Plymouth's band is 7.2 °F wide and Nikky USA's is 9 °F; "within 3 °F" would
  flag almost the whole fleet as a warning and mean nothing. A quarter of the
  band currently surfaces 2 units of 20.

  Anything already breaching is excluded — that belongs in Needs Attention, and
  a unit should never appear twice saying different things.
- **Stayed In Range — last $window** — share of readings inside limits.
  **It reads 100% only when nothing went out of range at all.** Anything imperfect
  is capped at 99.99, because a rounded 100.0% next to a panel listing breached
  units is the one number a customer would quote back and the one that must never
  flatter. It is also a *historical* figure across the whole window, not a
  statement about right now — Needs Attention answers that.
  **Seven days, not thirty, on purpose**: the metric scores history against
  *current* limits, so a longer window reports a threshold edit as though it were
  an equipment failure. Changing Plymouth from produce to poultry limits dropped
  its 30-day figure to 70% overnight while nothing physical changed.
- **Temperature by Company** — one line per company. Per-device was 20
  overlapping series and unreadable; individual charts with limit bands live on
  the device detail page.

## Dashboard: Fleet Status never hides a device

The status table shows **every registered device, always**, with its most recent
reading whatever the age — plus a `last_seen` column rendered as "12 minutes ago" that
recounts on each refresh. It deliberately has no time bound.

An earlier version limited readings to the last 6 hours, which meant stopping the
simulator overnight left the command center showing an **empty table**. An old reading
is information; an empty table is not. A device silent for nine days should say so.

It uses `LEFT JOIN LATERAL ... LIMIT 1` per device rather than `DISTINCT ON` over the
join: ~6 ms versus ~650 ms on 350k rows, which matters on a panel refreshing every 10
seconds. Use the same shape for any future "latest reading per device" query.

Conditions: `OK`, `ABOVE THRESHOLD`, `BELOW THRESHOLD`, `OFFLINE`, `NEVER REPORTED`.

**Needs Attention and Fleet Status must use the same words.** They describe the same
device from two angles, so a unit reading `ABOVE THRESHOLD` on one and `HIGH` on the
other reads like two different findings. The column is `Condition` on both.

**A silent device has no deviation.** Needs Attention leaves it blank rather than
computing one from the last reading: that gap is however far out it was when last
heard from, not how far out it is now, and because the panel sorts on deviation a
days-old number outranked units breaching live.

## Site View is the map's drill-through

Clicking a map marker opens **Site View** (`/d/site-view`) for that location: two
compact tiles (units here, how many need attention), the **Watch List**, a table
sorted so anything wrong is at the top, and one temperature line per unit.

**`$site` is keyed on site alone, not company + site.** The map groups by site for
a reason — Plymouth and S&J are both in Auburn, 20 m apart, so they land on the
same pixel — and a company-qualified key would never match a marker. Auburn's Site
View therefore shows both tenants' units, which is correct for a location view.

The marker link passes `${company:queryparam}` so a fleet view filtered to one
company stays filtered after the drill-through, instead of quietly widening back
out to every tenant.

**Never plot raw temperature for units from different companies on one axis.**
Site View did, and it read as a fault: Nikky USA's frozen band (-9.4 to -0.4 F)
sits about 40 F below Aloha's chilled band (33.8 to 41 F), so both Nikky units
looked far too cold when only one actually was, and the chart disagreed with the
Needs Attention count directly above it. Position on a shared axis says nothing
about being in range when every tenant has different limits.

The chart is now **one small panel per unit**, built with Grafana panel `repeat`
over a hidden `$unit` variable chained to `$site` and `$company` — so adding or
retiring a device changes the page with no dashboard edit. Each panel plots that
unit's temperature plus its own `temp_min_c` / `temp_max_c` **as extra series**,
which is the only way to draw a different band in each repeated panel; panel
options cannot vary per repeat.

**Per unit, not per company, because limits can be overridden per device.**
`Auburn Freezer 2` has a 30 F floor where its four Aloha siblings have 33.8 F.
Any band drawn for a whole company is therefore wrong for somebody: draw the
loosest and a real breach hides inside it, draw the strictest and a healthy unit
looks broken. Either way the chart contradicts the count again, which is the bug
this was fixing.

**The fleet dashboard's Temperature History still has this flaw** — 21 units
across four bands on one axis. Left as raw temperature deliberately, since at
fleet level people want actual degrees, but it cannot be read for compliance.

**Site View's Watch List is the fleet dashboard's Watch List** — same title, same
columns, same thresholds, same colouring, with only `d.site` added to the WHERE
clause. It was briefly a bargauge called "Headroom", which was two names and two
shapes for one idea; a person who learned the panel upstairs should not have to
re-learn it after clicking through. If you change one, change both.

**Keep stat titles short enough to render in full.** A stat tile is meant to be
read at a glance; "Units At This Site" ellipsized to "Units At Thi..." and needed
a hover, which defeats the point. `Units` and `Needs Attention` fit.

**Grafana cannot scroll to a panel from a URL.** Worth knowing before promising
it: panels render with a `data-viz-panel-key` attribute, not an `id`, so a `#`
fragment has nothing to land on, and `viewPanel` — the only parameter that targets
a panel — *maximizes* it, which locks the reader into that one panel rather than
taking them to it. (If you ever do need the maximizing behaviour, the scenes form
is `viewPanel=panel-<id>`; a bare id resolves through a legacy branch. See
`public/app/features/dashboard-scene/utils/pathId.test.ts` in the container.)

The fix for "take me to the problem units" is layout, not linking: Site View's
**All Units** sits directly beneath the tiles and is ordered breaches → offline →
healthy, so the units the count refers to are already on screen.

**Stat panels need an explicit `options.text.valueSize`.** Grafana scales stat
text to fill its panel, so a count of 21 in a tall tile renders as a billboard
surrounded by dead space. Fixed type (~32-38px, title ~13px) reads as a header
strip. Prefer two short tiles over one tall one for the same reason.

The fleet-wide *Stayed In Range* stat tile was removed — it restated the
per-device table directly below it, and one fleet-average number is the least
actionable form of that data.

## Excursions are computed, not stored

There is no `incidents` table. The **Excursions** panel on Device Detail finds
excursions by reading `telemetry` directly: `LAG()` marks where a device crosses
between in-range and out-of-range, a running `SUM` over those crossings numbers
each run, and grouping by that run number collapses consecutive bad readings into
one incident with a start, a duration and a worst-case overshoot.

This was chosen over a watcher process writing rows. A watcher only knows about
excursions that happen after it is switched on; the query covers all history that
exists, and cannot drift out of sync with the readings it describes. If a device's
limits are later corrected, past excursions re-score to match — which is right,
because the old numbers were scored against a threshold now known to be wrong.

Duration adds one `expected_interval_s` to the span, since a single out-of-range
reading spans an interval rather than an instant — without it, every one-reading
excursion would report a duration of zero.

**Acknowledgements and corrective-action notes cannot work this way.** They are
data about a person's response, not about the readings, so they will need a real
table keyed on device plus start time whenever they get built.

## Two dashboard windows, deliberately different

The **Compliance window** dropdown (`$window`: 24 hours / 7 days / 30 days /
90 days) drives the Stayed In Range panels and the Excursions panel. It is
**not** the dashboard time picker, which defaults to 6 hours and drives the
charts. One span cannot serve both — 6 hours is right for watching a temperature
move and meaningless as a compliance figure. Do not "simplify" by merging them.

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

## Filling the dashboard on demand: `SCENARIO=showcase`

```bash
SCENARIO=showcase docker compose --profile sim up -d --force-recreate fleet-simulator
SCENARIO=demo     docker compose --profile sim up -d --force-recreate fleet-simulator   # back to normal
```

`showcase` exists to check panels, not to tell a story: it puts two units out of
range (one warm, one cold, at companies with different bands), one silent, and two
in the warning zone — all on the **first publish**, via `snap=True`, rather than
ramping in over half an hour.

The warning-zone units use `STATE_STRUGGLING`, the one behaviour nothing else
simulates: a unit holding *just inside* its limit, which never alarms and is
exactly what the Watch List exists to catch. It settles at
`STRUGGLE_MARGIN_FRACTION` (0.15) of the band from its limit — inside the panel's
0.25 threshold, far enough from the edge that jitter does not tip it into an
excursion. Its noise is deliberately smaller than a healthy unit's for that reason.

Everything recovers after 24 intervals (2 hours at 300s), so a forgotten simulator
does not re-notify Slack forever. **These fire real Slack alerts** — the same as any
other excursion.

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

## Device admin UI (`admin/`) — the only thing that writes to `devices`

Grafana is read-only; it cannot modify the database under any configuration. The
`device-admin` container serves the forms for adding devices, changing limits,
renaming and retiring. It is scoped to the `devices` table alone — there is no
path from it to `telemetry`.

```
http://localhost:8080          on the VM
http://10.80.149.11:8080       from anywhere on the network
```
Credentials live in `.env` (`ADMIN_USER` / `ADMIN_PASSWORD`). Both dashboards
carry a **Manage Devices** link in the top bar.

**⚠️ Temperatures are entered in Fahrenheit and stored in Celsius.** The form
converts at the boundary and shows the resulting °C live as you type. Do not
"simplify" this by storing what was typed — a manager who reads 34 °F everywhere
and types 34 would otherwise store 34 °C (93 °F), and the freezer would never
alarm.

**`device_id` is deliberately not editable.** It is the join key for every
historical reading and what the firmware publishes; changing it orphans the data.
`display_name` exists for renaming and is freely editable.

**Retiring is a soft delete** (`devices.is_active = false`). Readings are kept.

**⚠️ Gunicorn must run `gthread`, not the default sync worker.** A sync worker
handles one connection at a time and blocks in `recv()` until that connection
sends a request. Browsers open speculative *preconnect* sockets that may never
send anything, so each one occupied a whole worker until gunicorn's timeout killed
it — with `-w 2` a browser could tie up both, and the next click returned an error
page. Retrying worked because replacement workers had booted by then, which is why
it looked random.

The tell in `docker compose logs device-admin` is `WORKER TIMEOUT` followed by
`Error handling request (no URI read)` — *no URI* means the worker died waiting
for a request rather than while serving one, so it is never an application bug.
Application errors would show a traceback through `/app/app.py` instead.

Reproduce with two idle sockets and no data sent:

```python
import socket, urllib.request
idle = [socket.create_connection(("localhost", 8080)) for _ in range(2)]
urllib.request.urlopen("http://localhost:8080/health", timeout=12)  # hangs if sync
```

Fleet Command Center, Site View and both alert rules filter on `d.is_active`,
so a retired device stops cluttering operations and stops alerting. **Any new
operational query joining `devices` must include that filter**, or retired units
quietly reappear in that one panel.

**Device Detail deliberately does NOT filter it.** A retired unit's readings are
exactly what an audit asks for, so its full history stays reachable there and the
device dropdown marks it `(retired)`. Retiring hides a device from operations; it
never hides it from the record.

### Per-company access is built but open

`admin_users.scope_company` is `NULL` for every user, meaning full access to all
companies. Set it to a company name and that user sees and edits only that
company — every query already filters through `scope_clause()`. Restricting
someone is one `UPDATE`, not a code change.
