# Neural Rover RC Car

> CSE499B planning: see [CSE499B_PLAN.md](CSE499B_PLAN.md) for the stationary USB-camera fall-detection dashboard and Cloudflare integration. The Arduino firmware remains the working car baseline.

<p align="center">
  <strong>A Wi-Fi-controlled four-wheel rover with live ESP32-CAM video, pan–tilt control, and fail-safe motor handling.</strong>
</p>

<p align="center">
  <img alt="Project status" src="https://img.shields.io/badge/CSE499A-complete-2ea44f">
  <img alt="Platform" src="https://img.shields.io/badge/platform-ESP32-E7352C">
  <img alt="Framework" src="https://img.shields.io/badge/framework-Arduino-00979D">
  <img alt="Control" src="https://img.shields.io/badge/control-WebSocket-2463EB">
</p>

<p align="center">
  <img src="Project%20Files/Neural%20Rover%20Prototype.png" alt="Neural Rover RC Car prototype" width="900">
</p>

<p align="center"><em>Final four-wheel Neural Rover prototype with ESP32-CAM, pan-tilt mount, and onboard control electronics.</em></p>

## Overview

Neural Rover RC Car is a complete CSE499A embedded-systems project built around two ESP32 boards:

- A **30-pin ESP32** hosts the mobile-friendly controller, handles WebSocket commands, drives four motors through two L298N modules, controls the pan–tilt servos, and applies automatic stopping.
- An **ESP32-CAM** captures and streams live video, controls its flash LED, and reports its current IP address to the main ESP32 through UART.

Both boards join the same 2.4 GHz network. The user drives the rover, views the camera, aims the pan–tilt mount, and adjusts the camera light from one browser page.

> [!IMPORTANT]
> The final firmware contains tested motor-side and polarity corrections. Follow the pin map in this README or in [`RC_CAR_COMPLETE_INFORMATION.md`](RC_CAR_COMPLETE_INFORMATION.md), not an older circuit label.

## Features

- Responsive press-and-hold forward, backward, left, right, and stop controls
- Persistent WebSocket control with automatic reconnection
- Live ESP32-CAM stream embedded in the main controller page
- Independent pan and tilt controls
- Camera flash/illumination control
- Smooth motor ramp to full power
- Safe 40 ms dead time before motor direction reversal
- Automatic stop on command timeout, browser disconnect, or Wi-Fi loss
- UART-based camera IP discovery
- Fixed mDNS names with numeric-IP fallback
- Separate battery motor rail and regulated 5 V logic rail

## System Architecture

<p align="center">
  <img src="Project%20Files/Neural%20Rover%20Architecture%20Premium.png" alt="Neural Rover system architecture" width="900">
</p>

```text
Phone / laptop browser
          │
          │ Wi-Fi: CAR (2.4 GHz)
          ▼
   Main ESP32 ───── PWM + direction ─────► Two L298N ─────► Four motors
       │   │
       │   └──── 50 Hz PWM ──────────────► Pan + tilt servos
       │
       └──── UART2 camera discovery ◄────► ESP32-CAM ─────► MJPEG stream

3S battery ─────► L298N motor supply
     │
     └────► LM2596 set to 5.0 V ─────► ESP32 boards + servos

All modules share a common ground.
```

## Hardware

| Quantity | Component | Function |
|---:|---|---|
| 1 | 30-pin ESP32 development board | Main controller and web server |
| 1 | AI-Thinker-style ESP32-CAM | Live camera stream and flash LED |
| 2 | L298N dual H-bridge modules | Four reversible motor channels |
| 4 | DC geared motors | Rover movement |
| 2 | SG90-style servos | Camera pan and tilt |
| 1 | LM2596 buck converter | Regulated 5.0 V logic/servo supply |
| 1 | 3S battery | Motor and system input power |
| 1 | Four-wheel chassis | Mechanical platform |

## Final Main-ESP32 Pin Map

### Left-side L298N

| Function | GPIO | Physical connection |
|---|---:|---|
| Front-left PWM | 32 | ENA |
| Front-left direction | 23, 22 | IN1, IN2 |
| Rear-left direction | 21, 19 | IN3, IN4 |
| Rear-left PWM | 18 | ENB |

- OUT1/OUT2 → front-left motor
- OUT3/OUT4 → rear-left motor
- The front-left polarity correction is already handled in the final firmware.

### Right-side L298N

| Function | GPIO | Physical connection |
|---|---:|---|
| Front-right PWM | 25 | ENA |
| Front-right direction | 26, 27 | IN1, IN2 |
| Rear-right direction | 14, 12 | IN3, IN4 |
| Rear-right PWM | 33 | ENB |

- OUT1/OUT2 → front-right motor
- OUT3/OUT4 → rear-right motor

### Servos and UART

| Function | Main ESP32 | Connected device |
|---|---:|---|
| Pan signal | GPIO13 | Pan servo signal |
| Tilt signal | GPIO4 | Tilt servo signal |
| Camera RX2 | GPIO16 | ESP32-CAM U0T/TX0 |
| Camera TX2 | GPIO17 | ESP32-CAM U0R/RX0 |

UART TX and RX must cross, and the two boards must share ground.

## Power Wiring

```text
3S battery positive
├── Left L298N motor-supply input
├── Right L298N motor-supply input
└── LM2596 input

LM2596 output, adjusted to exactly 5.0 V
├── Main ESP32 5V/VIN
├── ESP32-CAM 5V
├── Pan servo VCC
└── Tilt servo VCC
```

