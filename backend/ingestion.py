import json
import paho.mqtt.client as mqtt
import psycopg2

# --- Configuration ---
# MQTT Broker Settings
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "fleet/telemetry"

# PostgreSQL Database Settings
DB_HOST = "localhost"
DB_NAME = "fleet_data"
DB_USER = "admin"
DB_PASSWORD = "password123"

def init_db():
    """Connects to the database and ensures the telemetry table exists."""
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        cursor = conn.cursor()
        
        # Create the table if it doesn't already exist
        create_table_query = """
        CREATE TABLE IF NOT EXISTS telemetry (
            id SERIAL PRIMARY KEY,
            device_id VARCHAR(50) NOT NULL,
            recorded_at TIMESTAMP NOT NULL,
            temperature_c REAL NOT NULL,
            latitude REAL,
            longitude REAL,
            battery_pct INTEGER
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        print("Database initialized and table verified.")
        return conn, cursor
    except Exception as e:
        print(f"Database connection failed. Is the Postgres container running? Error: {e}")
        return None, None

# Initialize Database Connection
db_conn, db_cursor = init_db()

def on_connect(client, userdata, flags, rc):
    """Fires when the script successfully connects to the broker."""
    if rc == 0:
        print(f"Connected to MQTT Broker! Listening to topic: {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect to broker, return code {rc}")

def on_message(client, userdata, msg):
    """Fires every time a new message arrives on the subscribed topic."""
    if not db_conn:
        print("Dropped message: No database connection.")
        return

    try:
        # 1. Decode the JSON payload
        payload = json.loads(msg.payload.decode('utf-8'))
        print(f"Received data from {payload['device_id']}: {payload['temperature_c']}°C")

        # 2. Insert the data safely to prevent SQL injection
        insert_query = """
        INSERT INTO telemetry (device_id, recorded_at, temperature_c, latitude, longitude, battery_pct)
        VALUES (%s, %s, %s, %s, %s, %s);
        """
        db_cursor.execute(insert_query, (
            payload['device_id'],
            payload['timestamp'],
            payload['temperature_c'],
            payload['lat'],
            payload['lon'],
            payload['battery_pct']
        ))
        db_conn.commit()
        
    except json.JSONDecodeError:
        print("Error: Received malformed JSON payload.")
    except Exception as e:
        print(f"Database insertion error: {e}")
        db_conn.rollback()

# --- Main Execution ---
if __name__ == "__main__":
    if db_conn:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message

        try:
            print("Starting Backend Ingestion Service...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever() # Keeps the script running and listening
        except KeyboardInterrupt:
            print("\nShutting down service...")
        finally:
            db_cursor.close()
            db_conn.close()
            client.disconnect()