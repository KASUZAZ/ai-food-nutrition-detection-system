#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <LiquidCrystal_I2C.h>
#include "HX711.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

#define ENABLE_BLYNK 0

#if ENABLE_BLYNK
#define BLYNK_TEMPLATE_ID "YOUR_TEMPLATE_ID"
#define BLYNK_TEMPLATE_NAME "Food Nutrition System"
#define BLYNK_AUTH_TOKEN "YOUR_BLYNK_TOKEN"
#include <BlynkSimpleEsp32.h>
BlynkTimer blynkTimer;
#endif

// ===========================
// WiFi
// ===========================
const char *WIFI_SSID = NUTRITION_WIFI_SSID;
const char *WIFI_PASS = NUTRITION_WIFI_PASS;

const char *AP_SSID = "NutritionScale";
const char *AP_PASS = "12345678";

// ===========================
// LCD
// ===========================
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ===========================
// HX711
// ===========================
#define DT 19
#define SCK 18
HX711 scale;

float calibrationFactor = 183.37;

// ===========================
// Weight lock settings
// ===========================
float weight = 0.0;
float lastWeight = 0.0;
float lockedWeight = 0.0;

int stableCount = 0;
bool isLocked = false;

const float stableThreshold = 0.5;
const int stableRequired = 5;
const float unlockThreshold = 5.0;

// ===========================
// Nutrition data
// ===========================
String foodName = "Waiting food";
float caloriePerGram = 0.0;
float confidence = 0.0;
unsigned long lastFoodUpdateMs = 0;

// ===========================
// Timing
// ===========================
unsigned long lastReadMs = 0;
unsigned long lastLcdMs = 0;
unsigned long lastSerialMs = 0;

const unsigned long readIntervalMs = 200;
const unsigned long lcdIntervalMs = 300;
const unsigned long serialIntervalMs = 1000;

WebServer server(80);
bool captureRequested = false;
unsigned long lastCameraPollMs = 0;
bool cameraSeen = false;

IPAddress currentIp() {
  if (WiFi.getMode() == WIFI_AP) {
    return WiFi.softAPIP();
  }

  return WiFi.localIP();
}

String fit16(String text) {
  if (text.length() > 16) {
    return text.substring(0, 16);
  }

  while (text.length() < 16) {
    text += " ";
  }

  return text;
}

void lcdLine(uint8_t row, String text) {
  lcd.setCursor(0, row);
  lcd.print(fit16(text));
}

String urlDecode(String value) {
  value.replace("+", " ");

  String decoded = "";
  char temp[] = "00";

  for (uint16_t i = 0; i < value.length(); i++) {
    char c = value[i];
    if (c == '%' && i + 2 < value.length()) {
      temp[0] = value[i + 1];
      temp[1] = value[i + 2];
      decoded += char(strtol(temp, NULL, 16));
      i += 2;
    } else {
      decoded += c;
    }
  }

  return decoded;
}

String extractJsonString(const String &body, const String &key) {
  String pattern = "\"" + key + "\"";
  int keyIndex = body.indexOf(pattern);
  if (keyIndex < 0) return "";

  int colonIndex = body.indexOf(':', keyIndex);
  if (colonIndex < 0) return "";

  int firstQuote = body.indexOf('"', colonIndex + 1);
  if (firstQuote < 0) return "";

  int secondQuote = body.indexOf('"', firstQuote + 1);
  if (secondQuote < 0) return "";

  return body.substring(firstQuote + 1, secondQuote);
}

float extractJsonFloat(const String &body, const String &key, float fallback) {
  String pattern = "\"" + key + "\"";
  int keyIndex = body.indexOf(pattern);
  if (keyIndex < 0) return fallback;

  int colonIndex = body.indexOf(':', keyIndex);
  if (colonIndex < 0) return fallback;

  int start = colonIndex + 1;
  while (start < body.length() && body[start] == ' ') {
    start++;
  }

  int end = start;
  while (end < body.length()) {
    char c = body[end];
    if (!isDigit(c) && c != '.' && c != '-') break;
    end++;
  }

  if (end == start) return fallback;
  return body.substring(start, end).toFloat();
}

