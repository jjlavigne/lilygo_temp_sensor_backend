#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <U8g2lib.h>
#include <Wire.h>
#include "config.h"

// ============================================================================
//  FireBeetle 2 ESP32-E — fleet temperature sensor with local display
//
//  Wiring this expects:
//
//    DS18B20 probe          FireBeetle
//      Yellow (data)   ->   D2 / GPIO 25
//      Red   (VCC)     ->   3V3
//      Blue  (GND)     ->   GND
//      plus a 4.7k resistor between Yellow and 3V3   <-- REQUIRED
//
//    2.42" SSD1309 OLED     FireBeetle
//      VCC             ->   3V3          (3.3V, not 2.3V)
//      GND             ->   GND
//      SDA             ->   SDA / GPIO 21
//      SCL             ->   SCL / GPIO 22
//
//  DEMO_MODE 1 publishes every few seconds and never sleeps — for a live
//  demonstration where the probe moves between ice and hot water.
//  DEMO_MODE 0 reads once an hour and deep sleeps between, for battery use.
// ============================================================================

#define DEMO_MODE        1
#define DEMO_PUBLISH_MS  5000      // matches REAL_DEVICE_INTERVAL_S in the simulator

#define uS_TO_S_FACTOR   1000000ULL
#define TIME_TO_SLEEP    3600      // production sleep, seconds

// --- Pins ---
const int ONE_WIRE_PIN = 25;       // D2 on the FireBeetle silkscreen

// The FireBeetle 2 ESP32-E has an onboard divider for battery voltage. Confirm
// the pin against DFRobot's pinout before trusting the reading; if it is wrong
// you will get a plausible-looking but meaningless percentage, which is worse
// than none. Set to -1 to omit battery from the payload entirely (correct for a
// mains-powered unit, which has no cell to measure).
const int BATTERY_ADC_PIN = -1;

OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature sensors(&oneWire);

// A disconnected DS18B20 returns exactly -127.0. It is not a temperature, it is
// the chip reporting a broken wire. The backend rejects anything outside
// -55..125C and logs it, so a fallen-off probe shows as OFFLINE rather than as a
// bogus reading.
const float DS18B20_DISCONNECTED = -127.0f;

// --- Display geometry -------------------------------------------------------
// Cheap SSD1309 modules differ in how the controller maps its 128 columns onto
// the glass, so anything drawn hard against x=0 or x=127 gets clipped -- in
// practice worse on the left. Nothing is drawn outside these bounds.
//
// IF THE EDGES ARE STILL TRIMMED, raise these two numbers. They are the only
// values to touch, and the layout re-centres itself around them.
#define MARGIN_L   6
#define MARGIN_R   4

#define SCREEN_W   128
#define X_LEFT     MARGIN_L
#define X_RIGHT    (SCREEN_W - MARGIN_R)
#define CONTENT_W  (X_RIGHT - X_LEFT)

// 2.42" SSD1309 over hardware I2C.
//
// These modules ship with one of two column offsets, and U8g2 has a constructor
// for each. Pick the wrong one and the buffer is written a couple of columns out
// of step, so the pixels that fall off one edge WRAP AROUND and appear as a
// stray vertical line at the other -- nothing in this file draws such a line.
//
// If you see one, flip this between 0 and 2. Nothing else needs changing.
#define SSD1309_VARIANT  2

#if SSD1309_VARIANT == 2
U8G2_SSD1309_128X64_NONAME2_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
#else
U8G2_SSD1309_128X64_NONAME0_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
#endif

WiFiClient espClient;
PubSubClient client(espClient);

float lastTempC = NAN;
unsigned long lastPublishMs = 0;
bool lastPublishOk = false;


// ---------------------------------------------------------------------------
//  Display
// ---------------------------------------------------------------------------
void showStatus(const char *line1, const char *line2) {
    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_6x12_tf);
    u8g2.drawStr(X_LEFT, 12, DEVICE_ID);
    u8g2.drawHLine(X_LEFT, 16, CONTENT_W);
    u8g2.setFont(u8g2_font_7x13_tf);
    u8g2.drawStr(X_LEFT, 38, line1);
    if (line2) {
        u8g2.setFont(u8g2_font_6x12_tf);
        u8g2.drawStr(X_LEFT, 56, line2);
    }
    u8g2.sendBuffer();
}

