#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include "esp_camera.h"
#include "esp_http_server.h"

// Phone hotspot used by both ESP32 boards.
const char* WIFI_SSID = "CAR";
const char* WIFI_PASSWORD = "car123456";

// AI-Thinker ESP32-CAM camera pins.
constexpr int CAM_PIN_PWDN = 32;
constexpr int CAM_PIN_RESET = -1;
constexpr int CAM_PIN_XCLK = 0;
constexpr int CAM_PIN_SIOD = 26;
constexpr int CAM_PIN_SIOC = 27;
constexpr int CAM_PIN_Y9 = 35;
constexpr int CAM_PIN_Y8 = 34;
constexpr int CAM_PIN_Y7 = 39;
constexpr int CAM_PIN_Y6 = 36;
constexpr int CAM_PIN_Y5 = 21;
constexpr int CAM_PIN_Y4 = 19;
constexpr int CAM_PIN_Y3 = 18;
constexpr int CAM_PIN_Y2 = 5;
constexpr int CAM_PIN_VSYNC = 25;
constexpr int CAM_PIN_HREF = 23;
constexpr int CAM_PIN_PCLK = 22;
constexpr uint8_t FLASH_LED_PIN = 4;
constexpr uint8_t FLASH_LED_CHANNEL = 7;

httpd_handle_t controlServer = nullptr;
httpd_handle_t streamServer = nullptr;
unsigned long lastIpAnnouncementMs = 0;
int flashDuty = 0;

const char CAMERA_PAGE[] PROGMEM = R"HTML(
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Neural Rover Camera</title>
  <style>
    body{margin:0;background:#08111e;color:#fff;font-family:Arial;text-align:center}
    main{max-width:720px;margin:auto;padding:12px}
    img{width:100%;aspect-ratio:4/3;object-fit:contain;background:#000;border-radius:14px}
    a{color:#69e2af}
  </style>
</head>
<body>
  <main>
    <h2>ESP32-CAM</h2>
    <img id="stream" alt="Camera stream">
    <p>This is the camera diagnostic page. Use the main ESP32 page to control the rover.</p>
  </main>
  <script>
    document.getElementById('stream').src =
      'http://' + location.hostname + ':81/stream';
  </script>
</body>
</html>
)HTML";

esp_err_t rootHandler(httpd_req_t* request) {
  httpd_resp_set_type(request, "text/html");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  return httpd_resp_send(request, CAMERA_PAGE, HTTPD_RESP_USE_STRLEN);
}

esp_err_t flashHandler(httpd_req_t* request) {
  char query[64] = {};
  char valueText[12] = {};

  if (httpd_req_get_url_query_str(request, query, sizeof(query)) == ESP_OK &&
      httpd_query_key_value(
        query,
        "value",
        valueText,
        sizeof(valueText)
      ) == ESP_OK) {
    flashDuty = constrain(atoi(valueText), 0, 255);
    ledcWrite(FLASH_LED_PIN, flashDuty);
  }

  char response[32];
  const int responseLength = snprintf(
    response,
    sizeof(response),
    "{\"flash\":%d}",
    flashDuty
  );

  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  httpd_resp_set_type(request, "application/json");
  return httpd_resp_send(request, response, responseLength);
}

esp_err_t streamHandler(httpd_req_t* request) {
  static const char* CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=frame";
  static const char* BOUNDARY = "\r\n--frame\r\n";
  static const char* HEADER =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

  esp_err_t result = httpd_resp_set_type(request, CONTENT_TYPE);
  if (result != ESP_OK) return result;

  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");

  while (true) {
    camera_fb_t* frame = esp_camera_fb_get();
    if (!frame) {
      return ESP_FAIL;
    }

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

    char header[64];
    const int headerLength = snprintf(
      header,
      sizeof(header),
      HEADER,
      static_cast<unsigned int>(jpegLength)
    );

    result = httpd_resp_send_chunk(request, BOUNDARY, strlen(BOUNDARY));
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(request, header, headerLength);
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
        request,
        reinterpret_cast<const char*>(jpegBuffer),
        jpegLength
      );
    }

    if (converted) {
      free(jpegBuffer);
    }
    esp_camera_fb_return(frame);

    if (result != ESP_OK) {
      break;
    }
  }

  return result;
}

