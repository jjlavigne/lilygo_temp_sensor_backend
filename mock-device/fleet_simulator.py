"""
fleet_simulator.py — Multi-tenant fleet telemetry simulator.

Simulates 4 companies x 5 refrigeration sensors (20 mock devices) so the Grafana
command center can be tested at scale without provisioning physical hardware.

The real LilyGO board (TRUCK-LILYGO-001) is registered as a 6th Plymouth device but
is NEVER simulated here -- it publishes its own live readings from the DS18B20 probe.
That keeps the prototype device as the star of the demo while the other 21 nodes
provide a realistic fleet around it.

Two modes:

  live      Publishes over MQTT, exercising the real pipeline
            (broker -> ingestion.py -> Postgres). This is what you run during a demo.

  backfill  Writes historical rows DIRECTLY to Postgres. Required because
            ingestion.py stamps recorded_at = now(), so history cannot be replayed
            through MQTT -- every backdated reading would land with today's timestamp.

Usage:
    python fleet_simulator.py --setup-db            # create devices table, register fleet
    python fleet_simulator.py --backfill-hours 24   # populate dashboards with history
    python fleet_simulator.py                       # live publish (demo scenario)
    python fleet_simulator.py --scenario healthy    # everything nominal
    python fleet_simulator.py --fail ALO-SIM-02     # force a specific device to fail

This script only ever INSERTs and CREATEs. It never drops tables or deletes rows.
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import execute_values

# --- Configuration (matches backend/ingestion.py) ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "fleet/telemetry"
MQTT_USER = "fleet_admin"
MQTT_PASS = "Plymouth2026!"

DB_HOST = "localhost"
DB_NAME = "fleet_data"
DB_USER = "admin"
DB_PASSWORD = "password123"

# The physical prototype board. Registered so it inherits Plymouth's alert limits
# and shows up on the dashboard, but never simulated.
REAL_DEVICE_ID = "TRUCK-LILYGO-001"

SIM_SENSORS_PER_COMPANY = 5

# Plausibility bounds enforced by ingestion.py. Mirrored here so backfilled history
# behaves identically to live data. Keep in sync if you change ingestion.py.
INGEST_MIN_C = -40.0
INGEST_MAX_C = 101.0

# --- Timing ------------------------------------------------------------------
# These are the only numbers you need to touch to retune the demo's pace.
# Changing PUBLISH_INTERVAL_S automatically updates the staleness alert too,
# because expected_interval_s is written to the devices table from it.

PUBLISH_INTERVAL_S = 15        # how often each simulated sensor reports

REAL_DEVICE_INTERVAL_S = 5     # how often the physical board reports. Faster than
                               # the simulated fleet on purpose: it is the device
                               # the audience is watching, so it should react while
                               # you are still holding it over the water. Keep this
                               # matched to the delay in your firmware's loop().
                               # Set to 3600 when the board returns to hourly deep
                               # sleep for production.

# The staleness alert fires when a device has been silent for this many times its
# expected interval. At 15s that means an alert roughly 45 seconds after a sensor
# dies -- fast enough to demonstrate live, too twitchy for production (use 3-5x an
# hourly interval there).
STALENESS_MULTIPLIER = 3

SIM_EXPECTED_INTERVAL_S = PUBLISH_INTERVAL_S
REAL_EXPECTED_INTERVAL_S = REAL_DEVICE_INTERVAL_S


# --- Fleet definition ---------------------------------------------------------
# Each company gets its own safe temperature band, because a produce hauler and a
# frozen-goods hauler do not share limits. This is what makes per-tenant alerting
# meaningful rather than one global threshold applied to everybody.

COMPANIES = [
    {
        "name": "Plymouth",
        "prefix": "PLY",
        "cargo": "chilled produce",
        "temp_min_c": 2.0,
        "temp_max_c": 6.0,
        "sites": [
            {"name": "Seattle DC", "lat": 47.6062, "lon": -122.3321},
            {"name": "Tacoma Yard", "lat": 47.2529, "lon": -122.4443},
        ],
    },
    {
        "name": "Aloha",
        "prefix": "ALO",
        "cargo": "chilled produce",
        "temp_min_c": 1.0,
        "temp_max_c": 5.0,
        "sites": [
            {"name": "Honolulu Port", "lat": 21.3069, "lon": -157.8583},
            {"name": "Kahului Depot", "lat": 20.8893, "lon": -156.4729},
        ],
    },
    {
        "name": "Nikky USA",
        "prefix": "NIK",
        "cargo": "frozen goods",
        "temp_min_c": -23.0,
        "temp_max_c": -18.0,
        "sites": [
            {"name": "Portland Cold Store", "lat": 45.5152, "lon": -122.6784},
            {"name": "Boise Transfer", "lat": 43.6150, "lon": -116.2023},
        ],
    },
    {
        "name": "S&J",
        "prefix": "SNJ",
        "cargo": "dairy",
        "temp_min_c": 0.0,
        "temp_max_c": 4.0,
        "sites": [
            {"name": "Spokane Hub", "lat": 47.6588, "lon": -117.4260},
            {"name": "Yakima Line", "lat": 46.6021, "lon": -120.5059},
        ],
    },
]

# The physical board sits on the demo bench, grouped under Plymouth.
REAL_DEVICE_SITE = {"name": "Demo Bench", "lat": 47.6062, "lon": -122.3321}


# --- Device behavior states ---------------------------------------------------
# NORMAL       holds inside the safe band with realistic drift
# DOOR_OPEN    ramps upward past the max limit and stays there (the classic failure)
# OVERCOOL     drifts below the min limit (freeze damage on produce)
# SENSOR_FAULT reports -127 C, exactly what a disconnected DS18B20 returns
# OFFLINE      stops publishing entirely, so it can only be caught by a staleness alert

STATE_NORMAL = "normal"
STATE_DOOR_OPEN = "door_open"
STATE_OVERCOOL = "overcool"
STATE_SENSOR_FAULT = "sensor_fault"
STATE_OFFLINE = "offline"


class SimulatedDevice:
    """Holds the running state for one mock sensor."""

    def __init__(self, device_id, company, site):
        self.device_id = device_id
        self.company = company
        self.site = site

        # Start each device at a slightly different point inside its safe band so
        # the dashboard does not show 20 identical flat lines.
        span = company["temp_max_c"] - company["temp_min_c"]
        self.baseline = company["temp_min_c"] + span * random.uniform(0.3, 0.7)
        self.temp = self.baseline

        self.battery = random.uniform(75.0, 100.0)
        self.state = STATE_NORMAL
        self.fail_after_s = None   # seconds into the run before state kicks in
        self.pending_state = None

        # Small per-device GPS jitter so map markers do not stack perfectly.
        self.lat = site["lat"] + random.uniform(-0.02, 0.02)
        self.lon = site["lon"] + random.uniform(-0.02, 0.02)

    def schedule_failure(self, state, after_s):
        self.pending_state = state
        self.fail_after_s = after_s

    def step(self, elapsed_s, interval_s):
        """Advance the simulation by one interval and return the new temperature."""
        # Activate a scheduled failure once we pass its trigger time.
        if self.pending_state and elapsed_s >= self.fail_after_s:
            self.state = self.pending_state
            self.pending_state = None

        if self.state == STATE_SENSOR_FAULT:
            # A disconnected DS18B20 does not drift -- it reads a hard -127.0.
            self.temp = -127.0
            return self.temp

        if self.state == STATE_DOOR_OPEN:
            # Warm toward ~8 C above the ceiling, fast at first then tapering,
            # which is roughly how an unrefrigerated box behaves.
            target = self.company["temp_max_c"] + 8.0
            self.temp += (target - self.temp) * 0.06 + random.uniform(-0.05, 0.05)

        elif self.state == STATE_OVERCOOL:
            target = self.company["temp_min_c"] - 4.0
            self.temp += (target - self.temp) * 0.05 + random.uniform(-0.05, 0.05)

        else:
            # Mean-reverting random walk: wanders around the baseline but is pulled
            # back, so it never drifts out of band on its own.
            self.temp += (self.baseline - self.temp) * 0.15
            self.temp += random.gauss(0, 0.18)

        # Battery drains slowly; scaled so a long run shows visible decline.
        self.battery = max(0.0, self.battery - (interval_s / 3600.0) * random.uniform(0.4, 1.2))

        return self.temp

    def payload(self):
        """Build the JSON payload. Key names must match ingestion.py exactly."""
        return {
            "device_id": self.device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature_c": round(self.temp, 2),
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "battery_pct": int(self.battery),
        }


def build_fleet():
    """Create all simulated devices, spreading each company's sensors across sites."""
    fleet = []
    for company in COMPANIES:
        for i in range(SIM_SENSORS_PER_COMPANY):
            site = company["sites"][i % len(company["sites"])]
            device_id = f"{company['prefix']}-SIM-{i + 1:02d}"
            fleet.append(SimulatedDevice(device_id, company, site))
    return fleet


