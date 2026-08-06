# Neural Rover RC Car — Complete Working Configuration

**Status:** Final motor orientation tested and working  
**Last updated:** 6 August 2026  
**Main controller:** 30-pin ESP32 Dev Module  
**Camera controller:** AI-Thinker-style ESP32-CAM  

This document describes the configuration that is currently working on the physical rover. It supersedes older left/right labels in the original circuit diagram.

---

## 1. What the project does

The Neural Rover is a four-wheel Wi-Fi-controlled robot with:

- Forward, backward, left, right and emergency stop control.
- Four DC gear motors driven by two L298N motor-driver modules.
- A browser-based controller served by the main ESP32.
- Live ESP32-CAM video integrated into the controller page.
- Pan and tilt servo controls.
- Camera flash/illumination control.
- UART communication between the main ESP32 and ESP32-CAM.
- Automatic motor stop if commands, Wi-Fi or the browser connection are lost.
- Optional laptop face recognition using InsightFace `buffalo_l`.

---

## 2. Main components

| Quantity | Component | Purpose |
|---:|---|---|
| 1 | 30-pin ESP32 development board | Main control, webpage, WebSocket, motors and servos |
| 1 | ESP32-CAM | Camera capture, MJPEG stream and flash LED |
| 2 | L298N motor-driver modules | Drive four DC motors |
| 4 | DC geared motors | Rover movement |
| 1 | Pan/tilt bracket | Holds and aims the camera |
| 2 | SG90-style servos | Pan and tilt movement |
| 1 | LM2596 buck converter | Converts battery voltage to regulated 5.0 V |
| 1 | 3S battery | Motor and system power |
| 1 | Robot chassis and four wheels | Mechanical platform |
| — | Wires, switch and connectors | Electrical interconnection |

---

## 3. System responsibilities

### Main ESP32

The main ESP32 performs all real-time rover control:

- Connects to Wi-Fi hotspot `CAR`.
- Serves the control webpage on port 80.
- Maintains the `/ws` WebSocket connection.
- Drives both L298N modules.
- Generates PWM for all four motor enable inputs.
- Controls the pan and tilt servos.
- Receives the ESP32-CAM address over UART2.
- Inserts the camera stream into the control webpage.
- Stops the motors if commands or Wi-Fi are lost.

### ESP32-CAM

The ESP32-CAM performs camera-specific work:

- Connects to the same `CAR` hotspot.
- Serves its diagnostic page on port 80.
- Serves the MJPEG stream on port 81.
- Controls the onboard flash LED.
- Announces its DHCP address to the main ESP32 through UART.

### Laptop — optional AI stage

The laptop may:

- Receive `http://rovercam.local:81/stream`.
- Run InsightFace `buffalo_l` using the NVIDIA MX150.
- Register known people and compare face embeddings.
- Save recognition events and snapshots.

`buffalo_l` does **not** run on either ESP32 board.

---

## 4. Final working main ESP32 pin map

The physical terminal wiring and the software names are shown separately. This distinction matters because the front-left polarity is intentionally reversed in software.

### Physical L298N terminal wiring — do not change

| Physical driver | L298N terminal | Main ESP32 GPIO | Motor/channel |
|---|---|---:|---|
| Left-side driver | ENA | 32 | Front-left PWM |
| Left-side driver | IN1 | 23 | Front-left direction terminal 1 |
| Left-side driver | IN2 | 22 | Front-left direction terminal 2 |
| Left-side driver | IN3 | 21 | Rear-left direction terminal 1 |
| Left-side driver | IN4 | 19 | Rear-left direction terminal 2 |
| Left-side driver | ENB | 18 | Rear-left PWM |
| Right-side driver | ENA | 25 | Front-right PWM |
| Right-side driver | IN1 | 26 | Front-right direction terminal 1 |
| Right-side driver | IN2 | 27 | Front-right direction terminal 2 |
| Right-side driver | IN3 | 14 | Rear-right direction terminal 1 |
| Right-side driver | IN4 | 12 | Rear-right direction terminal 2 |
| Right-side driver | ENB | 33 | Rear-right PWM |

The tables below show how the final software uses those GPIOs.

### Physical left-side L298N

This driver powers the **front-left** and **rear-left** motors.

