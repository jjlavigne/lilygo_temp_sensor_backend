# Grafana queries and alert settings

Every query below was run against the live `fleet_data` database and returns real rows.
Paste them into Grafana panels and alert rules as-is.

**Datasource:** PostgreSQL, host `telemetry-db:5432` (the Docker service name, not
`localhost` -- Grafana reaches Postgres over the internal Docker network), database
`fleet_data`, user `grafana_viewer` (read-only; new tables need an explicit GRANT).

> **Units.** The database stores **Celsius**. Panels display **Fahrenheit** by
> converting in SQL. Absolute temperatures use `c * 9.0/5.0 + 32`; a *difference*
> such as `excursion_c` uses `c * 9.0/5.0` with **no offset**. Grafana's `fahrenheit`
> unit only relabels — it never converts — so the arithmetic must be in the query.
> The queries below are shown in Celsius for readability; the live panels wrap the
> temperature expressions in the conversion above.

---

## How the alerts are tuned

| Setting | Value | Why |
|---|---|---|
| Evaluation interval | 10s | Grafana's practical floor; how often rules are checked |
| Pending period | 0s | Fire on the first breach, no waiting |
| Group by | `company`, `site` | This is the "group failures by location" requirement |
| Group wait | 5s | Batches several devices at one site into a single Slack message |
| Group interval | 1m | Gap before an updated message for a group that already fired |
| Repeat interval | 5m | Re-notify only while STILL breaching |
| Send resolved | on | One "back in range" message, then silence |

**On repeats:** Grafana only repeats while the condition is still true. The moment a
temperature returns to its safe band the alert moves to Resolved, sends one recovery
notification, and stops. It cannot nag about something that has already been fixed.

---

## Alert A — Temperature excursion

Fires when a device breaches its own company's limits, in either direction. One rule
covers all four companies because the limits are read per-device from `devices`.

```sql
SELECT
  d.company,
  d.site,
  t.device_id,
  GREATEST(
    MAX(t.temperature_c) - d.temp_max_c,   -- how far above the ceiling
    d.temp_min_c - MIN(t.temperature_c)    -- how far below the floor
  ) AS excursion_c
FROM telemetry t
JOIN devices d USING (device_id)
WHERE t.recorded_at > now() - interval '90 seconds'
GROUP BY d.company, d.site, t.device_id, d.temp_min_c, d.temp_max_c;
```

**Condition:** `excursion_c > 0`

`excursion_c` is how many degrees outside the safe band the device went. Negative means
margin to spare. Because it is a single number rather than a raw temperature, the same
threshold of zero works for Plymouth's 2--6 C produce and Nikky USA's -23--18 C frozen
goods without any per-company rules.

Checking both directions matters: ice water puts a produce sensor *below* its floor, and
freeze damage is a real spoilage mode. It also makes the ice-water half of the demo
produce a genuine alert rather than a silent green panel.

---

## Alert B — Sensor offline

Fires when a device has gone quiet. This catches what a temperature rule structurally
cannot: a dead battery, a failed probe, or a truck out of coverage produces **no rows at
all**, so a threshold on temperature has nothing to evaluate and never fires.

```sql
SELECT
  d.company,
  d.site,
  d.device_id,
  EXTRACT(EPOCH FROM (now() - COALESCE(MAX(t.recorded_at), now() - interval '1 day')))
    / GREATEST(d.expected_interval_s * 3, 60) AS silence_ratio
FROM devices d
LEFT JOIN telemetry t
  ON t.device_id = d.device_id
 AND t.recorded_at > now() - interval '6 hours'
GROUP BY d.company, d.site, d.device_id, d.expected_interval_s;
```

**Condition:** `silence_ratio > 1`

The ratio is "how long it has been silent" divided by "how long it is allowed to be
silent," so one threshold serves every device no matter how often it reports. The
allowance is three times the device's expected interval, floored at 60 seconds:

- Simulated sensors (15s expected) -> alert after 60s of silence
- The LilyGO in demo mode (5s expected) -> alert after 60s of silence
- The LilyGO back on hourly deep sleep (3600s) -> alert after 3 hours