void showReading(float tempC, bool linkUp) {
    char buf[24];
    u8g2.clearBuffer();

    // Device name along the top, so a wall of these is identifiable at a glance.
    u8g2.setFont(u8g2_font_6x12_tf);
    u8g2.drawStr(X_LEFT, 10, DEVICE_ID);
    u8g2.drawHLine(X_LEFT, 13, CONTENT_W);

    if (isnan(tempC) || tempC <= DS18B20_DISCONNECTED) {
        u8g2.setFont(u8g2_font_7x13B_tf);
        u8g2.drawStr(X_LEFT, 38, "PROBE FAULT");
        u8g2.setFont(u8g2_font_6x12_tf);
        u8g2.drawStr(X_LEFT, 56, "check probe wiring");
        u8g2.sendBuffer();
        return;
    }

    // Fahrenheit, because that is what every screen in this system shows.
    // Celsius remains what gets transmitted and stored.
    float tempF = tempC * 9.0f / 5.0f + 32.0f;
    dtostrf(tempF, 4, 1, buf);

    // Measure the number WHILE the large font is selected. Measuring after
    // switching to the small font returns the wrong width, which put the "F"
    // on top of the digits.
    u8g2.setFont(u8g2_font_logisoso24_tn);
    int numW = u8g2.getStrWidth(buf);
    u8g2.setFont(u8g2_font_7x13B_tf);
    int unitW = u8g2.getStrWidth("F");

    // Centre the whole "73.0 F" group inside the safe area rather than pinning
    // it left, so trimming a margin does not push it off-screen.
    int groupX = X_LEFT + (CONTENT_W - (numW + 4 + unitW)) / 2;
    if (groupX < X_LEFT) groupX = X_LEFT;

    u8g2.setFont(u8g2_font_logisoso24_tn);
    u8g2.drawStr(groupX, 44, buf);
    u8g2.setFont(u8g2_font_7x13B_tf);
    u8g2.drawStr(groupX + numW + 4, 44, "F");

#ifdef DISPLAY_TEMP_MIN_F
    // Advisory only. The authoritative limits live in the devices table and are
    // evaluated by Grafana; these exist so somebody walking past can tell at a
    // glance. If the two ever disagree, the database is right.
    // y=61 not 62: at 64px tall, descenders on the bottom row clip at 62.
    u8g2.setFont(u8g2_font_6x12_tf);
    if (tempF > DISPLAY_TEMP_MAX_F) {
        u8g2.drawStr(X_LEFT, 61, "HIGH");
    } else if (tempF < DISPLAY_TEMP_MIN_F) {
        u8g2.drawStr(X_LEFT, 61, "LOW");
    } else {
        u8g2.drawStr(X_LEFT, 61, "OK");
    }
#endif

    // Link state in the corner: a unit that has stopped reporting still shows a
    // temperature, so without this you cannot tell a live reading from a stale one.
    u8g2.setFont(u8g2_font_6x12_tf);
    const char *link = linkUp ? "ONLINE" : "NO LINK";
    u8g2.drawStr(X_RIGHT - u8g2.getStrWidth(link), 61, link);

    u8g2.sendBuffer();
}


// ---------------------------------------------------------------------------
//  Power / failure handling
// ---------------------------------------------------------------------------
void haltOrRetry(const char *reason) {
#if DEMO_MODE
    Serial.print(reason);
    Serial.println(" -- restarting to retry (demo mode, no sleep).");
    showStatus(reason, "restarting...");
    delay(2500);
    ESP.restart();
#else
    Serial.print(reason);
    Serial.println(" -- sleeping to save battery...");
    showStatus(reason, "sleeping 1 hour");
    delay(2000);
    esp_sleep_enable_timer_wakeup(TIME_TO_SLEEP * uS_TO_S_FACTOR);
    esp_deep_sleep_start();
#endif
}


void setup_wifi() {
    WiFi.mode(WIFI_STA);
    Serial.print("\nConnecting to ");
    Serial.println(WIFI_SSID);
    showStatus("Connecting WiFi", WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASS);

    int timeoutCounter = 0;
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
        if (++timeoutCounter >= 30) {
            haltOrRetry("WiFi failed");
        }
    }
    Serial.print("\nWiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    showStatus("WiFi connected", WiFi.localIP().toString().c_str());
    delay(600);
}


