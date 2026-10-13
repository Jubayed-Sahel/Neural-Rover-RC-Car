# CSE499B: Fall Detection and Rover Dashboard

Planning baseline: 14 October 2026. The standalone CPU laptop test package is implemented under `laptop-test/`; dashboard and rover integration have not started. Real laptop performance and detection accuracy remain to be evaluated.

## Project scope

Build a stationary USB-camera fall-detection prototype and a shared dashboard for monitoring and manual rover control. The camera remains separate from the car. An operator can respond to a possible-fall alert by driving the rover; autonomous navigation and video from the rover's viewpoint are future scope.

Develop on the desktop (16 GB RAM, Intel Arc A770), but run and evaluate the complete demonstration on the ASUS VivoBook (Intel Core i5-8250U, 8 GB RAM, NVIDIA GeForce MX150 with 4 GB VRAM and Intel UHD 620). The demonstration must not depend on the desktop. Camera budget: BDT 2,500–3,000; proposed camera: A4Tech PK-910H, subject to purchase and testing.

## Mandatory laptop testing requirement

Initial package: `laptop-test/README.md`. It provides a CPU MediaPipe Lite pose test, live-camera and recorded-video modes, experimental temporal fall rules, and per-run performance/event logs. This establishes a benchmark starting point, not a validated detector.

Every recognition or detection module must support independent testing on the ASUS VivoBook (i5-8250U, 8 GB RAM, MX150 4 GB and Intel UHD 620). Desktop development or training is allowed, but deployment and inference must work on the laptop CPU without the Arc A770, a desktop connection, Cloudflare, or an ESP32 being present.

Provide two standalone test modes before dashboard integration:

- Live USB-webcam mode for checking capture, detection overlays, confidence, and alerts.
- Recorded-video mode for replaying the same evaluation clips and comparing model versions.

Both modes must use the same model, preprocessing, and temporal decision logic as the dashboard. Recorded-video evaluation must use source-video timestamps rather than processing speed to measure motion and event duration. Report inference FPS, frame age or processing latency, alert delay, and RAM usage. Include simple Windows setup and launch instructions, a CPU dependency set, model files or explicit download steps, and useful errors for a missing camera or model.

Expose camera index, input size, model selection, and processing interval through configuration. Add an option to disable recognition/detection while testing the car. Download model assets before offline tests; local inference must then continue without internet.

A module is not ready for integration until it starts on the laptop, processes both a webcam and recorded clips, and completes a representative session without crashing or accumulating delayed frames. Agree on measured performance targets after the first laptop benchmark; do not assume a frame rate. Test each later face, gesture, or object module under these same requirements.

## What the existing code already provides

`Project Car Code/ESP32_Controller/ESP32_Controller.ino` is the proposed integration target:

- Wi-Fi controller on port 80 with a WebSocket at `/ws`.
- Text commands `F`, `B`, `L`, `R`, and `S` for movement and stop.
- The current browser repeats held movement commands every 450 ms.
- A 1,300 ms movement-command timeout, stop on WebSocket disconnect, motor ramping, and 40 ms direction-change dead time.
- `K` is a connection keepalive, not a movement heartbeat.
- Pan and tilt commands (`P<angle>` and `T<angle>`), plus ESP32-CAM discovery.

Preserve the tested motor mapping, direction polarity, PWM configuration, and stop behavior. No firmware change is required for the first integration if this is the sketch currently installed.

An alternative sketch, `ESP32_Motor_Receiver.ino`, accepts UART packets rather than Wi-Fi commands. Confirm which sketch is actually installed before implementation. Do not switch sketches or wiring just to match this plan. The current `ESP32_CAM_Controller.ino` provides camera streaming and IP announcements; it does not itself provide a rover command endpoint.

The embedded controller page connects using `ws://` and loads the ESP32-CAM from a private HTTP address. Simply tunneling this existing page will not create the desired remote dashboard: an HTTPS browser needs a secure WebSocket and cannot rely on remote access to private camera addresses.

## Intended architecture

1. USB webcam feeds the demonstration laptop.
2. One capture worker reads frames; one inference worker estimates pose and evaluates movement.
3. A Python web application serves the dashboard, processed video, status, and alert history.
4. The phone talks only to that web application.
5. A server-side rover relay connects locally to `ws://<ESP32_IP>/ws`.
6. Cloudflare Tunnel exposes the laptop application through one HTTPS address.

