#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Ping.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "config.h"

// ============================================================================
//  DEMO MODE
//
//  1 = publish every few seconds, never sleep.  Use this for a live demo where
//      the probe goes into ice water and hot water and the dashboard has to
//      react while you are still holding it.
//  0 = read once, publish, deep sleep for an hour.  Production behaviour.
//
//  This is the ONLY line to change between the two. Failure handling switches
//  with it as well: in demo mode a WiFi or MQTT failure retries immediately
//  instead of sleeping for an hour, because a device that vanishes for an hour
//  mid-presentation is unrecoverable.
//
//  Keep DEMO_PUBLISH_MS matched to REAL_DEVICE_INTERVAL_S in
//  mock-device/fleet_simulator.py -- that value drives the "sensor offline"
//  alert threshold for this board.
// ============================================================================
#define DEMO_MODE        1
#define DEMO_PUBLISH_MS  5000     // 5s, matches REAL_DEVICE_INTERVAL_S

#define uS_TO_S_FACTOR   1000000ULL
#define TIME_TO_SLEEP    3600     // production sleep, seconds

// --- Sensor Configuration ---
// GPIO 25 to avoid the cellular modem power key
const int oneWireBus = 25;
OneWire oneWire(oneWireBus);
DallasTemperature sensors(&oneWire);

const int batPin = 35;

// A disconnected DS18B20 returns exactly -127.0. It is not a temperature, it is
// the chip reporting a broken wire. The backend rejects anything below -55 C and
// logs it to rejected_readings, so the unit surfaces as OFFLINE rather than as a
// bogus reading. Checking here too gives you the reason on the serial monitor.
const float DS18B20_DISCONNECTED = -127.0f;

WiFiClient espClient;
PubSubClient client(espClient);

// host computer ip address
IPAddress VM_ip(10, 80, 149, 11);
IPAddress myPhone_ip(10, 80, 10, 218);


// Sleep in production, retry in demo. Called from every unrecoverable path.
void haltOrRetry(const char *reason) {
#if DEMO_MODE
    Serial.print(reason);
    Serial.println(" -- restarting to retry (demo mode, no sleep).");
    delay(2000);
    ESP.restart();
#else
    Serial.print(reason);
    Serial.println(" -- sleeping to save battery...");
    esp_sleep_enable_timer_wakeup(TIME_TO_SLEEP * uS_TO_S_FACTOR);
    esp_deep_sleep_start();
#endif
}


void setup_wifi() {
    int numberOfNetworks = WiFi.scanNetworks();

    Serial.print("Number of networks found: ");
    Serial.println(numberOfNetworks);

    for (int i = 0; i < numberOfNetworks; i++) {
        Serial.print("Network name: ");
        Serial.print(WiFi.SSID(i));
        Serial.print(" | Signal strength: ");
        Serial.print(WiFi.RSSI(i));
        Serial.print(" dBm");
        Serial.print(" | Encryption: ");
        Serial.println((WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? "Open" : "Protected");
        delay(10);
    }

    Serial.print("\nConnecting to ");
    //Serial.println(HOMEWIFI_SSID);
    //WiFi.begin(HOMEWIFI_SSID, HOMEWIFI_PASS);
    //Serial.println(WIFI_SSID);
    //WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.println(FRAME_SSID);
    WiFi.begin(FRAME_SSID, FRAME_PASS);
    //Serial.println(HOTSPOT_SSID);
    //WiFi.begin(HOTSPOT_SSID, HOTSPOT_PASS);

    int timeoutCounter = 0;
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        timeoutCounter++;

        if (timeoutCounter >= 30) {
            haltOrRetry("\nWiFi connection failed!");
        }
    }
    Serial.println("\nWiFi connected. IP: ");
    Serial.println(WiFi.localIP());

    // Reachability check before we bother the MQTT stack. If this fails, the
    // broker IP in config.h is almost certainly stale -- it changes whenever the
    // VM moves between networks (home vs office).
    Serial.print("Pinging vm computer at ");
    Serial.println(VM_ip);

    if (Ping.ping(VM_ip)) {
        Serial.println("Ping successful! vm is reachable.");
    } else {
        Serial.println("Ping failed! vm is unreachable.");
        Serial.println("  -> Check MQTT_BROKER in config.h matches the VM's IP on THIS network.");
    }
}


