#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// ===========================
// WiFi
// ===========================
const char *WIFI_SSID = "YOUR_WIFI";
const char *WIFI_PASS = "YOUR_PASSWORD";

// Change this to the IP shown by ESP32 scale Serial Monitor.
const char *SCALE_URL = "http://192.168.1.50/api/food";

const char *AI_SERVER_URL = "http://192.168.0.115:5000/classify";

// ===========================
// AI Thinker ESP32-CAM pins
// ===========================
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27

#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
#define FLASH_LED_PIN 4

struct DetectionResult {
  String food;
  float caloriePerGram;
  float confidence;
  String detectionId;
};

unsigned long lastDetectionMs = 0;
const unsigned long detectionIntervalMs = 12000;
unsigned long lastCommandPollMs = 0;
const unsigned long commandPollIntervalMs = 1000;
bool cameraReady = false;

bool pollCaptureRequest() {
  String url = String(SCALE_URL);
  int endpoint = url.lastIndexOf('/');
  if (endpoint < 0) return false;
  url = url.substring(0, endpoint) + "/camera-command";
  HTTPClient http;
  http.begin(url);
  http.setTimeout(2000);
  int code = http.GET();
  String body = http.getString();
  http.end();
  return code == 200 && body.indexOf("\"capture\":true") >= 0;
}

String urlencode(String value) {
  String encoded = "";
  const char *hex = "0123456789ABCDEF";

  for (uint16_t i = 0; i < value.length(); i++) {
    char c = value[i];
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
      encoded += c;
    } else if (c == ' ') {
      encoded += "%20";
    } else {
      encoded += '%';
      encoded += hex[(c >> 4) & 0x0F];
      encoded += hex[c & 0x0F];
    }
  }

  return encoded;
}

String extractJsonString(const String &body, const String &key) {
  String pattern = "\"" + key + "\"";
  int keyIndex = body.indexOf(pattern);
  if (keyIndex < 0) return "";

  int colonIndex = body.indexOf(':', keyIndex);
  if (colonIndex < 0) return "";

  int firstQuote = body.indexOf('"', colonIndex + 1);
  if (firstQuote < 0) return "";

  String value = "";
  bool escaped = false;
  for (int i = firstQuote + 1; i < body.length(); i++) {
    char c = body[i];
    if (escaped) {
      if (c == 'n') value += '\n';
      else if (c == 'r') value += '\r';
      else if (c == 't') value += '\t';
      else value += c;
      escaped = false;
    } else if (c == '\\') {
      escaped = true;
    } else if (c == '"') {
      return value;
    } else {
      value += c;
    }
  }
  return "";
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

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor != NULL) {
    sensor->set_framesize(sensor, FRAMESIZE_QVGA);
    sensor->set_brightness(sensor, 1);
    sensor->set_saturation(sensor, -1);
  }

  Serial.println("Camera initialized");

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);
  return true;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  unsigned long startMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startMs < 20000) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi failed. Check SSID/password or connect to NutritionScale AP.");
    return;
  }

  Serial.println("WiFi connected");
  Serial.print("ESP32-CAM IP: ");
  Serial.println(WiFi.localIP());
}

bool sendToScale(String food, float caloriePerGram, float confidence, String detectionId) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Cannot send to scale.");
    return false;
  }

  String url = String(SCALE_URL);
  url += "?name=" + urlencode(food);
  url += "&cal=" + String(caloriePerGram, 3);
  url += "&conf=" + String(confidence, 2);
  url += "&detection_id=" + urlencode(detectionId);

  HTTPClient http;
  http.begin(url);
  int httpCode = http.GET();
  String response = http.getString();
  http.end();

  Serial.print("Send to scale: ");
  Serial.print(food);
  Serial.print(" | HTTP ");
  Serial.print(httpCode);
  Serial.print(" | ");
  Serial.println(response);

  return httpCode >= 200 && httpCode < 300;
}

bool requestAiDetection(DetectionResult &result) {
  // Discard one stale frame, then illuminate the food for the actual capture.
  camera_fb_t *staleFrame = esp_camera_fb_get();
  if (staleFrame) {
    esp_camera_fb_return(staleFrame);
  }

  digitalWrite(FLASH_LED_PIN, HIGH);
  delay(180);
  camera_fb_t *fb = esp_camera_fb_get();
  digitalWrite(FLASH_LED_PIN, LOW);

  if (!fb) {
    Serial.println("Camera capture failed");
    return false;
  }

  HTTPClient http;
  http.begin(AI_SERVER_URL);
  http.setTimeout(60000);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device", "esp32-cam");
  int httpCode = http.POST(fb->buf, fb->len);
  String response = http.getString();
  http.end();

  esp_camera_fb_return(fb);

  Serial.print("AI server HTTP ");
  Serial.print(httpCode);
  Serial.print(" | ");
  Serial.println(response);

  if (httpCode < 200 || httpCode >= 300) {
    return false;
  }

  String food = extractJsonString(response, "food");
  if (food.length() == 0) {
    food = extractJsonString(response, "name");
  }

  if (food.length() == 0) {
    Serial.println("AI response missing food name");
    return false;
  }

  result.food = food;
  result.caloriePerGram = extractJsonFloat(response, "calorie_per_gram", 0.0);
  result.caloriePerGram = extractJsonFloat(response, "cal", result.caloriePerGram);
  result.confidence = extractJsonFloat(response, "confidence", 0.0);
  result.confidence = extractJsonFloat(response, "conf", result.confidence);
  result.detectionId = extractJsonString(response, "detection_id");

  return true;
}

void runDetection() {
  DetectionResult result;
  if (requestAiDetection(result)) {
    sendToScale(result.food, result.caloriePerGram, result.confidence, result.detectionId);
  } else {
    Serial.println("AI detection failed");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  delay(500);

  Serial.println();
  Serial.println("ESP32-CAM Food Detection Sender");

  connectWiFi();

  if (!initCamera()) {
    Serial.println("Camera not ready. Restart board after checking wiring/model.");
    return;
  }

  cameraReady = true;
  runDetection();
  lastDetectionMs = millis();
}

void loop() {
  if (!cameraReady) {
    delay(100);
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  unsigned long now = millis();
  bool manualCapture = false;
  if (now - lastCommandPollMs >= commandPollIntervalMs) {
    lastCommandPollMs = now;
    manualCapture = pollCaptureRequest();
  }
  if (manualCapture || now - lastDetectionMs >= detectionIntervalMs) {
    runDetection();
    lastDetectionMs = millis();
  }
}