| Function in final code | ESP32 GPIO | L298N connection | Purpose |
|---|---:|---|---|
| `L_ENA` | 32 | ENA | Front-left PWM/speed enable |
| `L_IN1` | 22 | Physical driver IN2 | Software-corrected front-left polarity |
| `L_IN2` | 23 | Physical driver IN1 | Software-corrected front-left polarity |
| `L_IN3` | 21 | Rear-left direction A | Rear-left direction |
| `L_IN4` | 19 | Rear-left direction B | Rear-left direction |
| `L_ENB` | 18 | ENB | Rear-left PWM/speed enable |

Motor output connections:

| L298N output | Motor |
|---|---|
| OUT1 and OUT2 | Front-left motor |
| OUT3 and OUT4 | Rear-left motor |

> The front-left motor polarity is corrected in software. Do not swap its wires again while using the final code.

### Physical right-side L298N

This driver powers the **front-right** and **rear-right** motors.

| Function in final code | ESP32 GPIO | L298N connection | Purpose |
|---|---:|---|---|
| `R_ENA` | 25 | ENA | Front-right PWM/speed enable |
| `R_IN1` | 26 | Physical driver IN1 | Final corrected front-right polarity |
| `R_IN2` | 27 | Physical driver IN2 | Final corrected front-right polarity |
| `R_IN3` | 14 | Rear-right direction A | Rear-right direction |
| `R_IN4` | 12 | Rear-right direction B | Rear-right direction |
| `R_ENB` | 33 | ENB | Rear-right PWM/speed enable |

Motor output connections:

| L298N output | Motor |
|---|---|
| OUT1 and OUT2 | Front-right motor |
| OUT3 and OUT4 | Rear-right motor |

### Important correction from the original labels

The two motor-driver sides were physically opposite to the original code labels:

- The driver using GPIO32/23/22/21/19/18 is physically the **left** driver.
- The driver using GPIO25/26/27/14/12/33 is physically the **right** driver.

The final code already accounts for this and for the individual front-motor polarity corrections. All four motors now move forward when Forward is pressed.

---

## 5. Pan and tilt servo connections

Both servos are controlled by the **main 30-pin ESP32**, not the ESP32-CAM.

| Servo | Signal pin | Power | Ground |
|---|---:|---|---|
| Pan | GPIO13 | Regulated 5.0 V from LM2596 | Common GND |
| Tilt | GPIO4 | Regulated 5.0 V from LM2596 | Common GND |

Typical SG90 wire colors:

| Wire color | Connection |
|---|---|
| Orange/yellow | Signal |
| Red | 5 V |
| Brown/black | GND |

Important notes:

- Do not power either servo from ESP32 `3V3`.
- GPIO4 here means GPIO4 on the **main ESP32**. GPIO4 on the ESP32-CAM controls its flash LED.
- The servo PWM frequency is 50 Hz with 16-bit resolution.
- The program maps 0–180 degrees to approximately 500–2500 microseconds.
- If the bracket jams near an endpoint, reduce the permitted angle range.

---

## 6. ESP32-to-ESP32-CAM UART connection

UART2 runs at **115200 baud**.

| Main ESP32 | ESP32-CAM | Direction |
|---|---|---|
| GPIO16 — RX2 | U0T / TX0 | Camera to main ESP32 |
| GPIO17 — TX2 | U0R / RX0 | Main ESP32 to camera |
| GND | GND | Common reference |

The TX and RX connections must cross:

```text
Main ESP32 GPIO16 RX2  <-  ESP32-CAM U0T TX
Main ESP32 GPIO17 TX2  ->  ESP32-CAM U0R RX
```

The ESP32-CAM repeatedly sends:

```text
CAMIP:192.168.x.x
```

The main ESP32 parses this message and provides the address to the browser through `/camera-ip`.

---

## 7. ESP32-CAM internal camera pins

These pins connect the ESP32-CAM processor to its camera sensor. They should not be reused for external components.

| Camera signal | ESP32-CAM GPIO |
|---|---:|
| PWDN | 32 |
| RESET | Not connected (`-1`) |
| XCLK | 0 |
| SIOD/SDA | 26 |
| SIOC/SCL | 27 |
| Y9 / D7 | 35 |
| Y8 / D6 | 34 |
| Y7 / D5 | 39 |
| Y6 / D4 | 36 |
| Y5 / D3 | 21 |
| Y4 / D2 | 19 |
| Y3 / D1 | 18 |
| Y2 / D0 | 5 |
| VSYNC | 25 |
| HREF | 23 |
| PCLK | 22 |
| Flash LED | 4 |

The camera clock is 20 MHz.

### Current camera mode