String jsonEscape(String value) {
  value.replace("\\", "\\\\");
  value.replace("\"", "\\\"");
  return value;
}

float activeWeight() {
  return isLocked ? lockedWeight : weight;
}

float totalCalories() {
  if (caloriePerGram <= 0.0) return 0.0;
  return activeWeight() * caloriePerGram;
}

void setFood(String name, float cal, float conf) {
  name.trim();
  if (name.length() == 0) {
    name = "Unknown food";
  }

  if (cal < 0.0) cal = 0.0;
  if (conf < 0.0) conf = 0.0;
  if (conf > 1.0) conf = 1.0;

  foodName = name;
  caloriePerGram = cal;
  confidence = conf;
  lastFoodUpdateMs = millis();

  Serial.println("Food updated:");
  Serial.print("  Name: ");
  Serial.println(foodName);
  Serial.print("  Cal/g: ");
  Serial.println(caloriePerGram, 3);
  Serial.print("  Confidence: ");
  Serial.println(confidence, 2);
}

void connectWiFi() {
  lcdLine(0, "Connecting WiFi");
  lcdLine(1, WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < 15000) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Scale IP: ");
    Serial.println(WiFi.localIP());
    lcdLine(0, "WiFi connected");
    lcdLine(1, WiFi.localIP().toString());
    delay(1500);
    return;
  }

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);

  Serial.println("WiFi failed. AP mode started.");
  Serial.print("AP SSID: ");
  Serial.println(AP_SSID);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());

  lcdLine(0, "AP mode active");
  lcdLine(1, WiFi.softAPIP().toString());
  delay(2000);
}

void handleRoot() {
  String html = "";
  html += "<!doctype html><html><head>";
  html += "<meta name='viewport' content='width=device-width,initial-scale=1'>";
  html += "<title>Food Nutrition System</title>";
  html += "<style>";
  html += "body{font-family:Arial;margin:24px;background:#f6f7f9;color:#111}";
  html += ".box{max-width:520px;background:white;border:1px solid #ddd;padding:18px;border-radius:8px}";
  html += "h1{font-size:22px;margin:0 0 12px}";
  html += "p{font-size:16px;margin:8px 0}";
  html += "b{display:inline-block;width:130px}";
  html += ".actions{display:flex;gap:12px;margin-top:18px}button{padding:12px 24px;border:0;border-radius:6px;background:#087a5a;color:white;font-size:16px;cursor:pointer}button:disabled{opacity:.5}#message{min-height:24px}";
  html += "</style></head><body><div class='box'>";
  html += "<h1>Food Nutrition System</h1>";
  html += "<p><b>Food</b>" + foodName + "</p>";
  html += "<p><b>Weight</b>" + String(activeWeight(), 1) + " g</p>";
  html += "<p><b>Calories</b>" + String(totalCalories(), 0) + " kcal</p>";
  html += "<p><b>Cal/g</b>" + String(caloriePerGram, 2) + "</p>";
  html += "<p><b>Confidence</b>" + String(confidence * 100.0, 0) + "%</p>";
  html += "<p><b>Status</b>" + String(isLocked ? "LOCKED" : "READING") + "</p>";
  html += "<div class='actions'><button onclick=\"act('tare')\">Tare</button><button onclick=\"act('capture')\">Capture</button></div>";
  html += "<p id='message' role='status' aria-live='polite'></p>";
  html += "<script>let busy=false;async function act(action){busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);const m=document.getElementById('message');m.textContent=action==='tare'?'Taring...':'Requesting capture...';try{const r=await fetch('/api/'+action,{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');m.textContent=d.message;}catch(e){m.textContent=e.message;}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}}async function refresh(){if(busy)return;try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)return;const d=await r.json();const values=[d.food,Number(d.weight_g).toFixed(1)+' g',Number(d.calories).toFixed(0)+' kcal',Number(d.calorie_per_gram).toFixed(2),Math.round(d.confidence*100)+'%',d.locked?'LOCKED':'READING'];document.querySelectorAll('.box>p b').forEach((b,i)=>b.parentNode.lastChild.textContent=values[i]);}catch(e){document.getElementById('message').textContent='Scale connection lost. Retrying...';}}setInterval(refresh,3000);</script>";
  html += "</div></body></html>";

  server.send(200, "text/html", html);
}

