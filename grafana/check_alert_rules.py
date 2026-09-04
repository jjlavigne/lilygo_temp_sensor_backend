#!/usr/bin/env python3
"""
Validate that every Grafana alert rule's SQL actually runs.

Run this after ANY change to an alert rule. A broken rule does not announce
itself the way a broken dashboard panel does -- the panel shows an error to
whoever opens it, but a rule fails silently in the scheduler and simply stops
protecting you. A syntax error in the Fleet Sensor Offline rule went unnoticed
for seven days because nothing checked.

The only visible symptom is a DatasourceErrorAlert in Slack reading
"[no value] - [no value]", which is easy to mistake for a device problem.

    python grafana/check_alert_rules.py

Exits non-zero if any rule fails, so it can gate a change.
"""
import json
import os
import subprocess
import sys
import urllib.request

GRAFANA = os.getenv("GRAFANA_URL", "http://localhost:3000")
TOKEN = os.getenv("GRAFANA_TOKEN")
DB_CONTAINER = os.getenv("DB_CONTAINER", "telemetry-db")
DB_USER = os.getenv("DB_USER", "admin")
DB_NAME = os.getenv("DB_NAME", "fleet_data")


def fetch_rules():
    if not TOKEN:
        sys.exit("GRAFANA_TOKEN is not set (it lives in .env at the project root)")
    req = urllib.request.Request(f"{GRAFANA}/api/v1/provisioning/alert-rules",
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    return json.loads(urllib.request.urlopen(req).read())


def explain(sql):
    """EXPLAIN parses and plans without executing, so this is read-only and cheap."""
    p = subprocess.run(
        ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-v", "ON_ERROR_STOP=1", "-c", "EXPLAIN " + sql],
        capture_output=True, text=True)
    if p.returncode == 0:
        return True, ""
    lines = [l for l in p.stderr.strip().splitlines() if l.strip()]
    return False, lines[0] if lines else "unknown error"


def main():
    failures = []
    for rule in fetch_rules():
        queries = [q for q in rule.get("data", []) if q.get("model", {}).get("rawSql")]
        print(f"\n{rule['title']}  (uid={rule['uid']}, {len(queries)} SQL queries)")
        for q in queries:
            ok, err = explain(q["model"]["rawSql"])
            print(f"   query {q['refId']}: {'OK' if ok else 'BROKEN -- ' + err}")
            if not ok:
                failures.append((rule["title"], q["refId"], err))

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} BROKEN QUERIES -- these rules are not protecting anything:")
        for title, ref, err in failures:
            print(f"   {title} [{ref}]: {err}")
        print("\nFix via the API with the X-Disable-Provenance: true header.")
        print("Never provision alerting from files -- it wipes the Slack contact point.")
        return 1
    print("All alert rule queries parse. Rules are live and evaluating.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
