# Laptop pose and fall-detection test

This package tests CPU pose inference and an experimental temporal fall baseline on the ASUS i5/8 GB laptop. It does not connect to the car or Cloudflare. It is not yet a validated fall detector.

## What we are testing

1. Whether the model tracks shoulders, hips, knees, and ankles reliably in the actual room.
2. Whether CPU inference is responsive and RAM use remains manageable during a five-minute run.
3. Whether normal movements trigger false alarms or cause tracking loss.
4. Whether the experimental descent/posture rules can identify candidate falls in safe recordings.

A working camera proves only that video capture works. It does not establish model speed, full-body tracking quality, or detection accuracy.

## Run on the laptop

1. Copy this entire folder to the laptop and extract it if received as a ZIP. Do not run inside the ZIP preview.
2. Install **64-bit Python 3.12** from https://www.python.org/downloads/windows/ with the Python launcher enabled. Python 3.14 is not the version selected for this package.
3. Double-click `01_INSTALL.bat`. Internet is needed for dependencies; the ZIP includes the official Google Lite pose model, and the installer can download it again if missing. The installation uses its own `.venv`; no NVIDIA driver or GPU package is needed. `requirements-lock.txt` records the dependency versions verified during packaging; `requirements.txt` lists the direct dependencies.
4. Close other apps using the camera and double-click `02_TEST_LIVE.bat`.
5. Use the built-in webcam initially. Stand far enough away for your whole body and some floor to be visible. Camera index 0 is the default; change `camera_index` in `config.json` if an external camera is selected instead.
6. Press **Q** to finish. Each run saves a new folder under `results/`.

After installation and model download, local tests do not require internet. Package dependencies may have their own telemetry behavior; this application does not upload video or results.

## A useful first session

Run for approximately five minutes. Spend time standing, walking sideways, sitting, standing up, bending, and picking something up. Watch whether the full-body indicator remains reliable. Temporarily move out of view: status should become UNKNOWN. Do not perform a dangerous fall to test this package. Use suitable recorded clips or safely supervised staged motion on a padded surface later.

The first run measures pose tracking and everyday false alarms. Absence of an alert does not establish fall-detection recall. Aim initially for responsive body tracking with no growing delay; agree on a numerical performance target after seeing the laptop results.

Keyboard shortcuts: **Q/Esc** quit, **A** acknowledge/reset the latched alert, **S** save an annotated snapshot. Acknowledgement is recorded in the event log. UNKNOWN means insufficient full-body evidence, not a safe situation.

## Recorded video

Drag an MP4 or AVI onto `03_TEST_VIDEO.bat`. Both live and recorded tests use the same preprocessing and detector. Video motion is measured using media timestamps, with index/FPS fallback for constant-rate recordings. For unusual or broken timestamp metadata, convert to a constant-frame-rate MP4 first.

For a maximum-throughput recorded-video benchmark, open a terminal in this folder:

```powershell
.venv\Scripts\python.exe test_pose.py --video "C:\path\clip.mp4" --headless
```

For a timed live session or capture-only comparison:

```powershell
.venv\Scripts\python.exe test_pose.py --duration 300
.venv\Scripts\python.exe test_pose.py --no-detection --duration 60
```

## Results to send back

Send `summary.json` from the latest `results/` folder and describe any missing body points, visible lag, or false alarms. `metrics.csv` contains per-frame timing, sampled process RAM, full-body validity, and state. `events.json` records alerts and acknowledgement. Snapshots are saved only when S is pressed; no video recording is made automatically.

Mean inference time measures model execution. Frame age measures time from OpenCV frame retrieval to output processing, so it does not include unobservable camera-driver buffering. Live capture retains only the newest frame. RAM is the application process's sampled RAM, not total system RAM. Displayed video is reduced to preserve aspect ratio. At the default 0.1-second inference interval, processed FPS is intentionally capped around 10 even if the model is faster; reduce the interval to benchmark a higher rate.

Confirmation delay is measured from the rule's candidate transition. True fall-onset delay, missed falls, precision, and false alarms per hour require labelled recordings and manual evaluation; this package does not claim to calculate accuracy automatically.

## Model and limitations

Uses MediaPipe Pose Landmarker Lite on CPU. The pretrained model estimates pose; it is not a trained fall-classification model. The separate rules look for an upright-to-horizontal transition, downward hip movement relative to body size, and sustained low posture. Defaults are starting values, not calibrated thresholds. Fast intentional lying down can still trigger an alert. Some real falls may be missed. This is a one-person test; multiple people, perspective changes, obscured legs, or poor lighting can invalidate results.

The default requires visible shoulders, hips, knees, and ankles. This is intentionally conservative: a face-only webcam view cannot support this baseline. Full-body visibility may require moving the laptop or later buying an external webcam and stand.

Model path, input width, visibility threshold, inference interval, and temporal thresholds are configurable in `config.json`. A long tracking gap resets transition evidence. Alerts stay latched until acknowledgement; missing tracking still shows UNKNOWN. Capture-only mode does not run the model.

## Troubleshooting

- Install fails: keep the console error; check that Python 3.12 is installed and internet is available.
- Camera cannot open: close Camera/Teams/Zoom, allow desktop camera access in Windows Settings, and try camera index 1.
- Model missing/corrupt: rerun installation; for a corrupt file, remove only `models/pose_landmarker_lite.task` and rerun.
- Red/UNKNOWN state despite visible person: improve lighting and full-body framing before lowering confidence thresholds.
- Slow tracking: close heavy apps; reduce `input_width` to 480 or increase the processing interval. Re-test reliability afterward.

## Sources and model provenance

- MediaPipe Python guide: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python
- Model overview and licensing references: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/index
- Official model URL: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
- MediaPipe 0.10.21 package: https://pypi.org/project/mediapipe/0.10.21/

The installer prints the downloaded model SHA256 for provenance. Review the upstream model and dependency terms before distributing a final project.
