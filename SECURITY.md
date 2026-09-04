# Credentials in this repository

**This repository is PRIVATE and contains live credentials and data backups.**
That is a deliberate handover decision, not an accident: the alternative was
losing the system when the VM it runs on was returned.

Keep the repository private. If it is ever made public, or a collaborator is
added who should not have production access, **every credential below must be
rotated first.**

## What is stored here

| File | Contains |
|---|---|
| `.env` | Postgres password, device-admin login, Grafana service-account token, Flask session key |
| `firmware/firebeetle-fleet-firmware/src/config.h` | WiFi SSID + password, MQTT username + password |
| `firmware/fleet-telemetry-firmware/src/config.h` | LilyGO WiFi credentials (committed before this decision, by mistake) |
| `pwfile` | Mosquitto password hash |
| `backend/ingestion.py`, `mock-device/test_alert.py` | MQTT user/password in source |
| `docker-compose.yml` | Postgres password default |
| `fleet_data-backup-*.sql.gz` | Every reading, plus `admin_users` password hashes |
| `grafana-storage-backup-*.tar.gz` | Grafana database — dashboards, alert rules, and the **encrypted Slack webhook** |

## Rotation checklist

Work through this when the system moves to a permanent home, or immediately if
the repository is ever exposed. Nothing here is difficult; it is a half-hour job.

- [ ] **WiFi password** — change on the network, then update `config.h` and
      reflash the board. This is the only one that requires touching hardware.
- [ ] **MQTT user/password** — regenerate `pwfile` with
      `mosquitto_passwd -c pwfile fleet_admin`, then update `backend/ingestion.py`,
      `mock-device/test_alert.py`, `mock-device/fleet_simulator.py` and the
      firmware `config.h`. Restart the broker and every publisher.
- [ ] **Postgres password** — `ALTER ROLE admin WITH PASSWORD '...'`, then update
      `.env` and `docker-compose.yml`.
- [ ] **`grafana_viewer` password** — `ALTER ROLE grafana_viewer WITH PASSWORD '...'`,
      then update the Grafana datasource.
- [ ] **Device-admin login** — update `ADMIN_USER` / `ADMIN_PASSWORD` in `.env`
      and restart `device-admin`.
- [ ] **`ADMIN_SECRET_KEY`** — any long random string. Changing it logs everyone out.
- [ ] **Grafana service-account token** — revoke in
      *Administration → Service accounts*, issue a new one, update `.env`.
- [ ] **Slack webhook** — regenerate in Slack, then update the contact point in
      *Alerting → Contact points*. Send a test notification afterwards.

**Rotating a secret does not erase it from git history.** The old value stays in
every past commit and remains readable by anyone who can clone the repo. Rotation
makes the exposed value useless; it does not make it invisible. Only rewriting
history (`git filter-repo`) removes it, and that breaks every existing clone.

## The better long-term shape

Move the secrets out of tracked files entirely:

1. Everything in `.env`, which is gitignored, with `.env.example` as the record
   of what is needed. `.env.example` already exists.
2. `backend/ingestion.py`, `mock-device/*.py` and `admin/app.py` already read
   their configuration from environment variables — the literals in them are only
   fallback defaults, so removing the hardcoded values is a small change.
3. Firmware `config.h` stays gitignored and travels by hand or password manager.
   It cannot read environment variables; it is compiled in.
4. Keep the data backups out of the repo and in object storage or a password
   manager's file vault, so the repo holds code and the backups hold data.

That is the arrangement to adopt once the system has a permanent home. Until
then, a private repository holding everything is a defensible trade — losing the
work entirely is the worse outcome.
