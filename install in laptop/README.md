# Neural Rover laptop face recognition

This folder receives the ESP32-CAM MJPEG stream and runs InsightFace `buffalo_l` on the laptop. The ESP32 boards do not run the recognition model.

## Connection

All three devices must use the same `CAR` 2.4 GHz hotspot:

```text
ESP32-CAM -- http://CAMERA_IP:81/stream --> Laptop/buffalo_l
Main ESP32 --------------------------------> Motors and pan/tilt
```

The configured stable stream name is `http://rovercam.local:81/stream`. The camera still receives a numeric address from hotspot DHCP, but its `.local` name stays constant. If Windows cannot resolve mDNS, replace `stream_url` in `config.json` with the numeric camera endpoint printed by the main ESP32 serial monitor.

Do not simultaneously open the ESP32-CAM stream on the phone and laptop. RGB565-to-JPEG conversion is already demanding for the camera board, and multiple viewers can cause stuttering.

## First-time setup

1. Update the NVIDIA GeForce driver if necessary.
2. Double-click `01_INSTALL_GPU.bat`.
3. Double-click `02_CHECK_SETUP.bat`.

The setup check must list `CUDAExecutionProvider`. CPU fallback remains available if CUDA cannot load.

The MX150 is a Pascal GPU. The installer deliberately restricts ONNX Runtime to versions earlier than 1.27 because newer default packages use CUDA 13, which does not support Pascal GPUs.

## Test and use

1. `03_TEST_CAMERA.bat` checks the MJPEG endpoint without loading InsightFace.
2. `04_CAPTURE_FACES.bat` collects reference images.
3. `05_RUN_RECOGNITION.bat` starts live recognition.

During capture:

- Press **SPACE** to save an image.
- Capture at least eight clear images per person.
- Include frontal, slightly-left and slightly-right poses.
- Use good lighting and only one face in the image.
- Press **Q** to exit.

Reference photographs are stored under `known_faces/Person_Name/`.

## Recognition controls

- **Q**: quit
- **S**: save the currently displayed recognition frame under `snapshots/`

Recognition events are stored in `logs/recognition_log.csv`. A repeated identity is logged at most once every ten seconds.

## Accuracy settings

Settings are stored in `config.json`:

- `recognition_threshold`: starts at `0.45`. Increase it to reduce false matches; decrease it if known people are regularly marked Unknown. Calibrate using your own users.
- `detection_size`: `320` is faster. Try `640` if distant faces are not detected, but it will not recreate missing image detail.
- `minimum_face_width`: faces narrower than this value are labelled Too small instead of being trusted.
- `inference_interval_seconds`: increase this if the MX150 is overloaded.

## Troubleshooting

### Camera does not open

- Open the stream URL in a laptop browser.
- Verify the laptop is connected to `CAR`.
- Check the latest camera IP in the ESP32-CAM serial output.
- Close every other webpage using the camera stream.

### CUDA is missing

Run `02_CHECK_SETUP.bat`. If `CUDAExecutionProvider` is absent:

- Install the latest NVIDIA driver that supports the MX150.
- Run `01_INSTALL_GPU.bat` again.
- Do not install both `onnxruntime` and `onnxruntime-gpu` in this environment.

### InsightFace installation fails

Install Microsoft Visual C++ Redistributable/Build Tools and rerun the installer. The exact error is retained in the console.

### Model download

The first use downloads `buffalo_l` to the user InsightFace model directory. Internet is only required for installation and the first model download.

## Privacy and licensing

Face images and embeddings are biometric data. Collect them with consent and protect the `known_faces`, `logs`, and `snapshots` folders. InsightFace source code and its pretrained models have different licensing terms; the supplied pretrained model is intended for non-commercial research unless separately licensed.
