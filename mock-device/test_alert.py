import paho.mqtt.client as mqtt
import json

# --- Configuration ---
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "fleet/telemetry"
MQTT_USER = "fleet_admin"
MQTT_PASS = "Plymouth2026!"

# --- The Fake Emergency Payload ---
payload = {
    "device_id": "TRUCK-TEST-999",
    "temperature_c": 8.5,
    "lat": 47.6062,
    "lon": -122.3321,
    "battery_pct": 100
}

# --- Connection and Publishing ---
client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASS)

print("Connecting to broker...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

print(f"Publishing fake temperature ({payload['temperature_c']}°C)...")
client.publish(MQTT_TOPIC, json.dumps(payload))

print("Message sent! Disconnecting.")
client.disconnect()