The laptop and ESP32 join the phone's 2.4 GHz hotspot. The phone supplies internet for the tunnel. Verify that hotspot client isolation does not prevent laptop-to-ESP32 communication. Use a configurable numeric ESP32 IP if mDNS is unreliable.

Cloudflare carries browser traffic; camera processing and fall decisions remain on the laptop. Internet loss removes remote access but should not stop local detection. The camera is stationary, so the operator does not receive the car's viewpoint.

## Changes to implement

### New laptop application

Use FastAPI as the initial web backend, with OpenCV for capture and drawing. Keep the pose model behind an interchangeable interface; choose the model after a short CPU benchmark on the laptop. Do not make Intel GPU acceleration a requirement. Validate framework support before attempting desktop GPU acceleration; the existing CUDA installer does not support the Arc A770.

Proposed files, to create during implementation:

- `monitoring/app.py`: application lifecycle, routes, and dashboard serving.
- `monitoring/camera.py`: camera capture, timestamps, disconnect handling.
- `monitoring/pose.py`: pose-model adapter and preprocessing.
- `monitoring/fall_detector.py`: temporal state machine and confidence handling.
- `monitoring/rover.py`: WebSocket relay and command expiry.
- `monitoring/events.py`: local event storage, acknowledgement, and retention.
- `monitoring/templates/index.html` and `monitoring/static/`: dashboard.
- `monitoring/config.example.json`: camera index, ESP32 address, inference settings.
- `monitoring/requirements.txt`: tested CPU-capable dependencies.
- `monitoring/README.md`: Windows setup, operation, and troubleshooting.

Suggested application routes:

- `/`: dashboard.
- `/video`: processed MJPEG stream for the first prototype.
- `/api/status`: camera, model, rover, and detection status.
- `/api/events`: recent possible-fall events.
- `/api/events/<id>/ack`: acknowledge an event, without deleting it.
- `/ws/control`: browser-to-laptop driving connection.

Use relative HTTP URLs and select `ws://` locally or `wss://` on HTTPS. Never put the ESP32 private address in browser requests. Disable caching for video and live status. Use status polling or WebSockets initially; Quick Tunnels do not support SSE.

### Dashboard

Show the processed stationary-camera feed, possible-fall state, timestamped alerts, acknowledgement button, press-and-hold driving controls, STOP, and connection indicators. Label the feed "Stationary monitoring camera". Hide camera flash and pan/tilt controls from this dashboard unless the corresponding hardware is deliberately retained.

An alert must not automatically move the rover. Manual dispatch is the initial scope. Show "Command sent" rather than claiming confirmed movement: the existing protocol does not return motor-position feedback.

### Rover relay and fail-safe behavior

Forward only allowed movement commands using one active control session. Preserve the existing repeat interval as a starting point and benchmark internet delay against the 1,300 ms firmware timeout. Do not lengthen the timeout merely to conceal tunnel latency.

The relay must expire its local movement command when fresh browser input stops. It must not repeat the last direction indefinitely while keeping the ESP32 connection alive. Send `S` on release, browser disconnect, session expiry, relay shutdown, or control-owner change. Reconnection starts stopped; do not replay queued movement commands. Prioritize STOP over stale directions.

Keep capture/inference work outside the control event loop and keep only recent frames in bounded buffers. Confirm that processing overload cannot prevent command expiry. Protect the remote control page with authentication and validate WebSocket origins. Test first with wheels raised.

## Fall-detection approach

Start with one person in a controlled indoor area. Use a lightweight pretrained pose estimator and a transparent temporal baseline before attempting custom training.

Track shoulders, hips, torso direction, relative body height, and downward motion over timestamped frames. Normalize measurements to person size; do not use raw pixel thresholds across different camera distances.

Candidate states: `NORMAL`, `POSSIBLE_FALL`, `POST_FALL`, and `UNKNOWN`. Combine rapid descent, posture change, and sustained low posture. A horizontal person alone is insufficient evidence. Low-confidence or missing body points become `UNKNOWN`, not a confident normal or fall result. Camera disconnection must produce a visible unavailable state. A person lying down when the application starts is not evidence of an observed fall transition.

Keep alerts latched until acknowledged, avoid duplicate event storms, and log the reasons for each decision. Thresholds and duration windows remain configurable and must be calibrated on development recordings. They are not yet validated.

