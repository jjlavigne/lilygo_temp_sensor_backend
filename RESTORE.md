# Rebuilding this system on a new machine

Everything here assumes a fresh machine with **Docker** and **git** installed, and
nothing else.

Read this first: **the repository alone is not enough.** Four things live outside
git and cannot be recovered from it. Get them off the old machine *before* it goes
away.

## What you must carry across yourself

| Item | Where it lives now | Why it is not in git |
|---|---|---|
| `fleet_data-backup-*.sql.gz` | project root | Every reading. ~2 MB gzipped. |
| `.env` | project root | Passwords. `.env.example` documents the shape. |
| `firmware/firebeetle-fleet-firmware/src/config.h` | that path | WiFi + MQTT credentials. |
| `grafana-storage-backup-*.tar.gz` | project root | Dashboards, alert rules **and the Slack webhook**. ~21 MB. |

**The Slack webhook is inside that Grafana archive**, encrypted. It restores
correctly *provided no custom `GF_SECURITY_SECRET_KEY` is set* — none is today, so
Grafana uses its built-in default key and a restore on any machine decrypts it.
If you ever set one, it becomes a fifth thing to carry, and without it every
stored secret in that backup is unreadable.

Copy the webhook URL out of Slack into a password manager anyway. It costs a
minute and removes the only single point of failure in this list.

Put those four on a USB stick or in a password manager. Without the first, you
keep the system but lose the history; without the last, alerts stop.

Restoring the Grafana archive brings back dashboards, alert rules **and** the
Slack contact point in one step, which makes steps 5–7 unnecessary:

```bash
docker compose stop grafana
docker run --rm -v fleet-telemetry-pipeline_grafana-storage:/data -v "$PWD":/backup   alpine sh -c "rm -rf /data/* && tar xzf /backup/grafana-storage-backup-2026-09-04.tar.gz -C /data"
docker compose start grafana
```

That is the fastest route when moving to a machine you control. Steps 5–7 exist
for rebuilding from git alone, when you do not have the archive.

**Never put any of these four in the repository.** Git history is permanent — a
secret pushed once stays in the history even after the file is deleted, and this
repo already carries credentials from an earlier mistake (see the secrets section
of `CLAUDE.md`). Use a password manager and a USB stick or private cloud folder.

---

## 1. Clone and configure

```bash
git clone https://github.com/jjlavigne/lilygo_temp_sensor_backend.git fleet-telemetry-pipeline
cd fleet-telemetry-pipeline
cp .env.example .env
```

Edit `.env` and set every `change-me`. If you are restoring a database backup,
`POSTGRES_USER` / `POSTGRES_PASSWORD` **must match what the backup was taken
with**, or the restore fails on ownership.

## 2. Start the core stack

```bash
docker compose up -d
docker compose ps          # all should be Up; telemetry-db shows (healthy)
```

`ingestion.py` creates `telemetry` and `rejected_readings` on first start, so an
empty database is a working database.

## 3. Restore the readings

Skip if you are starting fresh and do not need the history.

```bash
gunzip -c fleet_data-backup-2026-09-04.sql.gz | \
  docker exec -i telemetry-db psql -U admin -d fleet_data
```

Verify:

```bash
docker exec telemetry-db psql -U admin -d fleet_data \
  -c "SELECT count(*) FROM telemetry; SELECT count(*) FROM devices;"
```

The 2026-09-04 backup holds ~197,900 readings and 22 devices.

## 4. Create the read-only Grafana role

Grafana does **not** connect as `admin`. This role is created by hand — compose
does not do it — and forgetting it is why a panel says
`permission denied for table X (SQLSTATE 42501)` while the same query works in
`psql`.

```sql
CREATE ROLE grafana_viewer LOGIN PASSWORD 'whatever you put in .env';
GRANT CONNECT ON DATABASE fleet_data TO grafana_viewer;
GRANT USAGE ON SCHEMA public TO grafana_viewer;
GRANT SELECT ON telemetry, admin_users, devices, rejected_readings TO grafana_viewer;

-- So tables created later are granted automatically. Without this, every new
-- table is invisible to Grafana until someone remembers to grant it.
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA public
  GRANT SELECT ON TABLES TO grafana_viewer;
```

Run with:

```bash
docker exec -i telemetry-db psql -U admin -d fleet_data
```

## 5. Connect Grafana to the database

Mount the provisioning file that ships in this repo — **this is the step where
you enable it**, and the only place it should ever be enabled. Add to the
`grafana` service in `docker-compose.yml`:

```yaml
    volumes:
      - grafana-storage:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro   # <-- add
    environment:
      GRAFANA_VIEWER_PASSWORD: ${GRAFANA_VIEWER_PASSWORD}     # <-- add
```

