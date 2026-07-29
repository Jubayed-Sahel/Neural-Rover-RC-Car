# ESP32 Neural Rover Master Documentation

This documentation is generated from the supplied project files and previous conversation.

## Project Files
- `New folder/WhatsApp Image 2026-07-18 at 12.04.48 AM.jpeg`
- `New folder/ESP32_CAM/ESP32_CAM_GOOD_BACKUP.txt`
- `New folder/ESP32_CAM/ESP32_CAM.ino`
- `New folder/ESP32_Controller/ESP32_Controller.ino`

## System Overview
- ESP32 Controller handles WiFi, motors, web UI, servos and UART.
- ESP32-CAM handles camera streaming and flash control.
- Communication reserved over UART2.

## Controller Pin Mapping

| Function | GPIO |
|---|---:|
| Left ENA |25|
| Left IN1 |26|
| Left IN2 |27|
| Left IN3 |14|
| Left IN4 |12|
| Left ENB |33|
| Right ENA |32|
| Right IN1 |23|
| Right IN2 |22|
| Right IN3 |21|
| Right IN4 |19|
| Right ENB |18|
| Pan Servo |13|
| Tilt Servo |4|
| UART RX2 |16|
| UART TX2 |17|

## ESP32-CAM Pins

| Signal | GPIO |
|---|---:|
|PWDN|32|
|RESET|-1|
|XCLK|0|
|SIOD|26|
|SIOC|27|
|Y9|35|
|Y8|34|
|Y7|39|
|Y6|36|
|Y5|21|
|Y4|19|
|Y3|18|
|Y2|5|
|VSYNC|25|
|HREF|23|
|PCLK|22|
|FLASH LED|4|

## Wiring Diagram

```text
Battery (3S)
 ├──> L298N Left VIN
 ├──> L298N Right VIN
 └──> LM2596
        ├──> ESP32 VIN
        ├──> ESP32-CAM 5V
        └──> Servo VCC

Common Ground:
Battery-, ESP32 GND, ESP32-CAM GND,
LM2596 GND, Both L298N GND
```

```text
ESP32 GPIO17 --------> ESP32-CAM U0R
ESP32 GPIO16 <-------- ESP32-CAM U0T
```

## Code Summary

### ESP32_Controller
- WiFi connection
- WebServer on port 80
- Responsive HTML interface
- PWM motor control
- Servo control
- UART2 initialized
- Commands:
  - forward
  - backward
  - left
  - right
  - stop

### ESP32-CAM
- Camera server
- Stream endpoint: /stream (port 81)
- Flash endpoint: /flash
- mDNS support
- JPEG streaming

## WiFi
SSID: froggy
Password: Passwordki

## Upload History
- Missing CP2102 driver fixed.
- Silicon Labs Universal Driver installed.
- Upload successful.

## Source Files


### ESP32_CAM_GOOD_BACKUP.txt (6147 bytes)
```cpp
﻿#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>
#include <ESPmDNS.h>
#include <esp_arduino_version.h>

const char* WIFI_SSID = "froggy";
const char* WIFI_PASSWORD = "Passwordki";

#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22
#define FLASH_LED_GPIO 4

httpd_handle_t streamServer = nullptr;
httpd_handle_t controlServer = nullptr;
int flashValue = 0;

#if ESP_ARDUINO_VERSION_MAJOR < 3
constexpr uint8_t FLASH_LED_CHANNEL = 7;
void setupFlashLed() {
  ledcSetup(FLASH_LED_CHANNEL, 5000, 8);
  ledcAttachPin(FLASH_LED_GPIO, FLASH_LED_CHANNEL);
  ledcWrite(FLASH_LED_CHANNEL, 0);
}
void writeFlashLed(int value) {
  ledcWrite(FLASH_LED_CHANNEL, value);
}
#else
void setupFlashLed() {
  ledcAttach(FLASH_LED_GPIO, 5000, 8);
  ledcWrite(FLASH_LED_GPIO, 0);
}
void writeFlashLed(int value) {
  ledcWrite(FLASH_LED_GPIO, value);
}
#endif

static esp_err_t flashHandler(httpd_req_t* request) {
  char query[64];
  char valueText[12];

  if (httpd_req_get_url_query_str(request, query, sizeof(query)) == ESP_OK &&
      httpd_query_key_value(query, "value", valueText, sizeof(valueText)) == ESP_OK) {
    flashValue = constrain(atoi(valueText), 0, 255);
    writeFlashLed(flashValue);
  }

  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_type(request, "application/json");
  String response = "{\"flash\":" + String(flashValue) + "}";
  return httpd_resp_send(request, response.c_str(), response.length());
}

static esp_err_t streamHandler(httpd_req_t* request) {
  static const char* CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
  static const char* BOUNDARY = "\r\n--frame\r\n";
  static const char* PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

  esp_err_t result = httpd_resp_set_type(request, CONTENT_TYPE);
  if (result != ESP_OK) return result;
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");

  char header[64];
  while (true) {
    camera_fb_t* frame = esp_camera_fb_get();
    if (!frame) return ESP_FAIL;

    uint8_t* jpegBuffer = frame->buf;
    size_t jpegLength = frame->len;
    bool converted = false;

    if (frame->format != PIXFORMAT_JPEG) {
      converted = frame2jpg(frame, 80, &jpegBuffer, &jpegLength);
      if (!converted) {
        esp_camera_fb_return(frame);
        return ESP_FAIL;
      }
    }

    result = httpd_resp_send_chunk(request, BOUNDARY, strlen(BOUNDARY));
    if (result == ESP_OK) {
      const size_t headerLength = snprintf(header, sizeof(header), PART, jpegLength);
      result = httpd_resp_send_chunk(request, header, headerLength);
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request,
                                     reinterpret_cast<const char*>(jpegBuffer),
                                     jpegLength);
    }

    if (converted) free(jpegBuffer);
    esp_camera_fb_return(frame);
    if (result != ESP_OK) break;
  }
  return result;
}

void startStreamServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port += 1;
  config.max_uri_handlers = 4;

  httpd_uri_t streamUri = {
    .
```

