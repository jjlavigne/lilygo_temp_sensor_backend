import json
import time
import random
import paho.mqtt.client as mqtt
from datetime import datetime, timezone

# --- Configuration ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "fleet/telemetry"
DEVICE_ID = "MOCK-TRUCK-001"

def on_connect(client, userdata, flags, rc):
    """Callback for when the device connects to the broker."""
    if rc == 0:
        print(f"Connected to MQTT Broker! Ready to publish as {DEVICE_ID}")
    else:
        print(f"Failed to connect to broker, return code {rc}")

def generate_mock_data():
    """Generates a realistic fake telemetry payload."""
    return {
        "device_id": DEVICE_ID,
        # Generate a standard ISO-8601 timestamp for the database
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Produce truck target temperature range (2 to 6 degrees Celsius)
        # normal temp alert
        "temperature_c": round(random.uniform(2.0, 6.0), 2),
        # high temp alert
        #"temperature_c": round(random.uniform(8.5, 10.0), 2),
        # GPS Coordinates (roughly Seattle area)
        "lat": round(random.uniform(47.5, 47.7), 6),
        "lon": round(random.uniform(-122.4, -122.2), 6),
        "battery_pct": random.randint(85, 100)
    }

# --- Main Execution ---
if __name__ == "__main__":
    client = mqtt.Client()
    client.on_connect = on_connect

    print(f"Starting Mock Edge Device: {DEVICE_ID}...")
    try:
        # Connect to the local broker
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start() # Starts a background thread to handle network traffic

        # Infinite loop to send data every 5 seconds
        while True:
            payload = generate_mock_data()
            json_payload = json.dumps(payload)
            
            # Publish the message to the broker
            client.publish(MQTT_TOPIC, json_payload)
            print(f"Published: {payload['temperature_c']}°C at {payload['timestamp']}")
            
            time.sleep(5) # Wait 5 seconds before generating the next reading
            
    except KeyboardInterrupt:
        print("\nShutting down mock device...")
    finally:
        client.loop_stop()
        client.disconnect()