Then `docker compose up -d grafana`.

The datasource uid is pinned to `cfmk49pm86epsf` in that file. **Do not change
it.** Every dashboard panel refers to the datasource by uid; a different one
makes all three dashboards render "datasource not found".

## 6. Recreate the Slack contact point — by hand

In Grafana: **Alerting → Contact points → Add contact point**

- Name: **`Slack Integration`** — exactly this string. The alert rules route to
  it by name, so a different one silently sends nothing.
- Integration: Slack, with the webhook URL you carried across.

Send a test notification before moving on.

> **Never point Grafana's provisioning at `grafana/alerting/alert-rules.yaml`.**
> Alerting provisioning replaces the notification configuration wholesale and
> would delete the contact point you just made. That file is a record, not an
> input.

## 7. Import the dashboards and alert rules

Dashboards — **Dashboards → New → Import**, upload each of:

```
grafana/dashboards/fleet-command-center.json
grafana/dashboards/site-view.json
grafana/dashboards/device-detail.json
```

Alert rules — post each rule in `grafana/alerting/alert-rules.yaml` to the API.
The header keeps them editable in the UI instead of locked as provisioned:

```bash
curl -X POST http://localhost:3000/api/v1/provisioning/alert-rules \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Disable-Provenance: true" \
  -d @rule.json
```

Then confirm every rule query actually runs — a broken rule fails silently in the
scheduler and protects nothing:

```bash
python grafana/check_alert_rules.py
```

## 8. Simulated fleet (optional)

```bash
docker compose --profile sim up -d
```

If you skipped the database restore, register the devices first:

```bash
docker compose run --rm fleet-simulator python fleet_simulator.py --setup-db
```

## 9. Point the hardware at the new network

The board has the broker address and WiFi compiled in, so a new network means a
reflash. In `firmware/firebeetle-fleet-firmware/src/config.h`:

```c
const char* WIFI_SSID   = "...";          // 2.4 GHz only -- ESP32 cannot see 5 GHz
const char* WIFI_PASS   = "...";
const char* MQTT_BROKER = "192.168.x.x";  // the NEW host's LAN IP
const char* DEVICE_ID   = "Freezer-FireBeetle-001";  // must match devices exactly, case-sensitive
```

Find the new host IP with `ipconfig` (Windows) or `ip addr` (Linux). Then:

```bash
cd firmware/firebeetle-fleet-firmware
pio run -t upload
pio device monitor        # watch for "Connected to MQTT broker"
```

## 10. Check it end to end

```bash
docker compose ps                          # 5-6 services Up
docker compose logs -f ingestion           # "Stored ..." lines
python grafana/check_alert_rules.py        # all queries parse
curl -s localhost:8080/health              # {"status":"ok"}
```

Then open:

- Grafana — `http://<host-ip>:3000/d/fleet-command-center/fleet-command-center`
- Device admin — `http://<host-ip>:8080`

---

## Reaching it from other machines

Everything binds to the host on `3000`, `8080`, `1883`, `5432`, so anyone on the
**same network** can reach it at the host's LAN IP. There is nothing to configure
per client beyond a Grafana login.

From a **different** network it is unreachable without a VPN or port forwarding —
these are private addresses. Slack is unaffected either way: Grafana pushes out
to Slack, so alerts arrive anywhere.

The host IP is not fixed. If it changes, Grafana and the admin UI simply move
with it, but **the board does not** — its broker address is compiled in, so it
needs a reflash. A DHCP reservation for the host avoids that entirely, and is
worth doing on any network you intend to stay on.

## Keeping backups current

```bash
# Readings -- safe while running, no downtime
docker exec telemetry-db pg_dump -U admin -d fleet_data --clean --if-exists \
  | gzip > "fleet_data-backup-$(date +%Y-%m-%d).sql.gz"

# Grafana: dashboards, alert rules AND the Slack contact point.
# Stop it first -- grafana.db is SQLite and a hot copy can be inconsistent.
docker compose stop grafana
docker run --rm -v fleet-telemetry-pipeline_grafana-storage:/data -v "$PWD":/backup \
  alpine tar czf "/backup/grafana-storage-backup-$(date +%Y-%m-%d).tar.gz" -C /data .
docker compose start grafana
```

**The volume names carry the compose project prefix** — `fleet-telemetry-pipeline_pgdata`,
not `pgdata`. Mounting the unprefixed name does not fail; Docker silently creates
a new empty volume, and the backup comes out a few hundred bytes and looks fine.
Check against `docker volume ls` if a backup seems small.

Those archives contain credentials. Keep them out of the repository.