### ESP32_CAM.ino (6186 bytes)
```cpp
﻿#include "esp_camera.h"
#include "esp_http_server.h"
#include <WiFi.h>
#include <ESPmDNS.h>
#include <esp_arduino_version.h>

const char* WIFI_SSID = "froggy";
const char* WIFI_PASSWORD = "Passwordki";

// AI Thinker ESP32-CAM camera pins
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22
#define FLASH_LED_GPIO 4

httpd_handle_t streamServer = nullptr;
httpd_handle_t controlServer = nullptr;
int flashValue = 0;

#if ESP_ARDUINO_VERSION_MAJOR < 3
constexpr uint8_t FLASH_LED_CHANNEL = 7;

void setupFlashLed() {
  ledcSetup(FLASH_LED_CHANNEL, 5000, 8);
  ledcAttachPin(FLASH_LED_GPIO, FLASH_LED_CHANNEL);
  ledcWrite(FLASH_LED_CHANNEL, 0);
}

void writeFlashLed(int value) {
  ledcWrite(FLASH_LED_CHANNEL, value);
}
#else
void setupFlashLed() {
  ledcAttach(FLASH_LED_GPIO, 5000, 8);
  ledcWrite(FLASH_LED_GPIO, 0);
}

void writeFlashLed(int value) {
  ledcWrite(FLASH_LED_GPIO, value);
}
#endif

static esp_err_t flashHandler(httpd_req_t* request) {
  char query[64];
  char valueText[12];

  if (httpd_req_get_url_query_str(request, query, sizeof(query)) == ESP_OK &&
      httpd_query_key_value(query, "value", valueText, sizeof(valueText)) == ESP_OK) {
    flashValue = constrain(atoi(valueText), 0, 255);
    writeFlashLed(flashValue);
  }

  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_type(request, "application/json");
  String response = "{\"flash\":" + String(flashValue) + "}";
  return httpd_resp_send(request, response.c_str(), response.length());
}

static esp_err_t streamHandler(httpd_req_t* request) {
  static const char* CONTENT_TYPE = "multipart/x-mixed-replace;boundary=frame";
  static const char* BOUNDARY = "\r\n--frame\r\n";
  static const char* PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

  esp_err_t result = httpd_resp_set_type(request, CONTENT_TYPE);
  if (result != ESP_OK) return result;
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");

  char header[64];
  while (true) {
    camera_fb_t* frame = esp_camera_fb_get();
    if (!frame) return ESP_FAIL;

    uint8_t* jpegBuffer = frame->buf;
    size_t jpegLength = frame->len;
    bool converted = false;

    if (frame->format != PIXFORMAT_JPEG) {
      converted = frame2jpg(frame, 80, &jpegBuffer, &jpegLength);
      if (!converted) {
        esp_camera_fb_return(frame);
        return ESP_FAIL;
      }
    }

    result = httpd_resp_send_chunk(request, BOUNDARY, strlen(BOUNDARY));
    if (result == ESP_OK) {
      const size_t headerLength = snprintf(header, sizeof(header), PART, jpegLength);
      result = httpd_resp_send_chunk(request, header, headerLength);
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request,
                                     reinterpret_cast<const char*>(jpegBuffer),
                                     jpegLength);
    }

    if (converted) free(jpegBuffer);
    esp_camera_fb_return(frame);
    if (result != ESP_OK) break;
  }
  return result;
}

void startStreamServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port += 1;
  config.max_uri_handlers 
```