The installed sensor reports that hardware JPEG is unavailable. The firmware therefore falls back to:

```text
Capture: RGB565
Resolution: QVGA 320 × 240
Streaming: software JPEG conversion, quality 80
```

The firmware initially attempts hardware-JPEG VGA 640 × 480 and automatically falls back when the sensor returns `ESP_ERR_NOT_SUPPORTED`.

---

## 8. Power wiring

### Battery rail

A 3S battery provides approximately:

- 11.1 V nominal.
- 12.6 V when fully charged.

Battery power goes to:

- The motor-supply input of the physical left L298N.
- The motor-supply input of the physical right L298N.
- The input of the LM2596 buck converter.

### Regulated logic rail

Set the LM2596 output to **exactly 5.0 V before connecting electronics**.

The regulated 5 V rail powers:

- Main ESP32 5V/VIN input.
- ESP32-CAM 5V input.
- Pan servo VCC.
- Tilt servo VCC.
- L298N logic if the modules are configured for external regulated logic power.

### Ground

All grounds must be joined:

```text
Battery negative
LM2596 input/output negative
Main ESP32 GND
ESP32-CAM GND
Both L298N GND terminals
Both servo ground wires
```

Without a common ground, PWM, direction, UART and servo signals will be unreliable.

### L298N jumper distinction

- Remove the **ENA and ENB jumper caps** because ENA/ENB are driven by ESP32 PWM.
- The **5V-EN jumper** is different. Configure it consistently with the module's logic-power method.
- Do not feed external 5 V into an L298N 5V output while its onboard regulator is also driving that pin unless the specific module documentation permits it.

### USB warning

Avoid powering the main ESP32 VIN from the LM2596 and USB simultaneously during normal testing. For code upload, disconnect rover power from the ESP32 or otherwise ensure that two 5 V sources are not fighting each other.

---

## 9. Wi-Fi and network endpoints

Both ESP32 boards connect as Wi-Fi stations:

```text
SSID: CAR
Password: car123456
Band: 2.4 GHz
```

### Stable names

| Function | Address |
|---|---|
| Main controller | `http://rover.local/` |
| ESP32-CAM page | `http://rovercam.local/` |
| ESP32-CAM stream | `http://rovercam.local:81/stream` |
| Main WebSocket | `ws://rover.local/ws` |

### Numeric addresses

The phone hotspot assigns numeric addresses through DHCP, so they may change after a reconnect. The serial monitor prints the current addresses.

Example:

```text
Main control page (IP): http://192.168.129.176/
Camera page (IP)      : http://192.168.129.17/
Camera stream (IP)    : http://192.168.129.17:81/stream
```

If a phone or Windows cannot resolve `.local`, use these numeric addresses.

### HTTP endpoints

#### Main ESP32

| Endpoint | Purpose |
|---|---|
| `/` | Complete RC controller webpage |
| `/ws` | WebSocket movement and servo commands |
| `/camera-ip` | Returns the current camera host/IP |

#### ESP32-CAM

| Endpoint | Purpose |
|---|---|
| `/` | Camera diagnostic page |
| `:81/stream` | MJPEG camera stream |
| `/flash?value=0..255` | Set flash LED brightness |

---

## 10. Browser controls and command protocol

### Motor commands

| WebSocket command | Action |
|---|---|
| `F` | Forward |
| `B` | Backward |
| `L` | Turn left |
| `R` | Turn right |
| `S` | Stop |
| `K` | Keepalive |

Movement buttons use press-and-hold behavior. Releasing the pointer sends Stop.

### Servo commands

| Command example | Action |
|---|---|
| `P90` | Set pan to 90 degrees |
| `T90` | Set tilt to 90 degrees |

### Flash command

The browser sends an HTTP request directly to the ESP32-CAM:

```text
http://CAMERA_IP/flash?value=0..255
```

---

## 11. Motor-control behavior

The final controller uses:

| Setting | Value | Purpose |
|---|---:|---|
| PWM frequency | 12 kHz | Quiet and responsive motor enable PWM |
| PWM resolution | 8 bit | Duty range 0–255 |
| Start duty | 120 | Overcome motor starting friction |
| Full duty | 255 | Maximum commanded speed |
| Ramp increment | 12 | Smooth acceleration |
| Ramp interval | 12 ms | Acceleration timing |
| Direction dead time | 40 ms | Remove power before reversing the H-bridge |
| Command timeout | 1300 ms | Stop if movement commands stop arriving |

