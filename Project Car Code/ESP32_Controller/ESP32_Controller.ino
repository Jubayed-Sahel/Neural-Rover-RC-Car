#include <Arduino.h>
#include <WiFi.h>
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>

// Phone hotspot
const char* WIFI_SSID = "CAR";
const char* WIFI_PASSWORD = "car123456";

// Left L298N
// OUT1/OUT2 = front-left, OUT3/OUT4 = rear-left
const uint8_t L_ENA = 25;
const uint8_t L_IN1 = 26;
const uint8_t L_IN2 = 27;
const uint8_t L_IN3 = 14;
const uint8_t L_IN4 = 12;
const uint8_t L_ENB = 33;

// Right L298N
// OUT1/OUT2 = front-right, OUT3/OUT4 = rear-right
const uint8_t R_ENA = 32;
const uint8_t R_IN1 = 23;
const uint8_t R_IN2 = 22;
const uint8_t R_IN3 = 21;
const uint8_t R_IN4 = 19;
const uint8_t R_ENB = 18;

// Pan/tilt and ESP32-CAM UART pins from the master documentation.
const uint8_t PAN_SERVO_PIN = 13;
const uint8_t TILT_SERVO_PIN = 4;
const uint8_t CAMERA_UART_RX = 16;  // ESP32-CAM U0T
const uint8_t CAMERA_UART_TX = 17;  // ESP32-CAM U0R
const uint32_t CAMERA_UART_BAUD = 115200;

enum Motion : uint8_t {
  STOP = 0,
  FORWARD = 1,
  BACKWARD = 2,
  LEFT = 3,
  RIGHT = 4
};

const unsigned long COMMAND_TIMEOUT_MS = 1300;

// Motor protection and soft start. The page still has no speed control:
// every command smoothly ramps to full power.
const uint32_t MOTOR_PWM_FREQUENCY = 12000;
const uint8_t MOTOR_PWM_RESOLUTION = 8;
const uint8_t MOTOR_START_DUTY = 120;
const uint8_t MOTOR_FULL_DUTY = 255;
const uint8_t MOTOR_RAMP_STEP = 12;
const unsigned long MOTOR_RAMP_INTERVAL_MS = 12;
const unsigned long DIRECTION_DEADTIME_MS = 40;
const uint32_t SERVO_PWM_FREQUENCY = 50;
const uint8_t SERVO_PWM_RESOLUTION = 16;
const int SERVO_START_ANGLE = 90;

AsyncWebServer server(80);
AsyncWebSocket webSocket("/ws");
HardwareSerial CameraSerial(2);

volatile uint8_t requestedMotion = STOP;
volatile unsigned long lastCommandMs = 0;
Motion currentMotion = STOP;
Motion pendingMotion = STOP;
uint8_t currentMotorDuty = 0;
unsigned long directionReadyMs = 0;
unsigned long lastRampMs = 0;
bool directionChangePending = false;
unsigned long lastWiFiRetryMs = 0;
bool wasWiFiConnected = false;
int panAngle = SERVO_START_ANGLE;
int tiltAngle = SERVO_START_ANGLE;

char cameraIp[16] = "";
char cameraLine[96] = "";
size_t cameraLineLength = 0;
unsigned long lastCameraIpRequestMs = 0;
portMUX_TYPE cameraIpMux = portMUX_INITIALIZER_UNLOCKED;