## Camera and preprocessing

### Camera selection update

Budget remains BDT 2,500–3,000. The original candidate was the A4Tech PK-910H. After comparing specifications for ground-level full-body framing, the revised recommendation is Rapoo C260 if available within the full budget. No purchase or final acceptance of the revised model has been confirmed.

A4Tech lists 1080p, fixed focus from 60 cm onward, and a 70-degree viewing angle. Rapoo lists 1080p, fixed focus, and a 95-degree diagonal field of view. These angle specifications are not necessarily measured on the same axis. The C260's advertised wider coverage is a reason to test it for this use, not proof of better image quality or fall accuracy. A wider view also reduces face size at a given distance and resolution.

Star Tech listings checked on 14 October 2026 showed PK-910H at BDT 2,499 and C260 at BDT 2,999; confirm current price, stock, actual hardware version, and full-body framing before purchase. Neither camera guarantees ground-level fall detection.

- A4Tech manufacturer: https://www.a4tech.com/product.aspx?id=36
- A4Tech retailer: https://www.startech.com.bd/a4-tech-pk-910h-1080p-webcam
- Rapoo manufacturer: https://rapoo.com/en/product/C260
- Rapoo retailer: https://www.startech.com.bd/rapoo-c260-usb-fhd-webcam

Planned-system illustration: [Fall detection and rover architecture](Project%20Files/CSE499B_Fall_Detection_Architecture.png). It illustrates the target architecture; dashboard and tunnel integration are not yet implemented.

### Rover-height viewpoint requirement

Confirmed requirement: detect human falls from a camera near ground level, representing the rover viewpoint. Keep the camera separate in the current prototype, but evaluate it at the intended rover mounting height and angle. This is a required evaluation condition, not a completed capability.

Mount the separate test camera at the proposed rover camera height and angle. Record those measurements, subject distance, floor coverage, and occlusions. Evaluate falls and ordinary activities from that viewpoint using held-out recordings. Desk-height performance cannot establish rover-height performance. Include low-angle footage during calibration/training, with separate sessions for final evaluation; do not assume a public dataset matches this geometry.

Perspective can change apparent torso orientation and landmark visibility. The current baseline uses 2D landmarks and requires visible ankles and knees; it may fail from ground level or after occlusion. Measure those failures before deciding whether to adapt the rules, change the pose model, or train a temporal classifier. If a camera is later mounted on a moving rover, test camera-motion false alarms separately and begin with detection while parked. Reliable moving-camera operation is additional scope, not validated by a stationary low-camera test. Define numerical recall, false-alarm, and alert-delay targets with the supervisor rather than promising detection of every fall.

- Mount the webcam securely so the whole person and surrounding floor remain visible.
- Test available capture modes rather than assuming the advertised mode is delivered by the driver.
- Start inference at a modest resolution and increase only when measured accuracy requires it.
- Preserve aspect ratio: 1920 × 1080 can resize to 640 × 360; use letterboxing if the model requires another shape.
- Follow the selected model's colour order and normalization requirements.
- Keep frame timestamps and inference timestamps. Use elapsed time, not frame count, for motion and duration checks.
- Avoid aggressive image enhancement until it demonstrates a measurable benefit.
- Keep display and inference rates configurable; discard old frames instead of building a delayed video queue.

## Development phases and completion checks

### 1. Preserve and verify the working car

Record the installed sketch, current wiring, dependencies, ESP32 IP, and successful direct control. Check release-to-stop, disconnect stop, and timeout. Leave firmware unchanged during this phase.

### 2. Camera and laptop benchmark

Verify the purchased webcam and test full-body coverage. Benchmark candidate pose models on the laptop CPU. Record processed FPS, frame age, CPU/RAM use, pose reliability, and model startup time. Select the simplest model that supports the required temporal observations; no FPS promise until measured.

### 3. Local fall prototype

Implement capture, pose, temporal rules, and event logging. Use recorded clips for repeatable checks before live demonstrations. Make uncertain tracking and camera loss visible.

### 4. Unified local dashboard

Serve annotated video and alerts, then connect the rover relay. Verify that alert handling and video load do not interfere with STOP. Confirm one-control-session behavior and stopped reconnections.

### 5. Cloudflare access

Install `cloudflared` on the demonstration laptop. With the application running on port 5000, test:

```powershell
cloudflared tunnel --url http://localhost:5000
```

Use the generated HTTPS address on the phone. A Quick Tunnel has a temporary hostname and no uptime guarantee. Add access protection before exposing motor controls. Test remote video quality and latency; reduce stream resolution/frame rate if hotspot upload is limiting. Keep a local-access demonstration fallback.

### 6. Evaluation and demonstration package

Test on the actual laptop, webcam, and hotspot. Package tested dependencies, downloaded model assets with applicable licensing notes, configuration instructions, and launch commands. Do not require model downloads during the demonstration.

## Evaluation protocol

### First laptop benchmark received

Source: `laptop-test/results/20261014_025956_562143/summary.json`, pulled from GitHub commit `57c725f`.

- A 60.4-second live-camera CPU run completed without a reported error.
- Camera output was 640 × 480 despite the requested 1280 × 720 capture size.
- Processed 435 frames at 7.2 frames/second. The configuration intentionally spaces inference by at least 0.1 seconds; this is not an unrestricted model-speed benchmark.
- Mean model inference was 28.79 ms; p95 frame age after capture retrieval was 43 ms. Driver buffering and complete remote-dashboard latency are not measured.
- Peak sampled application RAM was 206.6 MB, not total laptop RAM.
- Full-body reliability fraction was 0.0: no processed frame satisfied the baseline's required landmark confidence and in-frame checks.
- Zero fall events do not demonstrate successful detection or low false-alarm rates, because the fall baseline had no usable full-body observations.

Only the summary was pushed; frame-level metrics, event logs, and screenshots were not supplied. It cannot establish whether pose was absent, legs were out of frame, or landmark confidence was insufficient. Next test: full-body framing and ordinary movements for five minutes, preserving `metrics.csv` and one annotated snapshot for diagnosis. Do not optimize GPU use or lower confidence thresholds until tracking validity is understood.

The user subsequently confirmed sitting close to the laptop during this run. This is consistent with cropped lower-body landmarks and explains why it was not a full-body evaluation; an annotated snapshot is still needed to inspect tracking. For the next run, position the camera securely to include shoulders, hips, knees, ankles, and surrounding floor; check that "Full body: visible" appears, test ordinary movements, press S for a snapshot, and Q to finish. No staged fall is needed for this framing check.

Include safely staged falls or suitable public recordings and ordinary activities: walking, bending, sitting rapidly, kneeling, picking up objects, intentional lying down, and getting up. Include different distances, lighting, partial occlusion, empty frames, and camera interruption.

Separate development/calibration and held-out test recordings by person or recording session where practical. Do not place adjacent frames from the same clip in both sets. Report event-level precision and recall, missed falls, false alarms per hour of ordinary activity, alert delay, and laptop processing performance. Define event-matching and timing rules before final testing.

Run integration checks for browser closure while driving, hotspot/internet loss, ESP32 disconnect, laptop sleep, inference overload, stale video, and repeated reconnects. Firmware timeout and the relay must stop movement without depending on the detection model.

## Future changes of recognition task

Keep camera capture, dashboard, rover relay, and event storage independent of the detector. A face-recognition, gesture, or object-detection module can later replace or supplement fall detection without replacing the webcam. Benchmark each module separately before running several together.

Future hardware scope: camera on a stronger chassis, suitable power system, and onboard computer such as a Raspberry Pi. That requires a separate performance and mechanical evaluation.

## Repository cleanup and retained references

- Removed `sample-640x480.png`: a generated conversational illustration, not project input.
- Retained all three Arduino sketches: installed firmware must be confirmed before retiring alternatives.
- Retained the report, presentation, proposal, diagrams, and `workplan.html` as academic/history references.
- Marked `install in laptop/` as legacy. It is an ESP32-CAM/InsightFace face-recognition package with NVIDIA-specific setup assumptions, not the fall-detection application. Keep it as reference for a possible later recognition change.
- Retained the existing Python environment; its contents have not been established as disposable.
- Existing Git modifications and deletions were present before this planning task and were not reset.

## References

- Cloudflare Quick Tunnel setup and limitations: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
- Cloudflare Tunnel connection model: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/

## Outstanding decisions

Confirm the installed ESP32 sketch, purchase/test the webcam, select the pose model through laptop benchmarking, and agree on the evaluated fall scenarios. These do not block documenting the architecture but do block making performance or detection-accuracy claims.