Safety behavior:

- Browser disconnect → Stop.
- Wi-Fi loss → Stop.
- Movement command timeout → Stop.
- Direction change → PWM is removed, 40 ms dead time is applied, then the new direction starts.

---

## 12. Serial-monitor information

Use **115200 baud**.

The main ESP32 prints:

- Wi-Fi connection state.
- Main controller IP and fixed name.
- Camera fixed endpoints.
- Camera numeric IP and stream endpoint after receiving `CAMIP`.
- Browser controller connection/disconnection events.
- PWM attachment errors.

`Controller connected: 192.168.x.x` means a phone or laptop browser opened the WebSocket. It is not another ESP32.

The ESP32-CAM prints:

- Sensor PID.
- Capture format and resolution.
- Current page and stream addresses.
- Camera IP announcements.
- Initialization or server errors.

Unreadable characters immediately at boot are normally ROM/UART startup output or a temporary baud mismatch. Readable application messages should follow at 115200 baud.

---

## 13. Upload settings

### Main ESP32

| Arduino IDE option | Setting |
|---|---|
| Board | ESP32 Dev Module |
| Partition scheme | Huge APP / 3 MB application |
| Serial speed | 115200 baud monitor |

Upload:

```text
Project Car Code/ESP32_Controller/ESP32_Controller.ino
```

### ESP32-CAM

| Arduino IDE option | Setting |
|---|---|
| Board | AI Thinker ESP32-CAM |
| Partition scheme | Huge APP / 3 MB application |
| Upload speed | 115200 for reliability; faster may work |
| Serial speed | 115200 baud monitor |

GPIO0 must be connected to GND only while entering download/upload mode. Remove GPIO0 from GND and reset the board after uploading so it boots normally.

Upload:

```text
Project Car Code/ESP32_CAM_Controller/ESP32_CAM_Controller.ino
```

---

## 14. Laptop face-recognition package

The complete laptop package is located at:

```text
install in laptop/
```

Run in this order:

1. `01_INSTALL_GPU.bat`
2. `02_CHECK_SETUP.bat`
3. `03_TEST_CAMERA.bat`
4. `04_CAPTURE_FACES.bat`
5. `05_RUN_RECOGNITION.bat`

The laptop configuration uses:

```text
http://rovercam.local:81/stream
```

If `.local` resolution fails, replace the stream URL in `install in laptop/config.json` with the numeric stream address printed by the main ESP32.

---

## 15. Fast troubleshooting

### Car moves in the wrong direction

Do not return to the original diagram's left/right labels. The final code contains tested side and polarity corrections. Verify that the correct final sketch was uploaded.

### One motor runs backwards

Identify the exact physical motor first. Reverse only that motor's software polarity or motor wires—not the entire rover direction.

### Control page connects and disconnects repeatedly

- Use one browser tab.
- Open the numeric main ESP32 address for testing.
- Keep the controlling device connected to `CAR`.
- Disable mobile-data switching/Wi-Fi Assist.
- Stop other camera stream viewers.
- If disconnection occurs only when motors/servos move, investigate power sag and electrical noise.

### Camera stream stutters

- Use only one stream client.
- Close the camera page before starting laptop recognition.
- The current sensor requires software JPEG conversion, which limits frame rate.

### Camera view appears zoomed

The webpage uses `object-fit: contain`, so it does not crop the frame. The narrow view comes from the sensor/lens or its QVGA mode. A compatible wide-angle hardware-JPEG camera module is the practical hardware solution.

### Tilt does not move

- Signal must go to GPIO4 on the main ESP32.
- Servo red → regulated 5 V.
- Servo brown/black → common GND.
- Do not connect tilt signal to ESP32-CAM GPIO4; that pin is its flash LED.

### Camera IP changes

This is normal DHCP behavior. Use `rovercam.local` or the current numeric endpoint printed by Serial Monitor.

---

## 16. Authoritative project files

| File | Purpose |
|---|---|
| `Project Car Code/ESP32_Controller/ESP32_Controller.ino` | Final main controller firmware |
| `Project Car Code/ESP32_CAM_Controller/ESP32_CAM_Controller.ino` | Final camera firmware |
| `install in laptop/` | Face-recognition laptop package |
| `Neural_Rover_Final_Project_Presentation.pptx` | Final presentation |
| `Neural_Rover_Report/` | LaTeX report source |

When documentation conflicts with the rover's working behavior, treat the two final `.ino` files and this document as the current source of truth.