const char CONTROL_PAGE[] PROGMEM = R"HTML(
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
  <title>ESP32 RC Car</title>
  <style>
    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    html,body{margin:0;width:100%;min-height:100%;touch-action:manipulation}
    body{
      display:flex;justify-content:center;background:#0a101c;color:#fff;
      font-family:Arial,sans-serif;user-select:none;-webkit-user-select:none
    }
    main{width:min(720px,100%);padding:12px 12px 24px}
    h1{margin:2px 0 10px;text-align:center;font-size:26px}
    .video{
      position:relative;width:100%;aspect-ratio:4/3;background:#000;
      border:2px solid #263d57;border-radius:16px;overflow:hidden
    }
    .video img{display:block;width:100%;height:100%;object-fit:contain}
    #cameraLink{
      position:absolute;top:9px;left:9px;padding:6px 9px;border-radius:18px;
      background:#7b1d2c;color:#fff;font-size:11px;font-weight:900
    }
    #cameraLink.online{background:#12633e}
    #link{margin:9px 0 11px;text-align:center;color:#ff7373;font-weight:bold}
    #link.online{color:#68edae}
    .pad{
      width:min(410px,100%);margin:auto;
      display:grid;grid-template-columns:1fr 1fr 1fr;
      grid-template-areas:". f ." "l s r" ". b .";gap:12px
    }
    button{
      height:72px;border:0;border-radius:18px;background:#263750;color:#fff;
      font-size:34px;font-weight:900;touch-action:none;box-shadow:0 6px 0 #040812
    }
    button.active{transform:translateY(6px);box-shadow:none;background:#168458}
    #f{grid-area:f}#l{grid-area:l}#r{grid-area:r}#b{grid-area:b}
    #s{grid-area:s;background:#b42331;font-size:15px}
    #status{
      width:min(410px,100%);margin:15px auto 0;padding:10px;
      border-radius:12px;background:#111c2d;
      text-align:center;color:#72f1bc;font-size:18px;font-weight:bold
    }
    .controls{
      width:min(520px,100%);margin:13px auto 0;padding:12px;
      border-radius:14px;background:#111c2d
    }
    .control-row{
      display:grid;grid-template-columns:54px 1fr 42px;align-items:center;
      gap:9px;margin:9px 0;font-size:12px;font-weight:900
    }
    input[type=range]{width:100%;accent-color:#29c387}
    .help{margin-top:12px;text-align:center;color:#8fa0b6;font-size:13px}
  </style>
</head>
<body>
  <main>
    <h1>NEURAL ROVER</h1>
    <div class="video">
      <img id="camera" alt="ESP32-CAM VGA stream">
      <div id="cameraLink">CAMERA WAITING</div>
    </div>
    <div id="link">CONTROL CONNECTING...</div>
    <div class="pad">
      <button id="f" data-cmd="F">&#8593;</button>
      <button id="l" data-cmd="L">&#8592;</button>
      <button id="s" data-cmd="S">STOP</button>
      <button id="r" data-cmd="R">&#8594;</button>
      <button id="b" data-cmd="B">&#8595;</button>
    </div>
    <div id="status">STOP</div>
    <div class="controls">
      <div class="control-row">
        <label for="pan">PAN</label>
        <input id="pan" type="range" min="0" max="180" value="90">
        <output id="panValue">90</output>
      </div>
      <div class="control-row">
        <label for="tilt">TILT</label>
        <input id="tilt" type="range" min="0" max="180" value="90">
        <output id="tiltValue">90</output>
      </div>
      <div class="control-row">
        <label for="flash">LIGHT</label>
        <input id="flash" type="range" min="0" max="255" value="0">
        <output id="flashValue">0</output>
      </div>
    </div>
    <div class="help">PRESS AND HOLD · RELEASE TO STOP</div>
  </main>

  <script>
    const buttons = [...document.querySelectorAll('button')];
    const linkBox = document.getElementById('link');
    const statusBox = document.getElementById('status');
    const cameraImage = document.getElementById('camera');
    const cameraLink = document.getElementById('cameraLink');
    const names = {S:'STOP',F:'FORWARD',B:'BACKWARD',L:'LEFT',R:'RIGHT'};

    let socket = null;
    let cameraHost = '';
    let heldCommand = 'S';
    let heartbeatTimer = null;
    let keepAliveTimer = null;
    let reconnectTimer = null;
    const controlTimers = {pan:null,tilt:null,flash:null};

    function connectSocket() {
      clearTimeout(reconnectTimer);
      socket = new WebSocket('ws://' + location.host + '/ws');

      socket.onopen = () => {
        linkBox.textContent = 'CONNECTED';
        linkBox.classList.add('online');
        send('S');
        send('P' + document.getElementById('pan').value);
        send('T' + document.getElementById('tilt').value);
        clearInterval(keepAliveTimer);
        keepAliveTimer = setInterval(() => send('K'), 2000);
      };

      socket.onclose = () => {
        clearInterval(heartbeatTimer);
        clearInterval(keepAliveTimer);
        heartbeatTimer = null;
        keepAliveTimer = null;
        heldCommand = 'S';
        show('S');
        linkBox.textContent = 'RECONNECTING...';
        linkBox.classList.remove('online');
        reconnectTimer = setTimeout(connectSocket, 700);
      };

      socket.onerror = () => socket.close();
    }

    function send(command) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(command);
      }
    }

    async function refreshCameraHost() {
      try {
        const response = await fetch('/camera-ip', {cache:'no-store'});
        const host = (await response.text()).trim();
        if (!host || host === cameraHost) return;

        cameraHost = host;
        cameraLink.textContent = 'CAMERA CONNECTING';
        cameraLink.classList.remove('online');
        cameraImage.src =
          'http://' + cameraHost + ':81/stream?v=' + Date.now();
      } catch (_) {
        cameraLink.textContent = 'CAMERA WAITING';
        cameraLink.classList.remove('online');
      }
    }

    cameraImage.onload = () => {
      cameraLink.textContent = 'CAMERA LIVE';
      cameraLink.classList.add('online');
    };

    cameraImage.onerror = () => {
      cameraLink.textContent = 'CAMERA RECONNECTING';
      cameraLink.classList.remove('online');
      if (cameraHost) {
        setTimeout(() => {
          cameraImage.src =
            'http://' + cameraHost + ':81/stream?v=' + Date.now();
        }, 1000);
      }
    };

    function moveServo(axis, prefix, value) {
      document.getElementById(axis + 'Value').value = value;
      clearTimeout(controlTimers[axis]);
      controlTimers[axis] = setTimeout(() => send(prefix + value), 45);
    }

    function setFlash(value) {
      document.getElementById('flashValue').value = value;
      clearTimeout(controlTimers.flash);
      controlTimers.flash = setTimeout(() => {
        if (!cameraHost) return;
        fetch(
          'http://' + cameraHost + '/flash?value=' + value,
          {cache:'no-store'}
        ).catch(() => {});
      }, 60);
    }

    function show(command) {
      statusBox.textContent = names[command];
      buttons.forEach(button => {
        button.classList.toggle('active', button.dataset.cmd === command);
      });
    }

    function start(command) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
      heldCommand = command;
      show(command);
      send(command);

      if (command !== 'S') {
        heartbeatTimer = setInterval(() => {
          if (heldCommand === command) send(command);
        }, 450);
      }
    }

    function stop() {
      if (heldCommand === 'S') return;
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
      heldCommand = 'S';
      show('S');
      send('S');
    }

    buttons.forEach(button => {
      button.addEventListener('pointerdown', event => {
        event.preventDefault();
        start(button.dataset.cmd);
      });
      button.addEventListener('contextmenu', event => event.preventDefault());
    });

    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
    window.addEventListener('blur', stop);
    window.addEventListener('pagehide', stop);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stop();
    });

    document.getElementById('pan').addEventListener('input', event => {
      moveServo('pan', 'P', event.target.value);
    });
    document.getElementById('tilt').addEventListener('input', event => {
      moveServo('tilt', 'T', event.target.value);
    });
    document.getElementById('flash').addEventListener('input', event => {
      setFlash(event.target.value);
    });

    connectSocket();
    refreshCameraHost();
    setInterval(refreshCameraHost, 2500);
  </script>
