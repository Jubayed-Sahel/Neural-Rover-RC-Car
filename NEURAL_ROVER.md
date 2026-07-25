# Neural Rover — Elderly Monitoring Rover + Chatbot

## Core Project

An **RC car** controlled via **phone** with an **ESP32-CAM** on a **pan-tilt + raised mount** that patrols elderly care facilities:

1. The phone creates the **2.4 GHz hotspot `CAR`**, forming the rover's local network
2. The phone opens the rover control webpage to drive forward, reverse, left, right, and stop
3. The **ESP32-CAM** captures live video and provides an MJPEG stream over the hotspot
4. A **GPU laptop connected to the same hotspot** receives the live stream
5. Face models are trained and executed on the laptop rather than on the ESP32-CAM
6. **InsightFace (ArcFace)** detects and recognizes enrolled residents in real time
7. **YOLO-pose / MediaPipe Pose** detects falls or unusual posture
8. Detection events are logged with timestamp, resident name, location, and pose status

The ESP32-CAM is responsible for camera capture, video streaming, and the control
webpage. Driving commands are passed to the main ESP32 through UART. The main
ESP32 remains responsible for the motor drivers, motors, and future pan-tilt
servos. Internet access is optional for local control and recognition; it is only
required for cloud services such as Telegram or a cloud-hosted LLM.

### Alert Scenarios
- **Unknown person on floor** → fall detected → immediate Telegram alert to caregivers
- **Resident out of usual area** (e.g., Mr. Ali in east wing at 2 AM) → alert
- **No sighting of a resident for X hours** → absence alert

### What the Rover Checks
- Face recognition → "Mrs. Khan, Room 204"
- Pose estimation → standing safely / lying on floor / stumbling
- Location tracking → which zone the person is in

## Chatbot (Telegram)

A **Telegram chatbot** lets caregivers ask about residents using an LLM:

### Example Queries
- "Who hasn't been seen in the last 2 hours?"
- "Where was Mr. Hassan last detected?"
- "Show me all fall events from today"
- "List residents currently in the garden area"
- "Was Mrs. Khan checked on this morning?"

## Architecture

```
                         Phone
                Hotspot `CAR` + controls
                           │
                           ▼
                   ESP32-CAM Server
                  ┌────────┴─────────┐
                  │                  │
          MJPEG live stream     UART commands
                  │                  │
                  ▼                  ▼
          GPU Laptop (Python)    Main ESP32
          ┌───────┴────────┐          │
          │ Face Recognition│     Two L298Ns
          │ Pose Detection  │          │
          └───────┬────────┘      Four Motors
                  │
          Event Log / Database
                  │
          ┌───────┴────────┐
          │ Telegram Alerts │
          │ Telegram Chatbot│
          │ LLM Answers     │
          └─────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Vehicle | RC car (phone-controlled) |
| Camera | ESP32-CAM (OV2640) on pan-tilt + raised mount |
| Local Network | Phone hotspot `CAR` (2.4 GHz) |
| Video Transport | ESP32-CAM MJPEG stream over local Wi-Fi |
| AI Processing | GPU laptop running Python |
| Motor Controller | ESP32 Dev Board connected to ESP32-CAM through UART |
| Face Recognition | InsightFace (ArcFace) |
| Pose Detection | YOLO-pose / MediaPipe Pose |
| LLM Cloud | Gemini API / Ollama (local) |
| Chat Interface | Telegram Bot |