bool setupCamera() {
  const bool hasPsram = psramFound();
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = CAM_PIN_Y2;
  config.pin_d1 = CAM_PIN_Y3;
  config.pin_d2 = CAM_PIN_Y4;
  config.pin_d3 = CAM_PIN_Y5;
  config.pin_d4 = CAM_PIN_Y6;
  config.pin_d5 = CAM_PIN_Y7;
  config.pin_d6 = CAM_PIN_Y8;
  config.pin_d7 = CAM_PIN_Y9;
  config.pin_xclk = CAM_PIN_XCLK;
  config.pin_pclk = CAM_PIN_PCLK;
  config.pin_vsync = CAM_PIN_VSYNC;
  config.pin_href = CAM_PIN_HREF;
  config.pin_sccb_sda = CAM_PIN_SIOD;
  config.pin_sccb_scl = CAM_PIN_SIOC;
  config.pin_pwdn = CAM_PIN_PWDN;
  config.pin_reset = CAM_PIN_RESET;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count = hasPsram ? 2 : 1;
  config.grab_mode =
    hasPsram ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location =
    hasPsram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  esp_err_t error = esp_camera_init(&config);
  framesize_t activeFrameSize = FRAMESIZE_VGA;

  if (error == ESP_ERR_NOT_SUPPORTED) {
    Serial.println(
      "Sensor has no hardware JPEG; using RGB565 QVGA fallback."
    );

    // Non-JPEG capture is much heavier on the original ESP32. QVGA with one
    // frame buffer is the stable setting recommended for software conversion.
    config.pixel_format = PIXFORMAT_RGB565;
    config.frame_size = FRAMESIZE_QVGA;
    config.fb_count = 1;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    activeFrameSize = FRAMESIZE_QVGA;
    error = esp_camera_init(&config);
  }

  if (error != ESP_OK) {
    Serial.printf("Camera initialization failed: 0x%x\n", error);
    return false;
  }

  sensor_t* sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_framesize(sensor, activeFrameSize);
  }

  return true;
}

void setupFlashLed() {
  // Channel 7 avoids the camera XCLK on LEDC channel/timer 0.
  if (!ledcAttachChannel(
        FLASH_LED_PIN,
        5000,
        8,
        FLASH_LED_CHANNEL
      )) {
    Serial.println("Flash LED PWM setup failed.");
  }
  ledcWrite(FLASH_LED_PIN, 0);
}

bool startWebServers() {
  httpd_config_t controlConfig = HTTPD_DEFAULT_CONFIG();
  controlConfig.server_port = 80;
  controlConfig.max_uri_handlers = 4;
  controlConfig.lru_purge_enable = true;

  if (httpd_start(&controlServer, &controlConfig) != ESP_OK) {
    return false;
  }

  const httpd_uri_t rootUri = {
    .uri = "/",
    .method = HTTP_GET,
    .handler = rootHandler,
    .user_ctx = nullptr
  };
  const httpd_uri_t flashUri = {
    .uri = "/flash",
    .method = HTTP_GET,
    .handler = flashHandler,
    .user_ctx = nullptr
  };

  httpd_register_uri_handler(controlServer, &rootUri);
  httpd_register_uri_handler(controlServer, &flashUri);

  httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
  streamConfig.server_port = 81;
  streamConfig.ctrl_port = controlConfig.ctrl_port + 1;
  streamConfig.max_uri_handlers = 2;
  streamConfig.lru_purge_enable = true;

  if (httpd_start(&streamServer, &streamConfig) != ESP_OK) {
    return false;
  }

  const httpd_uri_t streamUri = {
    .uri = "/stream",
    .method = HTTP_GET,
    .handler = streamHandler,
    .user_ctx = nullptr
  };
  httpd_register_uri_handler(streamServer, &streamUri);
  return true;
}

void connectToHotspot() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting ESP32-CAM to hotspot ");
  Serial.println(WIFI_SSID);

  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print('.');
  }
  Serial.println();
}

void announceCameraIp() {
  if (WiFi.status() != WL_CONNECTED) return;

  Serial.print("CAMIP:");
  Serial.println(WiFi.localIP());
  lastIpAnnouncementMs = millis();
}

void handleUartRequests() {
  while (Serial.available() > 0) {
    if (Serial.read() == '?') {
      announceCameraIp();
    }
  }
}

void setup() {
  // U0R/U0T are used for uploading and, after installation, for UART2
  // communication with the main ESP32.
  Serial.begin(115200);
  delay(500);

  if (!setupCamera()) {
    while (true) delay(1000);
  }
  setupFlashLed();
  connectToHotspot();

  if (!startWebServers()) {
    Serial.println("Camera web server failed to start.");
    while (true) delay(1000);
  }

  if (MDNS.begin("rovercam")) {
    MDNS.addService("http", "tcp", 80);
  }

  Serial.print("Camera page: http://");
  Serial.println(WiFi.localIP());
  Serial.print("VGA stream: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");
  announceCameraIp();
}

void loop() {
  handleUartRequests();

  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(500);
    return;
  }

  if (millis() - lastIpAnnouncementMs >= 3000) {
    announceCameraIp();
  }

  delay(10);
}