void reconnect() {
    int mqttTimeout = 0;
    while (!client.connected()) {
        Serial.print("Attempting MQTT connection to ");
        Serial.print(MQTT_BROKER);
        Serial.print(" on port ");
        Serial.println(MQTT_PORT);

        if (client.connect(DEVICE_ID, MQTT_USER, MQTT_PASS)) {
            Serial.println("Success! Connected to MQTT Broker.");
        } else {
            Serial.print("Connection failed. Client state code: ");
            int state = client.state();
            Serial.print(state);

            switch (state) {
                case -4: Serial.println(" (MQTT_CONNECTION_TIMEOUT - Server didn't respond in time)"); break;
                case -3: Serial.println(" (MQTT_CONNECTION_LOST - Network broke mid-connection)"); break;
                case -2: Serial.println(" (MQTT_CONNECT_FAILED - The server explicitly refused or network path is blocked)"); break;
                case -1: Serial.println(" (MQTT_DISCONNECTED)"); break;
                case 1:  Serial.println(" (MQTT_CONNECT_BAD_PROTOCOL)"); break;
                case 2:  Serial.println(" (MQTT_CONNECT_BAD_CLIENT_ID)"); break;
                case 3:  Serial.println(" (MQTT_CONNECT_UNAVAILABLE - Broker is busy or initializing)"); break;
                case 4:  Serial.println(" (MQTT_CONNECT_BAD_CREDENTIALS)"); break;
                case 5:  Serial.println(" (MQTT_CONNECT_UNAUTHORIZED)"); break;
                default: Serial.println(" (Unknown error)"); break;
            }
            Serial.println("Retrying in 5 seconds...\n");
            delay(5000);

            mqttTimeout++;
            if (mqttTimeout >= 3) {
                haltOrRetry("\nMQTT failed!");
            }
        }
    }
}


void setup() {
    Serial.begin(115200);

    // Force the cellular modem OFF to save power. The board runs on WiFi.
    const int MODEM_PWR_PIN = 4;
    pinMode(MODEM_PWR_PIN, OUTPUT);
    digitalWrite(MODEM_PWR_PIN, LOW);

    sensors.begin();

    WiFi.mode(WIFI_STA);
    Serial.print("Device MAC Address: ");
    Serial.println(WiFi.macAddress());

#if DEMO_MODE
    Serial.println(">>> DEMO MODE: publishing every 5s, deep sleep disabled.");
#else
    Serial.println(">>> PRODUCTION MODE: one reading per hour, deep sleep enabled.");
#endif

    setup_wifi();
    client.setBufferSize(512);
    client.setServer(MQTT_BROKER, MQTT_PORT);
}


void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    // --- 1. Live temperature from the DS18B20 ---
    sensors.requestTemperatures();
    float liveTempC = sensors.getTempCByIndex(0);

    if (liveTempC <= DS18B20_DISCONNECTED) {
        Serial.println("WARNING: DS18B20 reads -127 C -- probe disconnected or wiring fault.");
        Serial.println("  The backend will reject this reading and log it to rejected_readings.");
        Serial.println("  This unit will show as OFFLINE on the dashboard, not as a bad temperature.");
    }

    // --- 2. Battery voltage and percentage ---
    int rawValue = analogRead(batPin);
    float voltage = (rawValue / 4095.0) * 3.3 * 2.0;

    int batteryPct = 0;
    if (voltage >= 4.2) {
        batteryPct = 100;
    } else if (voltage <= 3.2) {
        batteryPct = 0;
    } else {
        batteryPct = (int)((voltage - 3.2) / (4.2 - 3.2) * 100.0);
    }

    Serial.print("Live Battery Voltage: ");
    Serial.print(voltage);
    Serial.print("V | Charge: ");
    Serial.print(batteryPct);
    Serial.print("% | Temp: ");
    Serial.print(liveTempC);
    Serial.print("C / ");
    Serial.print(liveTempC * 9.0 / 5.0 + 32.0);   // the dashboard shows Fahrenheit
    Serial.println("F");

    // --- 3. Build the payload ---
    // Key names must match backend/ingestion.py exactly. Temperature is sent in
    // CELSIUS: the database stores Celsius and Grafana converts for display.
    // Do not send Fahrenheit here -- it would be stored as if it were Celsius.
    JsonDocument doc;
    doc["device_id"]     = DEVICE_ID;
    doc["temperature_c"] = liveTempC;
    doc["battery_pct"]   = batteryPct;

    // Site coordinates so this board appears on the fleet map alongside
    // Plymouth's other Auburn WA units. These are the FACILITY location, not a
    // GPS fix -- the T-SIM7000G's GNSS sits behind the cellular modem, which is
    // powered down above to save battery.
    doc["lat"] = 47.3073;   // Auburn WA
    doc["lon"] = -122.2285;

    char buffer[256];
    serializeJson(doc, buffer);

    Serial.print("Publishing: ");
    Serial.println(buffer);
    client.publish(MQTT_TOPIC, buffer);

#if DEMO_MODE
    // Stay awake so the probe can be moved between ice and hot water and the
    // dashboard follows within seconds.
    delay(DEMO_PUBLISH_MS);
#else
    // Let the WiFi radio finish transmitting before the power drops.
    delay(1000);
    esp_sleep_enable_timer_wakeup(TIME_TO_SLEEP * uS_TO_S_FACTOR);
    Serial.println("Going to sleep now...");
    esp_deep_sleep_start();
#endif
}