> [!CAUTION]
> Remove the L298N **ENA and ENB jumper caps** because these pins receive ESP32 PWM. The **5V-EN** jumper is different and must match the selected L298N logic-power method. Avoid powering an ESP32 from USB and the LM2596 5 V output at the same time unless the board's power-path design explicitly allows it.

## Software Requirements

- [Arduino IDE](https://www.arduino.cc/en/software)
- Espressif ESP32 board package
- `AsyncTCP`
- `ESPAsyncWebServer`
- `esp_camera` supplied with the ESP32 Arduino core

## Uploading the Firmware

### 1. Main ESP32

Open [`Project Car Code/ESP32_Controller/ESP32_Controller.ino`](Project%20Car%20Code/ESP32_Controller/ESP32_Controller.ino).

Recommended Arduino IDE settings:

| Setting | Value |
|---|---|
| Board | ESP32 Dev Module |
| Partition scheme | Huge APP / 3 MB application |
| Serial Monitor | 115200 baud |

### 2. ESP32-CAM

Open [`Project Car Code/ESP32_CAM_Controller/ESP32_CAM_Controller.ino`](Project%20Car%20Code/ESP32_CAM_Controller/ESP32_CAM_Controller.ino).

Recommended Arduino IDE settings:

| Setting | Value |
|---|---|
| Board | AI Thinker ESP32-CAM |
| Partition scheme | Huge APP / 3 MB application |
| Upload speed | 115200 for reliability |
| Serial Monitor | 115200 baud |

Ground ESP32-CAM GPIO0 only while entering upload mode. After uploading, disconnect GPIO0 from ground and reset the board for normal boot.

## Network Configuration

The current working firmware uses:

```text
SSID: CAR
Password: car123456
Band: 2.4 GHz
```

Change these constants in both sketches if a different network is required.

| Service | Preferred address |
|---|---|
| Main controller | `http://rover.local/` |
| Main WebSocket | `ws://rover.local/ws` |
| Camera page | `http://rovercam.local/` |
| Camera stream | `http://rovercam.local:81/stream` |

The hotspot assigns numeric addresses through DHCP. If `.local` names do not resolve, use the IP addresses printed in Serial Monitor.

## Control Protocol

| Message | Action |
|---|---|
| `F` | Forward |
| `B` | Backward |
| `L` | Turn left |
| `R` | Turn right |
| `S` | Stop |
| `K` | Keepalive |
| `P0` … `P180` | Pan angle |
| `T0` … `T180` | Tilt angle |

The browser sends Stop when a movement button is released. The controller also stops the motors if valid commands become stale.

## Camera Behavior

The firmware first attempts VGA hardware-JPEG capture. The installed sensor reports that hardware JPEG is unsupported, so the tested fallback is:

```text
Capture format: RGB565
Resolution: QVGA 320 × 240
Streaming: software JPEG conversion
JPEG quality: 80
```

Use one stream viewer at a time for the most stable result.

## Repository Structure

```text
CSE499/
├── Project Car Code/
│   ├── ESP32_Controller/          # Final main-controller firmware
│   ├── ESP32_CAM_Controller/      # Final camera firmware
│   └── ESP32_Motor_Receiver/      # Earlier UART receiver experiment
├── Project Files/                 # Diagrams and supporting documentation
├── IEEE_499A_Report/              # Final five-page IEEE report
├── install in laptop/             # Optional laptop-side computer-vision tools
├── RC_CAR_COMPLETE_INFORMATION.md # Complete tested build reference
├── NEURAL_ROVER.md                # Project concept and development notes
└── workplan.html                  # CSE499 workplan
```

## Verified CSE499A Status

The following project tasks are complete:

- Chassis assembly and four-motor installation
- Two-driver wiring and final motor-orientation correction
- Browser and WebSocket control
- Motor ramp, timeout, disconnect stop, and reversal dead time
- ESP32-CAM live streaming
- Camera IP discovery over UART
- Pan, tilt, and camera-light controls
- Integrated power wiring and common-ground verification
- Final system testing, documentation, presentation, and IEEE report

## Documentation

- [Complete working configuration](RC_CAR_COMPLETE_INFORMATION.md)
- [Project overview and development notes](NEURAL_ROVER.md)
- [Final IEEE CSE499A report](IEEE_499A_Report/Neural_Rover_IEEE_499A_Report_Final.pdf)
- [Full project diagram](Project%20Files/Neural%20Rover%20Full%20Project%20Diagram.png)
- [ESP32-CAM upload diagram](Project%20Files/ESP32-CAM%20Code%20Upload%20Diagram.jpeg)

## Troubleshooting

- **Page opens but controls disconnect:** use one browser tab, remain connected to `CAR`, and try the numeric controller IP.
- **ESP32 resets when motors start:** check battery charge, LM2596 output, common ground, motor noise, and supply wiring.
- **A wheel runs backward:** upload the final controller sketch before changing wires; it already contains the tested polarity correction.
- **Camera stays in download mode:** remove GPIO0 from ground and reset the ESP32-CAM.
- **Camera stream stutters:** close other stream viewers; RGB565-to-JPEG conversion is processor-intensive.
- **Tilt does not move:** connect the tilt signal to GPIO4 on the main ESP32, not GPIO4 on the ESP32-CAM.

## Repository Ownership

**Owner and maintainer:** [Jubayed Ahmed Sahel](https://github.com/Jubayed-Sahel)  
**Academic supervisor:** Dr. K. M. A. Salam  
**Course:** CSE499A

Project-specific firmware and documentation in this repository are maintained by J. A. Sahel.