### ESP32_Controller.ino (15594 bytes)
```cpp
﻿#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <esp_arduino_version.h>

const char* WIFI_SSID = "froggy";
const char* WIFI_PASSWORD = "Passwordki";

// Left L298N
constexpr uint8_t L_ENA = 25;
constexpr uint8_t L_IN1 = 26;
constexpr uint8_t L_IN2 = 27;
constexpr uint8_t L_IN3 = 14;
constexpr uint8_t L_IN4 = 12;
constexpr uint8_t L_ENB = 33;

// Right L298N
constexpr uint8_t R_ENA = 32;
constexpr uint8_t R_IN1 = 23;
constexpr uint8_t R_IN2 = 22;
constexpr uint8_t R_IN3 = 21;
constexpr uint8_t R_IN4 = 19;
constexpr uint8_t R_ENB = 18;

constexpr uint8_t PAN_PIN = 13;
constexpr uint8_t TILT_PIN = 4;
constexpr uint8_t UART_RX = 16;  // ESP32-CAM U0T
constexpr uint8_t UART_TX = 17;  // ESP32-CAM U0R

constexpr uint32_t MOTOR_PWM_FREQ = 1000;
constexpr uint8_t MOTOR_PWM_BITS = 8;
constexpr uint32_t SERVO_PWM_FREQ = 50;
constexpr uint8_t SERVO_PWM_BITS = 16;
constexpr uint8_t MOTOR_SPEED = 220;

WebServer server(80);
HardwareSerial CameraSerial(2);

#if ESP_ARDUINO_VERSION_MAJOR < 3
constexpr uint8_t CH_L_ENA = 0;
constexpr uint8_t CH_L_ENB = 1;
constexpr uint8_t CH_R_ENA = 2;
constexpr uint8_t CH_R_ENB = 3;
constexpr uint8_t CH_PAN = 4;
constexpr uint8_t CH_TILT = 5;

void attachPwm(uint8_t pin, uint8_t channel, uint32_t freq, uint8_t bits) {
  ledcSetup(channel, freq, bits);
  ledcAttachPin(pin, channel);
}
void writePwm(uint8_t pin, uint8_t channel, uint32_t duty) {
  (void)pin;
  ledcWrite(channel, duty);
}
#else
void attachPwm(uint8_t pin, uint8_t channel, uint32_t freq, uint8_t bits) {
  (void)channel;
  ledcAttach(pin, freq, bits);
}
void writePwm(uint8_t pin, uint8_t channel, uint32_t duty) {
  (void)channel;
  ledcWrite(pin, duty);
}
#endif

int panAngle = 90;
int tiltAngle = 90;

void setServo(uint8_t pin, uint8_t channel, int angle) {
  angle = constrain(angle, 0, 180);
  // 0.5 ms to 2.5 ms pulse in a 20 ms period.
  const uint32_t duty = map(angle, 0, 180, 1638, 8192);
  writePwm(pin, channel, duty);
}

void setMotorPins(bool leftForward, bool leftReverse,
                  bool rightForward, bool rightReverse) {
  digitalWrite(L_IN1, leftForward);
  digitalWrite(L_IN2, leftReverse);
  digitalWrite(L_IN3, leftForward);
  digitalWrite(L_IN4, leftReverse);
  digitalWrite(R_IN1, rightForward);
  digitalWrite(R_IN2, rightReverse);
  digitalWrite(R_IN3, rightForward);
  digitalWrite(R_IN4, rightReverse);
}

void stopMotors() {
  setMotorPins(false, false, false, false);
}

void drive(const String& command) {
  if (command == "forward") {
    setMotorPins(true, false, true, false);
  } else if (command == "backward") {
    setMotorPins(false, true, false, true);
  } else if (command == "left") {
    setMotorPins(false, true, true, false);
  } else if (command == "right") {
    setMotorPins(true, false, false, true);
  } else {
    stopMotors();
  }
}


const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
  <title>ESP32 Robot Car</title>
  <style>
    :root{color-scheme:dark;--card:rgba(16,29,46,.82);--line:rgba(148,180,220,.18);--text:#eef6ff;--muted:#93a9c2;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    body{margin:0;min-height:100svh;color:var(--text);background:radial-gradient(circle at 15% 10%,rgba(56,168,255,.28),transparent 32%),radial-gradient(circle at 85% 0%,rgba(
```
