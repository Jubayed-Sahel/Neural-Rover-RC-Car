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

AsyncWebServer server(80);
AsyncWebSocket webSocket("/ws");

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

const char CONTROL_PAGE[] PROGMEM = R"HTML(
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
  <title>ESP32 RC Car</title>
  <style>
    *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
    html,body{margin:0;width:100%;height:100%;overflow:hidden;touch-action:none}
    body{
      display:grid;place-items:center;background:#0a101c;color:#fff;
      font-family:Arial,sans-serif;user-select:none;-webkit-user-select:none
    }
    main{width:min(390px,94vw);padding:18px}
    h1{margin:0;text-align:center;font-size:28px}
    #link{margin:7px 0 18px;text-align:center;color:#ff7373;font-weight:bold}
    #link.online{color:#68edae}
    .pad{
      display:grid;grid-template-columns:1fr 1fr 1fr;
      grid-template-areas:". f ." "l s r" ". b .";gap:12px
    }
    button{
      height:90px;border:0;border-radius:18px;background:#263750;color:#fff;
      font-size:34px;font-weight:900;touch-action:none;box-shadow:0 6px 0 #040812
    }
    button.active{transform:translateY(6px);box-shadow:none;background:#168458}
    #f{grid-area:f}#l{grid-area:l}#r{grid-area:r}#b{grid-area:b}
    #s{grid-area:s;background:#b42331;font-size:15px}
    #status{
      margin-top:17px;padding:11px;border-radius:12px;background:#111c2d;
      text-align:center;color:#72f1bc;font-size:18px;font-weight:bold
    }
    .help{margin-top:12px;text-align:center;color:#8fa0b6;font-size:13px}
  </style>
</head>
<body>
  <main>
    <h1>ESP32 RC Car</h1>
    <div id="link">CONNECTING...</div>
    <div class="pad">
      <button id="f" data-cmd="F">&#8593;</button>
      <button id="l" data-cmd="L">&#8592;</button>
      <button id="s" data-cmd="S">STOP</button>
      <button id="r" data-cmd="R">&#8594;</button>
      <button id="b" data-cmd="B">&#8595;</button>
    </div>
    <div id="status">STOP</div>
    <div class="help">PRESS AND HOLD · RELEASE TO STOP</div>
  </main>

  <script>
    const buttons = [...document.querySelectorAll('button')];
    const linkBox = document.getElementById('link');
    const statusBox = document.getElementById('status');
    const names = {S:'STOP',F:'FORWARD',B:'BACKWARD',L:'LEFT',R:'RIGHT'};

    let socket = null;
    let heldCommand = 'S';
    let heartbeatTimer = null;
    let keepAliveTimer = null;
    let reconnectTimer = null;

    function connectSocket() {
      clearTimeout(reconnectTimer);
      socket = new WebSocket('ws://' + location.host + '/ws');

      socket.onopen = () => {
        linkBox.textContent = 'CONNECTED';
        linkBox.classList.add('online');
        send('S');
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

    connectSocket();
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

  if (type != WS_EVT_DATA || len != 1) return;

  AwsFrameInfo* info = static_cast<AwsFrameInfo*>(arg);
  if (!info->final || info->index != 0 || info->opcode != WS_TEXT) return;

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
  connectToPhoneHotspot();

  webSocket.onEvent(onWebSocketEvent);
  server.addHandler(&webSocket);

  server.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    AsyncWebServerResponse* response =
      request->beginResponse_P(200, "text/html", CONTROL_PAGE);
    response->addHeader("Cache-Control", "no-store, no-cache, must-revalidate");
    request->send(response);
  });

  server.onNotFound([](AsyncWebServerRequest* request) {
    request->redirect("/");
  });

  server.begin();
  lastCommandMs = millis();
  Serial.println("WebSocket RC car controller ready.");
}

void loop() {
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
