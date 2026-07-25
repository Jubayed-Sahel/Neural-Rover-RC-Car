# Neural Rover — Elderly Monitoring Rover + Chatbot

## Core Project

An **RC car** controlled via **phone** with an **ESP32-CAM** on a **pan-tilt + raised mount** that patrols elderly care facilities:

1. **Phone app** controls the rover remotely (forward, reverse, steer)
2. **ESP32-CAM** captures live video as the rover patrols hallways and common areas
3. **Video streamed over Wi-Fi** to a GPU laptop
4. **InsightFace (ArcFace)** detects and recognizes residents in real-time
5. **YOLO-pose / MediaPipe Pose** detects falls or unusual posture
6. Detection events logged with timestamp, resident name, location, and pose status

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
Phone ──controls──▶ RC Rover (ESP32-CAM + pan-tilt + raised mount)
                           │
                    MJPEG stream over Wi-Fi
                           ▼
                     GPU Laptop (Python)
                           │
                    ┌──────┴────────┐
                    │ Face Detection│
                    │ (InsightFace) │
                    └──────┬────────┘
                           │
                    ┌──────┴────────┐
                    │ Pose Check    │
                    │ (YOLO-pose)   │
                    └──────┬────────┘
                            │
                     ┌──────┴──────────┐
                     ▼                 
               Telegram Alert          
               (timely action)  

                    Caregiver
                        │
                  Telegram Chatbot
                        │
                 ┌──────┴──────┐
                 │  LLM        │
                 │  Answer     │
                 └─────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Vehicle | RC car (phone-controlled) |
| Camera | ESP32-CAM (OV2640) on pan-tilt + raised mount |
| Microcontroller | ESP32 Dev Board |
| Face Recognition | InsightFace (ArcFace) |
| Pose Detection | YOLO-pose / MediaPipe Pose |
| LLM Cloud | Gemini API / Ollama (local) |
| Chat Interface | Telegram Bot |