void reconnect() {
    int attempts = 0;
    while (!client.connected()) {
        Serial.print("Attempting MQTT connection to ");
        Serial.print(MQTT_BROKER);
        Serial.print(":");
        Serial.println(MQTT_PORT);
        showStatus("Connecting broker", MQTT_BROKER);

        if (client.connect(DEVICE_ID, MQTT_USER, MQTT_PASS)) {
            Serial.println("Connected to MQTT broker.");
            showStatus("Broker connected", NULL);
            delay(400);
            return;
        }

        int state = client.state();
        Serial.print("Failed, client state ");
        Serial.print(state);
        switch (state) {
            case -4: Serial.println(" (TIMEOUT - broker did not respond)"); break;
            case -2: Serial.println(" (CONNECT_FAILED - wrong address, or blocked)"); break;
            case  4: Serial.println(" (BAD_CREDENTIALS)"); break;
            case  5: Serial.println(" (UNAUTHORIZED)"); break;
            default: Serial.println(""); break;
        }

        // Put the raw code on screen -- it is the fastest way to tell a wrong
        // broker address from a wrong password without attaching a laptop.
        char msg[24];
        snprintf(msg, sizeof(msg), "MQTT error %d", state);
        showStatus(msg, "retrying in 5s");
        delay(5000);

        if (++attempts >= 3) {
            haltOrRetry("MQTT failed");
        }
    }
}


int readBatteryPercent() {
    if (BATTERY_ADC_PIN < 0) return -1;
    int raw = analogRead(BATTERY_ADC_PIN);
    float voltage = (raw / 4095.0f) * 3.3f * 2.0f;   // onboard divider
    if (voltage >= 4.2f) return 100;
    if (voltage <= 3.2f) return 0;
    return (int)((voltage - 3.2f) / (4.2f - 3.2f) * 100.0f);
}


void setup() {
    Serial.begin(115200);
    delay(200);

    Wire.begin();          // SDA/SCL as labelled on the FireBeetle
    u8g2.begin();
    u8g2.setContrast(200);
    showStatus("Starting up", DEVICE_ID);

    sensors.begin();

#if DEMO_MODE
    Serial.println(">>> DEMO MODE: publishing every 5s, deep sleep disabled.");
#else
    Serial.println(">>> PRODUCTION MODE: one reading per hour, deep sleep enabled.");
#endif
    Serial.print("MAC: ");
    Serial.println(WiFi.macAddress());

    setup_wifi();
    client.setBufferSize(512);
    client.setServer(MQTT_BROKER, MQTT_PORT);
}


void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();

    // --- read ---
    sensors.requestTemperatures();
    float tempC = sensors.getTempCByIndex(0);
    lastTempC = tempC;

    if (tempC <= DS18B20_DISCONNECTED) {
        Serial.println("WARNING: DS18B20 reads -127 C -- probe disconnected.");
        Serial.println("  Check the 4.7k pull-up between the data line and 3V3.");
        showReading(tempC, client.connected());
        // Still fall through: the backend rejects it and logs the fault, which is
        // how a broken probe surfaces as OFFLINE rather than silently vanishing.
    }

    int battery = readBatteryPercent();

    Serial.print("Temp: ");
    Serial.print(tempC);
    Serial.print(" C / ");
    Serial.print(tempC * 9.0f / 5.0f + 32.0f);
    Serial.print(" F");
    if (battery >= 0) {
        Serial.print(" | Battery: ");
        Serial.print(battery);
        Serial.print("%");
    }
    Serial.println();

    // --- publish ---
    // Key names must match backend/ingestion.py exactly. Temperature is sent in
    // CELSIUS: the database stores Celsius and Grafana converts for display.
    // Sending Fahrenheit here would be stored as though it were Celsius.
    StaticJsonDocument<256> doc;
    doc["device_id"]     = DEVICE_ID;
    doc["temperature_c"] = tempC;
    if (battery >= 0) doc["battery_pct"] = battery;
#ifdef SITE_LAT
    doc["lat"] = SITE_LAT;
    doc["lon"] = SITE_LON;
#endif

    char buffer[256];
    serializeJson(doc, buffer);
    Serial.print("Publishing: ");
    Serial.println(buffer);

    lastPublishOk = client.publish(MQTT_TOPIC, buffer);
    lastPublishMs = millis();

    showReading(tempC, client.connected() && lastPublishOk);

#if DEMO_MODE
    delay(DEMO_PUBLISH_MS);
#else
    delay(1000);                                  // let the radio finish sending
    esp_sleep_enable_timer_wakeup(TIME_TO_SLEEP * uS_TO_S_FACTOR);
    Serial.println("Going to sleep now...");
    u8g2.setPowerSave(1);                         // blank the OLED while asleep
    esp_deep_sleep_start();
#endif
}
