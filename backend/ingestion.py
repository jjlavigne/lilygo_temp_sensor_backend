import json
import paho.mqtt.client as mqtt
import psycopg2
import datetime

# --- Configuration ---
# MQTT Broker Settings
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "fleet/telemetry"
MQTT_USER = "fleet_admin"
MQTT_PASS = "Plymouth2026!"

# PostgreSQL Database Settings
DB_HOST = "localhost"
DB_NAME = "fleet_data"
DB_USER = "admin"
DB_PASSWORD = "password123"

def init_db():
    """Connects to the database and ensures the telemetry table exists."""
    try:
        # Attemps to open a network connection to the Postgres database using the credentials from the config block
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        # Creates a "cursor" object (the physical vehicle that carries my SQL commands into the database and brings the results back)
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
        cursor.execute(create_table_query) #Hands the SQL command to the cursor to run 
        conn.commit() # Saves the changes. The DB doesnt finalize structural changes or data insertions until you explicitely "commit" them
        print("Database initialized and table verified.")
        return conn, cursor
    except Exception as e:
        print(f"Database connection failed. Is the Postgres container running? Error: {e}")
        return None, None

# Initialize Database Connection
db_conn, db_cursor = init_db()

def on_connect(client, userdata, flags, rc):
    """A "callback" function that is automatically triggered the moment the script successfully logs into the MQTT broker"""
    if rc == 0:  # rc stands for return code. A code of 0 means the connection was flawless
        print(f"Connected to MQTT Broker! Listening to topic: {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC) # After connection is established, this immeditaely tells the broker to forward every message published to fleet/telemetry
    else:
        print(f"Failed to connect to broker, return code {rc}")


# The heart of the script. Gets called everytime the Lilygo publishes a reading
# If the DB is offline, it immediately drops the message rather than crashing the script trying to save it 
def on_message(client, userdata, msg):
    """Fires every time a new message arrives on the subscribed topic."""
    if not db_conn:
        print("Dropped message: No database connection.")
        return

    try:
        # 1. Decodes the JSON payload into a readable string
        # Parses string into a Python dictionary so values can be accessed via keys
        payload = json.loads(msg.payload.decode('utf-8'))


        # --- ADDED VALIDATION BLOCK FOR SECURITY STARTS HERE ---

        # Structural Validation. Checks if the incoming JSON actually contains all necessary data (Ensure keys exist)
        # required_keys = ['device_id', 'temperature_c', 'lat', 'lon', 'battery_pct']
        required_keys = ['device_id', 'temperature_c']
        # If the LilyGO glitches and sends half a payload, this blocks it from ruining your database schema 
        if not all(k in payload for k in required_keys):
            print("Dropped message: Missing required JSON keys.")
            return

        # Value Boundary Checking (Checks the physical limits so we don't add an invalid temp to the DB) 
        # (Must change threshold after discussing with company what they should be)
        temp = float(payload['temperature_c'])
        # if not (-23.0 <= temp <= -18.0): **Switch to this threshold for actual industry threshold**
        if not (-40.0 <= temp <= 101.0): # Assuming cold chain transportation limits
            print(f"Dropped message: Abnormal temperature detected ({temp}°C). Please check Temperature Sensor.")
            return

        # --- VALIDATION BLOCK ENDS HERE ---

    
        lat = payload.get('lat')
        lon = payload.get('lon')
        battery_pct = payload.get('battery_pct')

        # If it passes validation, proceed with logging and insertion
        # print(f"Received valid data from {payload['device_id']}: {payload['temperature_c']}°C")
        print(f"Received valid data from {payload['device_id']} | Temp: {payload['temperature_c']}°C | Battery: {payload.get('battery_pct')}%")

        # 2. Insert the data safely to prevent SQL injection
        insert_query = """
        INSERT INTO telemetry (device_id, recorded_at, temperature_c, latitude, longitude, battery_pct)
        VALUES (%s, %s, %s, %s, %s, %s);
        """
        db_cursor.execute(insert_query, (
            payload['device_id'],
            datetime.datetime.now(datetime.timezone.utc),
            payload['temperature_c'],
            lat,
            lon,
            battery_pct
        ))
        db_conn.commit()
        
    # If anything goes wrong during the try block (bad JSON, database timeout), it jumps down here
    except json.JSONDecodeError:
        print("Error: Received malformed JSON payload.")
    except Exception as e:
        print(f"Database insertion error: {e}")
        db_conn.rollback() # if a DB error occurs mid-insertion, this completely undoes the partial transaction so you dont end up with corrupted data fragments 

# --- Main Execution loop ---
if __name__ == "__main__":
    if db_conn:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message

        try:
            print("Starting Backend Ingestion Service...")
            client.username_pw_set(MQTT_USER, MQTT_PASS) # Passes secure credentials to the broker 
            client.connect(MQTT_BROKER, MQTT_PORT, 60) 
            client.loop_forever() # Keeps the script running and listening
        except KeyboardInterrupt:
            print("\nShutting down service...") # CTRL C will close the cursor, safely disconnect from PostgreSQL, and drop the MQTT connection before shutting down 
        finally:
            db_cursor.close()
            db_conn.close()
            client.disconnect()