# --- Demo scenarios -----------------------------------------------------------

def apply_scenario(fleet, scenario, forced_failures):
    """
    Put the fleet into a known state.

    'demo' is deliberately scripted rather than random, so a presentation tells the
    same story every time and each alert type gets exercised:

      Plymouth  stays clean -- the live board is the one that goes into alarm
      Aloha     a door-open failure ramping past the ceiling  (high-temp alert)
      Nikky USA a disconnected probe reporting -127 C         (plausibility filter)
      S&J       a node that goes silent                        (staleness alert)
    """
    by_id = {d.device_id: d for d in fleet}

    if scenario == "demo":
        # Staggered so the alerts do not all land at once during a presentation.
        by_id["ALO-SIM-02"].schedule_failure(STATE_DOOR_OPEN, after_s=90)
        by_id["NIK-SIM-04"].schedule_failure(STATE_SENSOR_FAULT, after_s=180)
        by_id["SNJ-SIM-01"].schedule_failure(STATE_OFFLINE, after_s=240)
        by_id["SNJ-SIM-03"].schedule_failure(STATE_OVERCOOL, after_s=300)
        by_id["ALO-SIM-05"].battery = 12.0  # low-battery panel has something to show

    elif scenario == "chaos":
        for device in random.sample(fleet, k=max(1, len(fleet) // 4)):
            device.schedule_failure(
                random.choice([STATE_DOOR_OPEN, STATE_OVERCOOL, STATE_SENSOR_FAULT, STATE_OFFLINE]),
                after_s=random.randint(30, 300),
            )

    # 'healthy' intentionally schedules nothing.

    for device_id in forced_failures:
        if device_id in by_id:
            by_id[device_id].schedule_failure(STATE_DOOR_OPEN, after_s=0)
            print(f"  Forced failure: {device_id}")
        else:
            print(f"  WARNING: unknown device '{device_id}' -- ignored")


# --- Database -----------------------------------------------------------------

def db_connect():
    try:
        return psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
    except Exception as e:
        print(f"Database connection failed. Is the Postgres container running? Error: {e}")
        return None


def setup_db(fleet):
    """
    Create the devices metadata table and register the fleet.

    This is purely additive -- it does not touch the telemetry table's existing rows.
    Company and site live here rather than in the MQTT payload on purpose: a device
    that reports its own tenant could claim to belong to a different company, which
    is not acceptable once multiple customers share one database.
    """
    conn = db_connect()
    if not conn:
        return False
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id           VARCHAR(50) PRIMARY KEY,
            company             VARCHAR(50) NOT NULL,
            site                VARCHAR(50) NOT NULL,
            cargo               VARCHAR(50),
            temp_min_c          REAL NOT NULL,
            temp_max_c          REAL NOT NULL,
            expected_interval_s INTEGER NOT NULL DEFAULT 60,
            is_simulated        BOOLEAN NOT NULL DEFAULT TRUE
        );
    """)

    # Dashboards filter by device and time constantly; without these every panel
    # is a sequential scan once the table has any real history in it.
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_recorded_at
            ON telemetry (recorded_at DESC);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
            ON telemetry (device_id, recorded_at DESC);
    """)

    rows = [
        (d.device_id, d.company["name"], d.site["name"], d.company["cargo"],
         d.company["temp_min_c"], d.company["temp_max_c"], SIM_EXPECTED_INTERVAL_S, True)
        for d in fleet
    ]

    # Register the physical board under Plymouth so it inherits Plymouth's limits.
    # Its expected interval is separate because the board reports on its own schedule.
    plymouth = next(c for c in COMPANIES if c["name"] == "Plymouth")
    rows.append((
        REAL_DEVICE_ID, plymouth["name"], REAL_DEVICE_SITE["name"], plymouth["cargo"],
        plymouth["temp_min_c"], plymouth["temp_max_c"], REAL_EXPECTED_INTERVAL_S, False,
    ))

    execute_values(cursor, """
        INSERT INTO devices (device_id, company, site, cargo, temp_min_c, temp_max_c,
                             expected_interval_s, is_simulated)
        VALUES %s
        ON CONFLICT (device_id) DO UPDATE SET
            company             = EXCLUDED.company,
            site                = EXCLUDED.site,
            cargo               = EXCLUDED.cargo,
            temp_min_c          = EXCLUDED.temp_min_c,
            temp_max_c          = EXCLUDED.temp_max_c,
            expected_interval_s = EXCLUDED.expected_interval_s;
    """, rows)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"Registered {len(rows)} devices ({len(rows) - 1} simulated + 1 physical).")
    for company in COMPANIES:
        print(f"  {company['name']:<10} {company['temp_min_c']:>6.1f} to {company['temp_max_c']:>5.1f} C  ({company['cargo']})")
    return True