void handleFood() {
  String incomingName = "";
  float incomingCal = caloriePerGram;
  float incomingConf = confidence;

  if (server.hasArg("name")) {
    incomingName = urlDecode(server.arg("name"));
  }

  if (server.hasArg("food")) {
    incomingName = urlDecode(server.arg("food"));
  }

  if (server.hasArg("cal")) {
    incomingCal = server.arg("cal").toFloat();
  }

  if (server.hasArg("calorie_per_gram")) {
    incomingCal = server.arg("calorie_per_gram").toFloat();
  }

  if (server.hasArg("conf")) {
    incomingConf = server.arg("conf").toFloat();
  }

  if (server.hasArg("confidence")) {
    incomingConf = server.arg("confidence").toFloat();
  }

  if (server.method() == HTTP_POST && server.hasArg("plain")) {
    String body = server.arg("plain");
    String jsonName = extractJsonString(body, "food");
    if (jsonName.length() == 0) {
      jsonName = extractJsonString(body, "name");
    }

    if (jsonName.length() > 0) {
      incomingName = jsonName;
    }

    incomingCal = extractJsonFloat(body, "calorie_per_gram", incomingCal);
    incomingCal = extractJsonFloat(body, "cal", incomingCal);
    incomingConf = extractJsonFloat(body, "confidence", incomingConf);
    incomingConf = extractJsonFloat(body, "conf", incomingConf);
  }

  if (incomingName.length() == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"missing food name\"}");
    return;
  }

  setFood(incomingName, incomingCal, incomingConf);
  server.send(200, "application/json", "{\"ok\":true}");
}

void handleStatus() {
  String json = "{";
  json += "\"food\":\"" + jsonEscape(foodName) + "\",";
  json += "\"calorie_per_gram\":" + String(caloriePerGram, 3) + ",";
  json += "\"weight_g\":" + String(activeWeight(), 1) + ",";
  json += "\"calories\":" + String(totalCalories(), 1) + ",";
  json += "\"locked\":" + String(isLocked ? "true" : "false") + ",";
  json += "\"confidence\":" + String(confidence, 2);
  json += "}";

  server.send(200, "application/json", json);
}

void handleTare() {
  if (!scale.wait_ready_timeout(1000)) {
    server.send(503, "application/json", "{\"ok\":false,\"error\":\"HX711 not ready. Check wiring.\"}");
    return;
  }
  scale.tare();
  weight = 0.0;
  lastWeight = 0.0;
  lockedWeight = 0.0;
  stableCount = 0;
  isLocked = false;

  server.send(200, "application/json", "{\"ok\":true,\"message\":\"tare complete\"}");
}

void handleCapture() {
  if (!cameraSeen || millis() - lastCameraPollMs > 15000) {
    server.send(503, "application/json", "{\"ok\":false,\"error\":\"Camera unavailable or busy. Try again shortly.\"}");
    return;
  }
  captureRequested = true;
  server.send(202, "application/json", "{\"ok\":true,\"message\":\"Capture queued. Wait for the AI result.\"}");
}

void handleCameraCommand() {
  cameraSeen = true;
  lastCameraPollMs = millis();
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", captureRequested ? "{\"capture\":true}" : "{\"capture\":false}");
  captureRequested = false;
}

void setupServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/food", HTTP_ANY, handleFood);
  server.on("/api/status", HTTP_GET, handleStatus);
  server.on("/api/tare", HTTP_GET, handleTare);
  server.on("/api/tare", HTTP_POST, handleTare);
  server.on("/api/capture", HTTP_POST, handleCapture);
  server.on("/api/camera-command", HTTP_GET, handleCameraCommand);

  server.begin();
  Serial.println("HTTP server started");
}

void readWeight() {
  if (!scale.is_ready()) {
    Serial.println("HX711 not ready");
    lcdLine(0, "HX711 ERROR");
    lcdLine(1, "Check wiring");
    return;
  }

  float rawWeight = scale.get_units(5);
  if (rawWeight < 1.0) rawWeight = 0.0;

  weight = rawWeight;

  if (!isLocked) {
    if (fabs(weight - lastWeight) < stableThreshold) {
      stableCount++;
    } else {
      stableCount = 0;
    }

    if (stableCount >= stableRequired) {
      isLocked = true;
      lockedWeight = weight;
    }
  } else {
    if (fabs(weight - lockedWeight) > unlockThreshold) {
      isLocked = false;
      stableCount = 0;
    }
  }

  lastWeight = isLocked ? lockedWeight : weight;
}

void updateLcd() {
  if (caloriePerGram <= 0.0) {
    lcdLine(0, "Waiting food");
    lcdLine(1, String(isLocked ? "LOCK " : "READ ") + String(activeWeight(), 1) + "g");
    return;
  }

  String shortFood = foodName;
  if (shortFood.length() > 9) {
    shortFood = shortFood.substring(0, 9);
  }

  String line0 = shortFood + " " + String(activeWeight(), 0) + "g";
  String line1 = String(totalCalories(), 0) + " kcal ";
  line1 += isLocked ? "LOCK" : "READ";

  lcdLine(0, line0);
  lcdLine(1, line1);
}

void printSerialStatus() {
  Serial.print("Food: ");
  Serial.print(foodName);
  Serial.print(" | Weight: ");
  Serial.print(activeWeight(), 1);
  Serial.print(" g | Calories: ");
  Serial.print(totalCalories(), 0);
  Serial.print(" kcal | Cal/g: ");
  Serial.print(caloriePerGram, 2);
  Serial.print(" | ");
  Serial.println(isLocked ? "LOCKED" : "READING");
}

#if ENABLE_BLYNK
void pushToBlynk() {
  Blynk.virtualWrite(V0, activeWeight());
  Blynk.virtualWrite(V1, totalCalories());
  Blynk.virtualWrite(V2, foodName);
  Blynk.virtualWrite(V3, isLocked ? 1 : 0);
  Blynk.virtualWrite(V4, confidence);
}
#endif

void setup() {
  Serial.begin(115200);
  delay(300);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcdLine(0, "Nutrition AI");
  lcdLine(1, "Starting...");

  scale.begin(DT, SCK);
  scale.set_scale(calibrationFactor);
  scale.tare();

  delay(1000);
  connectWiFi();
  setupServer();

#if ENABLE_BLYNK
  if (WiFi.status() == WL_CONNECTED) {
    Blynk.config(BLYNK_AUTH_TOKEN);
    Blynk.connect(5000);
    blynkTimer.setInterval(2000L, pushToBlynk);
  }
#endif

  lcd.clear();
  lcdLine(0, "System ready");
  lcdLine(1, currentIp().toString());
  delay(1500);
}

void loop() {
  server.handleClient();

#if ENABLE_BLYNK
  if (WiFi.status() == WL_CONNECTED) {
    Blynk.run();
    blynkTimer.run();
  }
#endif

  unsigned long now = millis();

  if (now - lastReadMs >= readIntervalMs) {
    lastReadMs = now;
    readWeight();
  }

  if (now - lastLcdMs >= lcdIntervalMs) {
    lastLcdMs = now;
    updateLcd();
  }

  if (now - lastSerialMs >= serialIntervalMs) {
    lastSerialMs = now;
    printSerialStatus();
  }
}