</body>
</html>
)HTML";

void setPair(uint8_t in1, uint8_t in2, int8_t direction) {
  if (direction > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else if (direction < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
}

void setEnableDuty(uint8_t duty) {
  ledcWrite(L_ENA, duty);
  ledcWrite(L_ENB, duty);
  ledcWrite(R_ENA, duty);
  ledcWrite(R_ENB, duty);
  currentMotorDuty = duty;
}

uint32_t servoDutyForAngle(int angle) {
  const int constrainedAngle = constrain(angle, 0, 180);
  const uint32_t pulseUs = map(constrainedAngle, 0, 180, 500, 2500);
  return (pulseUs * 65535UL) / 20000UL;
}

void setServoAngle(uint8_t pin, int angle) {
  ledcWrite(pin, servoDutyForAngle(angle));
}

void stopCar() {
  setEnableDuty(0);
  setPair(L_IN1, L_IN2, 0);
  setPair(L_IN3, L_IN4, 0);
  setPair(R_IN1, R_IN2, 0);
  setPair(R_IN3, R_IN4, 0);
  currentMotion = STOP;
  pendingMotion = STOP;
  directionChangePending = false;
}

void applyDirection(Motion motion) {
  int8_t leftDirection = 0;
  int8_t rightDirection = 0;

  if (motion == FORWARD) {
    leftDirection = 1;
    rightDirection = 1;
  } else if (motion == BACKWARD) {
    leftDirection = -1;
    rightDirection = -1;
  } else if (motion == LEFT) {
    leftDirection = -1;
    rightDirection = 1;
  } else if (motion == RIGHT) {
    leftDirection = 1;
    rightDirection = -1;
  } else {
    stopCar();
    return;
  }

  setPair(L_IN1, L_IN2, leftDirection);
  setPair(L_IN3, L_IN4, leftDirection);
  setPair(R_IN1, R_IN2, rightDirection);
  setPair(R_IN3, R_IN4, rightDirection);
}

void updateMotors(Motion requested) {
  const unsigned long now = millis();

  if (requested == STOP) {
    if (currentMotion != STOP || directionChangePending ||
        currentMotorDuty != 0) {
      stopCar();
    }
    return;
  }

  if (directionChangePending) {
    // A newer command replaces an older pending command safely.
    if (requested != pendingMotion) {
      pendingMotion = requested;
      directionReadyMs = now + DIRECTION_DEADTIME_MS;
    }

    if (static_cast<long>(now - directionReadyMs) >= 0) {
      applyDirection(pendingMotion);
      currentMotion = pendingMotion;
      directionChangePending = false;
      setEnableDuty(MOTOR_START_DUTY);
      lastRampMs = now;
    }
    return;
  }

  if (requested != currentMotion) {
    // Remove motor power before changing H-bridge direction. This prevents
    // a large reverse-current spike when the user changes direction quickly.
    setEnableDuty(0);
    setPair(L_IN1, L_IN2, 0);
    setPair(L_IN3, L_IN4, 0);
    setPair(R_IN1, R_IN2, 0);
    setPair(R_IN3, R_IN4, 0);
    currentMotion = STOP;
    pendingMotion = requested;
    directionChangePending = true;
    directionReadyMs = now + DIRECTION_DEADTIME_MS;
    return;
  }

  if (currentMotorDuty < MOTOR_FULL_DUTY &&
      now - lastRampMs >= MOTOR_RAMP_INTERVAL_MS) {
    const uint16_t nextDuty =
      static_cast<uint16_t>(currentMotorDuty) + MOTOR_RAMP_STEP;
    setEnableDuty(nextDuty > MOTOR_FULL_DUTY
                    ? MOTOR_FULL_DUTY
                    : static_cast<uint8_t>(nextDuty));
    lastRampMs = now;
  }
}

void requestMotion(Motion motion) {
  requestedMotion = static_cast<uint8_t>(motion);
  lastCommandMs = millis();
}

void onWebSocketEvent(AsyncWebSocket* server,
                      AsyncWebSocketClient* client,
                      AwsEventType type,
                      void* arg,
                      uint8_t* data,
                      size_t len) {
  if (type == WS_EVT_CONNECT) {
    Serial.print("Controller connected: ");
    Serial.println(client->remoteIP());
    requestMotion(STOP);
    return;
  }

  if (type == WS_EVT_DISCONNECT) {
    Serial.println("Controller disconnected. Stopping.");
    requestMotion(STOP);
    return;
  }

  if (type != WS_EVT_DATA || len == 0) return;

  AwsFrameInfo* info = static_cast<AwsFrameInfo*>(arg);
  if (!info->final || info->index != 0 || info->opcode != WS_TEXT) return;

  if (len >= 2 &&
      (static_cast<char>(data[0]) == 'P' ||
       static_cast<char>(data[0]) == 'T')) {
    char angleText[8] = {};
    const size_t angleLength = min(len - 1, sizeof(angleText) - 1);
    memcpy(angleText, data + 1, angleLength);
    const int angle = constrain(atoi(angleText), 0, 180);

    if (static_cast<char>(data[0]) == 'P') {
      panAngle = angle;
      setServoAngle(PAN_SERVO_PIN, panAngle);
    } else {
      tiltAngle = angle;
      setServoAngle(TILT_SERVO_PIN, tiltAngle);
    }
    return;
  }

  if (len != 1) return;

  // Browser keepalive: keeps phone hotspots from dropping an idle WebSocket.
  if (static_cast<char>(data[0]) == 'K') {
    client->text("K");
    return;
  }

  Motion motion = STOP;
  switch (static_cast<char>(data[0])) {
    case 'F': motion = FORWARD; break;
    case 'B': motion = BACKWARD; break;
    case 'L': motion = LEFT; break;
    case 'R': motion = RIGHT; break;
    default:  motion = STOP; break;
  }

  requestMotion(motion);
}

void setupMotorPins() {
  const uint8_t directionPins[] = {
    L_IN1, L_IN2, L_IN3, L_IN4,
    R_IN1, R_IN2, R_IN3, R_IN4
  };

  for (uint8_t pin : directionPins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }

  const uint8_t enablePins[] = {L_ENA, L_ENB, R_ENA, R_ENB};
  for (uint8_t pin : enablePins) {
    if (!ledcAttach(pin, MOTOR_PWM_FREQUENCY, MOTOR_PWM_RESOLUTION)) {
      Serial.print("PWM attach failed on GPIO ");
      Serial.println(pin);
    }
    ledcWrite(pin, 0);
  }

  stopCar();
}

void setupServoPins() {
  if (!ledcAttach(
        PAN_SERVO_PIN,
        SERVO_PWM_FREQUENCY,
        SERVO_PWM_RESOLUTION
      )) {
    Serial.println("Pan servo PWM setup failed.");
  }
  if (!ledcAttach(
        TILT_SERVO_PIN,
        SERVO_PWM_FREQUENCY,
        SERVO_PWM_RESOLUTION
      )) {
    Serial.println("Tilt servo PWM setup failed.");
  }

  setServoAngle(PAN_SERVO_PIN, panAngle);
  setServoAngle(TILT_SERVO_PIN, tiltAngle);
}

void saveCameraIp(const char* value) {
  IPAddress parsedIp;
  if (!parsedIp.fromString(value)) return;

  portENTER_CRITICAL(&cameraIpMux);
  strncpy(cameraIp, value, sizeof(cameraIp) - 1);
  cameraIp[sizeof(cameraIp) - 1] = '\0';
  portEXIT_CRITICAL(&cameraIpMux);

  Serial.print("ESP32-CAM detected at: http://");
  Serial.println(value);
}

void processCameraLine() {
  cameraLine[cameraLineLength] = '\0';

  if (strncmp(cameraLine, "CAMIP:", 6) == 0) {
    saveCameraIp(cameraLine + 6);
  }

  cameraLineLength = 0;
}

void readCameraUart() {
  while (CameraSerial.available() > 0) {
    const char value = static_cast<char>(CameraSerial.read());

    if (value == '\n') {
      processCameraLine();
    } else if (value != '\r') {
      if (cameraLineLength < sizeof(cameraLine) - 1) {
        cameraLine[cameraLineLength++] = value;
      } else {
        cameraLineLength = 0;
      }
    }
  }
}

void maintainCameraLink() {
  const unsigned long now = millis();
  if (now - lastCameraIpRequestMs >= 3000) {
    lastCameraIpRequestMs = now;
    CameraSerial.write('?');
  }
}

void connectToPhoneHotspot() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to phone hotspot ");
  Serial.println(WIFI_SSID);

  const unsigned long startedMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedMs < 15000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    wasWiFiConnected = true;
    Serial.print("Connected. Open: http://");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Hotspot not found yet. Automatic reconnect is active.");
  }
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wasWiFiConnected) {
      wasWiFiConnected = true;
      Serial.print("Wi-Fi reconnected. Open: http://");
      Serial.println(WiFi.localIP());
    }
    return;
  }

  requestMotion(STOP);

  if (wasWiFiConnected) {
    wasWiFiConnected = false;
    Serial.println("Wi-Fi lost. Motors stopped.");
  }

  const unsigned long now = millis();
  if (now - lastWiFiRetryMs >= 3000) {
    lastWiFiRetryMs = now;
    WiFi.reconnect();
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);

  setupMotorPins();
  setupServoPins();
  CameraSerial.begin(
    CAMERA_UART_BAUD,
    SERIAL_8N1,
    CAMERA_UART_RX,
    CAMERA_UART_TX
  );
  connectToPhoneHotspot();

  webSocket.onEvent(onWebSocketEvent);
  server.addHandler(&webSocket);

  server.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    AsyncWebServerResponse* response =
      request->beginResponse_P(200, "text/html", CONTROL_PAGE);
    response->addHeader("Cache-Control", "no-store, no-cache, must-revalidate");
    request->send(response);
  });

  server.on("/camera-ip", HTTP_GET, [](AsyncWebServerRequest* request) {
    char ipCopy[16] = {};
    portENTER_CRITICAL(&cameraIpMux);
    strncpy(ipCopy, cameraIp, sizeof(ipCopy) - 1);
    portEXIT_CRITICAL(&cameraIpMux);

    if (ipCopy[0] == '\0') {
      request->send(200, "text/plain", "rovercam.local");
    } else {
      request->send(200, "text/plain", ipCopy);
    }
  });

  server.onNotFound([](AsyncWebServerRequest* request) {
    request->redirect("/");
  });

  server.begin();
  lastCommandMs = millis();
  Serial.println("WebSocket RC car controller ready.");
}

void loop() {
  readCameraUart();
  maintainCameraLink();
  maintainWiFi();
  webSocket.cleanupClients();

  if (requestedMotion != STOP &&
      millis() - lastCommandMs > COMMAND_TIMEOUT_MS) {
    requestedMotion = STOP;
  }

  const Motion motion = static_cast<Motion>(requestedMotion);
  updateMotors(motion);

  delay(1);
}