def backfill(fleet, hours, interval_s):
    """
    Write historical readings straight to Postgres.

    This bypasses MQTT deliberately. ingestion.py stamps recorded_at with the server
    clock, so replaying history through the broker would collapse every backdated
    reading onto the current timestamp.
    """
    conn = db_connect()
    if not conn:
        return False
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    steps = int((hours * 3600) / interval_s)

    print(f"Generating {hours}h of history at {interval_s}s intervals "
          f"({steps} steps x {len(fleet)} devices = {steps * len(fleet):,} rows)...")

    rows = []
    dropped = 0
    for step in range(steps):
        elapsed = step * interval_s
        stamp = start + timedelta(seconds=elapsed)
        for device in fleet:
            temp = device.step(elapsed, interval_s)
            if device.state == STATE_OFFLINE:
                continue  # an offline node leaves a gap, which is the point
            # Apply the same plausibility filter ingestion.py uses, so backfilled
            # history matches what the live pipeline would actually have stored.
            # Without this a -127 sensor fault shows up in history but never in
            # live data, and the two silently disagree.
            if not (INGEST_MIN_C <= temp <= INGEST_MAX_C):
                dropped += 1
                continue
            rows.append((
                device.device_id, stamp, round(temp, 2),
                round(device.lat, 6), round(device.lon, 6), int(device.battery),
            ))

    execute_values(cursor, """
        INSERT INTO telemetry (device_id, recorded_at, temperature_c, latitude, longitude, battery_pct)
        VALUES %s;
    """, rows, page_size=1000)

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Inserted {len(rows):,} historical rows.")
    return True


