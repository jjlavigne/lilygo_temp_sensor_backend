#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
    Serial.print("\nConnecting to ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected. IP: ");
    Serial.println(WiFi.localIP());
}

void reconnect() {
    while (!client.connected()) {
        Serial.print("Attempting MQTT connection...");
        if (client.connect(DEVICE_ID)) {
            Serial.println("connected");
        } else {
            Serial.print("failed, rc=");
            Serial.print(client.state());
            Serial.println(" try again in 5s");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    setup_wifi();
    client.setServer(MQTT_BROKER, MQTT_PORT);
}

void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    // Generate Mock Telemetry Data
    JsonDocument doc;
    doc["device_id"] = DEVICE_ID;
    doc["temperature_c"] = random(200, 550) / 100.0; // Random temp between 2.00 and 5.50 C
    doc["lat"] = 47.6062; 
    doc["lon"] = -122.3321;
    doc["battery_pct"] = 100;

    char buffer[256];
    serializeJson(doc, buffer);

    Serial.print("Publishing: ");
    Serial.println(buffer);
    client.publish(MQTT_TOPIC, buffer);

    delay(10000); // Wait 10 seconds before sending the next reading
}