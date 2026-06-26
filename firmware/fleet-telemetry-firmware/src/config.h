#ifndef CONFIG_H
#define CONFIG_H

// Network Secrets
const char* WIFI_SSID = "IT_Test";
const char* WIFI_PASS = "Auburn@2230Friday!";

// Infrastructure Settings
const char* MQTT_BROKER = "172.29.96.1"; 
const int MQTT_PORT = 1883;
const char* MQTT_TOPIC = "fleet/telemetry";
const char* DEVICE_ID = "TRUCK-LILYGO-001";

#endif