# --- MQTT ---------------------------------------------------------------------

def make_client(client_id):
    """Build a paho client that works on both 1.x and 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker.")
    else:
        # 4 and 5 mean the broker rejected the credentials, which is the most
        # likely failure given mosquitto.conf sets allow_anonymous false.
        print(f"Failed to connect to broker, return code {rc}")
        if rc in (4, 5):
            print("  -> Bad credentials. Check MQTT_USER / MQTT_PASS against pwfile.")


def run_live(fleet, interval_s, duration_s):
    """Publish readings for the whole fleet on a fixed interval."""
    client = make_client("fleet-simulator")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"Could not reach the broker at {MQTT_BROKER}:{MQTT_PORT} -- {e}")
        return False

    client.loop_start()

    print(f"\nSimulating {len(fleet)} devices every {interval_s}s. Ctrl-C to stop.")
    print(f"The physical board ({REAL_DEVICE_ID}) publishes on its own -- not simulated.\n")

    start = time.time()
    try:
        while True:
            elapsed = time.time() - start
            if duration_s and elapsed >= duration_s:
                print("\nDuration reached.")
                break

            alarms = []
            for device in fleet:
                device.step(elapsed, interval_s)
                if device.state == STATE_OFFLINE:
                    continue  # silent on purpose

                client.publish(MQTT_TOPIC, json.dumps(device.payload()))

                if device.temp > device.company["temp_max_c"]:
                    alarms.append(f"{device.device_id} HIGH {device.temp:.1f}C")
                elif device.temp < device.company["temp_min_c"]:
                    alarms.append(f"{device.device_id} LOW {device.temp:.1f}C")

            live = sum(1 for d in fleet if d.state != STATE_OFFLINE)
            stamp = datetime.now().strftime("%H:%M:%S")
            summary = f"[{stamp}] published {live}/{len(fleet)}"
            if alarms:
                summary += "  |  " + ", ".join(alarms[:4])
                if len(alarms) > 4:
                    summary += f" (+{len(alarms) - 4} more)"
            print(summary)

            time.sleep(interval_s)

    except KeyboardInterrupt:
        print("\nShutting down simulator...")
    finally:
        client.loop_stop()
        client.disconnect()
    return True


# --- Entry point --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Simulate a multi-company refrigerated fleet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--setup-db", action="store_true",
                        help="Create the devices table and register the fleet, then exit")
    parser.add_argument("--backfill-hours", type=float, default=0,
                        help="Write N hours of history directly to Postgres, then exit")
    parser.add_argument("--backfill-interval", type=int, default=60,
                        help="Seconds between backfilled readings (default 60)")
    parser.add_argument("--interval", type=int, default=PUBLISH_INTERVAL_S,
                        help=f"Seconds between live publishes (default {PUBLISH_INTERVAL_S})")
    parser.add_argument("--duration", type=int, default=0,
                        help="Stop after N seconds (default: run until Ctrl-C)")
    parser.add_argument("--scenario", choices=["demo", "healthy", "chaos"], default="demo",
                        help="Failure script to run (default: demo)")
    parser.add_argument("--fail", action="append", default=[], metavar="DEVICE_ID",
                        help="Force a device into a high-temp failure immediately")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed, for a byte-identical repeat run")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    fleet = build_fleet()
    print(f"Fleet: {len(COMPANIES)} companies x {SIM_SENSORS_PER_COMPANY} sensors "
          f"= {len(fleet)} simulated devices\n")

    if args.setup_db:
        return 0 if setup_db(fleet) else 1

    apply_scenario(fleet, args.scenario, args.fail)

    if args.backfill_hours > 0:
        return 0 if backfill(fleet, args.backfill_hours, args.backfill_interval) else 1

    return 0 if run_live(fleet, args.interval, args.duration) else 1


if __name__ == "__main__":
    sys.exit(main())
