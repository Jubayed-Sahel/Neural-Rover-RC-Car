#include <Arduino.h>

// UART link from ESP32-CAM:
// ESP32-CAM U0T/GPIO1 -> main ESP32 GPIO16/RX2
// Common GND is required. GPIO17/TX2 is reserved for future feedback.
constexpr uint8_t CAMERA_RX_PIN = 16;
constexpr uint8_t CAMERA_TX_PIN = 17;
constexpr uint32_t CAMERA_UART_BAUD = 115200;
constexpr uint8_t UART_SYNC = 0xA5;

// Left L298N
// OUT1/OUT2 = front-left, OUT3/OUT4 = rear-left
constexpr uint8_t L_ENA = 25;
constexpr uint8_t L_IN1 = 26;
constexpr uint8_t L_IN2 = 27;
constexpr uint8_t L_IN3 = 14;
constexpr uint8_t L_IN4 = 12;
constexpr uint8_t L_ENB = 33;

// Right L298N
// OUT1/OUT2 = front-right, OUT3/OUT4 = rear-right
constexpr uint8_t R_ENA = 32;
constexpr uint8_t R_IN1 = 23;
constexpr uint8_t R_IN2 = 22;
constexpr uint8_t R_IN3 = 21;
constexpr uint8_t R_IN4 = 19;
constexpr uint8_t R_ENB = 18;

enum Motion : uint8_t {
  STOP = 0,
  FORWARD = 1,
  BACKWARD = 2,
  LEFT = 3,
  RIGHT = 4
};

// The camera page repeats a held command every 250 ms. If communication
// disappears, the main ESP32 stops the motors automatically.
constexpr unsigned long COMMAND_TIMEOUT_MS = 800;

// Smooth internal ramp to reduce four-motor startup current.
constexpr uint32_t MOTOR_PWM_FREQUENCY = 12000;
constexpr uint8_t MOTOR_PWM_RESOLUTION = 8;
constexpr uint8_t MOTOR_START_DUTY = 120;
constexpr uint8_t MOTOR_FULL_DUTY = 255;
constexpr uint8_t MOTOR_RAMP_STEP = 12;
constexpr unsigned long MOTOR_RAMP_INTERVAL_MS = 12;
constexpr unsigned long DIRECTION_DEADTIME_MS = 40;

HardwareSerial CameraLink(2);

Motion requestedMotion = STOP;
Motion currentMotion = STOP;
Motion pendingMotion = STOP;
uint8_t currentMotorDuty = 0;
unsigned long lastCommandMs = 0;
unsigned long directionReadyMs = 0;
unsigned long lastRampMs = 0;
bool directionChangePending = false;

enum PacketState : uint8_t {
  WAIT_FOR_SYNC,
  WAIT_FOR_COMMAND,
  WAIT_FOR_CHECKSUM
};

PacketState packetState = WAIT_FOR_SYNC;
uint8_t receivedCommand = 0;

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

bool decodeCommand(uint8_t command, Motion& motion) {
  switch (static_cast<char>(command)) {
    case 'F': motion = FORWARD; return true;
    case 'B': motion = BACKWARD; return true;
    case 'L': motion = LEFT; return true;
    case 'R': motion = RIGHT; return true;
    case 'S': motion = STOP; return true;
    default: return false;
  }
}

void acceptCommand(uint8_t command) {
  Motion motion = STOP;
  if (!decodeCommand(command, motion)) return;

  requestedMotion = motion;
  lastCommandMs = millis();
}

void readCameraCommands() {
  while (CameraLink.available() > 0) {
    const uint8_t value = static_cast<uint8_t>(CameraLink.read());

    if (packetState == WAIT_FOR_SYNC) {
      if (value == UART_SYNC) {
        packetState = WAIT_FOR_COMMAND;
      }
      continue;
    }

    if (packetState == WAIT_FOR_COMMAND) {
      receivedCommand = value;
      packetState = WAIT_FOR_CHECKSUM;
      continue;
    }

    if (value == static_cast<uint8_t>(receivedCommand ^ 0xFF)) {
      acceptCommand(receivedCommand);
    }

    packetState = value == UART_SYNC ? WAIT_FOR_COMMAND : WAIT_FOR_SYNC;
  }
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

void setup() {
  Serial.begin(115200);
  delay(300);

  setupMotorPins();
  CameraLink.begin(
    CAMERA_UART_BAUD,
    SERIAL_8N1,
    CAMERA_RX_PIN,
    CAMERA_TX_PIN
  );

  lastCommandMs = millis();
  Serial.println("Main ESP32 motor receiver ready.");
}

void loop() {
  readCameraCommands();

  if (requestedMotion != STOP &&
      millis() - lastCommandMs > COMMAND_TIMEOUT_MS) {
    requestedMotion = STOP;
  }

  updateMotors(requestedMotion);
  delay(1);
}
