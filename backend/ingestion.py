import json
import os
import time
import paho.mqtt.client as mqtt
import psycopg2
import datetime

# --- Configuration ---
# Every setting reads from the environment with a localhost default, so the same
# file works in both places without edits:
#   * run directly on the VM  -> defaults apply (localhost)
#   * run inside a container  -> compose supplies the Docker service names,
#                                because inside a container "localhost" is the
#                                container itself, not the VM.
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "fleet/telemetry")
MQTT_USER = os.getenv("MQTT_USER", "fleet_admin")
MQTT_PASS = os.getenv("MQTT_PASS", "Plymouth2026!")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "fleet_data")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password123")

# --- Plausibility bounds -- NOT the alert thresholds ---
# These exist for one job only: reject values the DS18B20 physically cannot produce.
# A disconnected probe reports -127.0, which is a broken wire, not a temperature.
#
# "Too warm" is deliberately NOT decided here. Alert limits differ per company
# (produce runs 2 to 6 C, frozen goods run -23 to -18 C) and they live in the
# devices table, evaluated by Grafana. If this script discarded readings for being
# alarming, they would never reach the database, and Grafana could never alert on
# them -- you cannot raise an alarm about a reading you deleted.
SENSOR_MIN_C = -55.0
SENSOR_MAX_C = 125.0

# Module-level connection handle. Deliberately rebuilt on demand rather than opened
# once at startup, so a Postgres restart does not permanently break ingestion.
db_conn = None


def connect_db(quiet=False):
    """Open a fresh connection to Postgres. Returns None on failure."""
    try:
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, database=DB_NAME,
            user=DB_USER, password=DB_PASSWORD
        )
    except Exception as e:
        if not quiet:
            print(f"Database connection failed. Is the Postgres container running? Error: {e}")
        return None


def ensure_schema(conn):
    """Create the tables if they don't already exist. Safe to call repeatedly."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id SERIAL PRIMARY KEY,
            device_id VARCHAR(50) NOT NULL,
            recorded_at TIMESTAMP NOT NULL,
            temperature_c REAL NOT NULL,
            latitude REAL,
            longitude REAL,
            battery_pct INTEGER
        );
    """)

    # Rejected readings are recorded rather than silently discarded. Without this,
    # a probe that fell off and a truck in a dead zone look identical -- both are
    # just a gap in the data. For a cold chain record, an unexplained gap is a
    # liability, so we keep the evidence.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rejected_readings (
            id SERIAL PRIMARY KEY,
            device_id VARCHAR(50),
            received_at TIMESTAMP NOT NULL,
            reason VARCHAR(60) NOT NULL,
            raw_payload TEXT
        );
    """)

    conn.commit()
    cursor.close()


def close_connection():
    """Drop the current handle so the next write builds a fresh one."""
    global db_conn
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception:
            pass
    db_conn = None


def get_connection():
    """Return a live connection, reconnecting if the previous one died."""
    global db_conn
    if db_conn is not None and db_conn.closed == 0:
        return db_conn

    db_conn = connect_db(quiet=True)
    if db_conn is not None:
        ensure_schema(db_conn)
        print("Database connection established.")
    return db_conn


def execute_write(query, params):
    """
    Run a write, reconnecting once if the connection has gone away.

    This is the fix for the failure that used to kill the service: the connection
    was opened once at import, so when Postgres restarted, every later insert
    failed forever and the rollback in the error handler failed too. The script
    stayed running and silently stored nothing until somebody noticed.
    """
    for attempt in (1, 2):
        conn = get_connection()
        if conn is None:
            if attempt == 2:
                print("Dropped message: database unreachable.")
            continue

        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            cursor.close()
            return True

        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # The connection itself is broken. Throw it away and let attempt 2
            # build a new one.
            print(f"Lost database connection ({type(e).__name__}). Reconnecting...")
            close_connection()

        except Exception as e:
            # A real query error (bad data, constraint violation). The connection
            # is still fine, so roll back the partial transaction and give up on
            # this one message rather than retrying it.
            print(f"Database insertion error: {e}")
            try:
                conn.rollback()
            except Exception:
                close_connection()
            return False

    return False


def record_rejection(device_id, reason, raw_payload):
    """Log a reading we refused to store, so the gap can be explained later."""
    print(f"Rejected [{reason}] from {device_id or 'unknown device'}")
    execute_write("""
        INSERT INTO rejected_readings (device_id, received_at, reason, raw_payload)
        VALUES (%s, %s, %s, %s);
    """, (
        device_id,
        datetime.datetime.now(datetime.timezone.utc),
        reason,
        raw_payload[:2000],   # guard against a runaway payload
    ))


def on_connect(client, userdata, flags, rc):
    """Callback fired the moment the script logs into the MQTT broker."""
    if rc == 0:  # rc is the return code; 0 means the connection was flawless
        print(f"Connected to MQTT Broker! Listening to topic: {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect to broker, return code {rc}")
        if rc in (4, 5):
            print("  -> Broker rejected the credentials. Check MQTT_USER/MQTT_PASS against pwfile.")


def on_message(client, userdata, msg):
    """Fires every time a new message arrives on the subscribed topic."""
    raw = msg.payload.decode("utf-8", errors="replace")

    # 1. Parse the JSON payload into a Python dictionary
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        record_rejection(None, "malformed_json", raw)
        return

    if not isinstance(payload, dict):
        record_rejection(None, "payload_not_an_object", raw)
        return

    # 2. Structural validation -- lat/lon/battery stay optional because the LilyGO
    #    sends partial payloads when it has no GPS fix.
    device_id = payload.get("device_id")
    if not device_id or "temperature_c" not in payload:
        record_rejection(device_id, "missing_required_keys", raw)
        return

    # 3. Plausibility check -- is this a number a real sensor could produce?
    try:
        temp = float(payload["temperature_c"])
    except (TypeError, ValueError):
        record_rejection(device_id, "temperature_not_a_number", raw)
        return

    if not (SENSOR_MIN_C <= temp <= SENSOR_MAX_C):
        # -127.0 lands here, which is the DS18B20's disconnected-probe signature.
        record_rejection(device_id, "implausible_temperature", raw)
        return

    # 4. Store it. Every plausible reading is kept, including alarming ones --
    #    Grafana decides which of these are excursions.
    lat = payload.get("lat")
    lon = payload.get("lon")
    battery_pct = payload.get("battery_pct")

    stored = execute_write("""
        INSERT INTO telemetry (device_id, recorded_at, temperature_c, latitude, longitude, battery_pct)
        VALUES (%s, %s, %s, %s, %s, %s);
    """, (
        device_id,
        datetime.datetime.now(datetime.timezone.utc),
        temp,
        lat,
        lon,
        battery_pct,
    ))

    if stored:
        print(f"Stored {device_id} | Temp: {temp}°C | Battery: {battery_pct}%")


# --- Main Execution loop ---
if __name__ == "__main__":
    print("Starting Backend Ingestion Service...")

    # Wait for Postgres rather than exiting, so this can start alongside the
    # containers without a race on which comes up first.
    for attempt in range(10):
        if get_connection() is not None:
            break
        print(f"  Waiting for database... ({attempt + 1}/10)")
        time.sleep(3)
    else:
        print("Database not reachable yet -- starting anyway and will keep retrying.")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nShutting down service...")
    finally:
        close_connection()
        client.disconnect()