That last row is the point of the floor-and-multiplier design: when you put the firmware
back into production mode, this rule retunes itself instead of alerting every minute.

> **Expect this to fire right now.** `TRUCK-LILYGO-001` is registered but not publishing,
> so it currently reports a silence ratio around 1440. That is correct behavior -- the
> board really is offline. Either pause this rule while building dashboards, or leave it
> as a live demonstration that offline detection works.

---

## Alert C — Low battery

Early warning, before a flat battery turns into an offline alert.

```sql
SELECT
  d.company,
  d.site,
  t.device_id,
  MIN(t.battery_pct) AS battery_pct
FROM telemetry t
JOIN devices d USING (device_id)
WHERE t.recorded_at > now() - interval '5 minutes'
  AND t.battery_pct IS NOT NULL
GROUP BY d.company, d.site, t.device_id;
```

**Condition:** `battery_pct < 20`

`ALO-SIM-05` is scripted to sit at low battery so this panel always has something to show.

---

## Panel 1 — Fleet status table (the single pane of glass)

One row per device, current state, colour-coded. This is the panel someone looks at first.

```sql
SELECT DISTINCT ON (d.device_id)
  d.company,
  d.site,
  d.device_id,
  t.temperature_c,
  d.temp_min_c,
  d.temp_max_c,
  t.battery_pct,
  t.recorded_at,
  CASE
    WHEN t.recorded_at IS NULL
      OR t.recorded_at < now() - (GREATEST(d.expected_interval_s * 3, 60) || ' seconds')::interval
      THEN 'OFFLINE'
    WHEN t.temperature_c > d.temp_max_c THEN 'HIGH'
    WHEN t.temperature_c < d.temp_min_c THEN 'LOW'
    ELSE 'OK'
  END AS status
FROM devices d
LEFT JOIN telemetry t
  ON t.device_id = d.device_id
 AND t.recorded_at > now() - interval '6 hours'
ORDER BY d.device_id, t.recorded_at DESC;
```

Add a value mapping on `status` so OK is green, HIGH/LOW red, OFFLINE grey.

---

## Panel 2 — Temperature over time

```sql
SELECT
  t.recorded_at AS "time",
  t.device_id   AS metric,
  t.temperature_c
FROM telemetry t
JOIN devices d USING (device_id)
WHERE $__timeFilter(t.recorded_at)
  AND d.company IN ($company)
ORDER BY t.recorded_at;
```

Needs the dashboard variable below. Add threshold lines at the selected company's limits.

---

## Panel 3 — Fleet map

```sql
SELECT DISTINCT ON (t.device_id)
  t.device_id,
  t.latitude,
  t.longitude,
  t.temperature_c
FROM telemetry t
JOIN devices d USING (device_id)
WHERE t.recorded_at > now() - interval '10 minutes'
  AND t.latitude IS NOT NULL
  AND d.company IN ($company)
ORDER BY t.device_id, t.recorded_at DESC;
```

Your physical board will not appear here -- its firmware has `lat`/`lon` commented out,
so those columns are NULL for every real reading. That is expected, not a bug.

---

## Panel 4 — Rejected readings

Makes sensor faults visible instead of leaving an unexplained gap in the chart.

```sql
SELECT
  received_at AS "time",
  device_id,
  reason,
  raw_payload
FROM rejected_readings
WHERE $__timeFilter(received_at)
ORDER BY received_at DESC;
```

---

## Dashboard variable — the company filter

Create a variable named `company`, type Query, multi-value and include-all enabled:

```sql
SELECT DISTINCT company FROM devices ORDER BY company;
```

This is what makes adding a fifth company free: insert its rows into `devices` and the
name appears in this dropdown on its own, with no dashboard edit.

---

## Adding a company later

1. Add the block to `COMPANIES` in `mock-device/fleet_simulator.py` (or insert rows into
   `devices` directly for real hardware).
2. Run `python fleet_simulator.py --setup-db`.
3. Add one route in the Slack notification policy if they want their own channel.

The dashboard variable, all three alert rules, and every panel pick it up automatically,
because they all read from `devices` rather than having company names written into them.
