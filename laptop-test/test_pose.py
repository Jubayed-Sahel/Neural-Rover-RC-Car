"""CPU pose benchmark and experimental fall baseline. No rover/network required."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import platform
import sys
import threading
import time

from fall_detector import FallDetector, observation_from_landmarks

ROOT = Path(__file__).resolve().parent
EDGES = ((11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),
         (23,24),(23,25),(25,27),(24,26),(26,28),(27,29),(29,31),(28,30),(30,32))


class LatestCamera:
    """Drain capture continuously and retain one frame, avoiding a Python backlog."""
    def __init__(self, cv2, config):
        self.cap = cv2.VideoCapture(config["camera_index"], cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(config["camera_index"])
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError("Camera cannot open. Close Camera/Teams/Zoom, allow desktop camera access, or change camera_index in config.json.")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config["capture_width"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config["capture_height"])
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.lock = threading.Lock()
        self.latest = None
        self.failure = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        sequence = 0
        while not self.stop.is_set():
            ok, frame = self.cap.read()
            if not ok:
                self.failure = "Camera stopped delivering frames. Reconnect it and restart the test."
                break
            sequence += 1
            with self.lock:
                self.latest = (sequence, frame, time.perf_counter())

    def get(self):
        with self.lock:
            return self.latest

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)
        self.cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", help="Recorded video; timestamps use source media time")
    parser.add_argument("--camera", type=int, help="Override camera index")
    parser.add_argument("--check", action="store_true", help="Check packages and initialize CPU model without camera")
    parser.add_argument("--headless", action="store_true", help="Recorded-video benchmark without a window")
    parser.add_argument("--duration", type=float, default=0, help="Stop after N wall-clock seconds; 0 is unlimited")
    parser.add_argument("--no-detection", action="store_true", help="Capture-only baseline")
    args = parser.parse_args()
    if args.headless and not args.video:
        parser.error("--headless requires --video")
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        import psutil
    except ImportError as error:
        raise RuntimeError("Missing dependency. Run 01_INSTALL.bat. Details: " + str(error)) from error
    config = json.loads((ROOT / "config.json").read_text())
    if args.camera is not None:
        config["camera_index"] = args.camera
    if config["input_width"] < 64 or config["inference_interval_seconds"] < 0:
        raise RuntimeError("input_width must be at least 64; inference interval must be non-negative")
    model = ROOT / config["model_path"]
    landmarker = None
    if not args.no_detection:
        if not model.is_file():
            raise RuntimeError("Model missing. Run 01_INSTALL.bat or setup_package.py while online.")
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model), delegate=mp.tasks.BaseOptions.Delegate.CPU),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1, min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5, min_tracking_confidence=0.5)
        landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
    if args.check:
        print("PASS: CPU model initialized; Python", platform.python_version(),
              "MediaPipe", mp.__version__, "OpenCV", cv2.__version__)
        if landmarker:
            blank = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((360,640,3),dtype=np.uint8))
            result = landmarker.detect_for_video(blank, 1)
            print("PASS: inference on blank input; poses:", len(result.pose_landmarks))
            landmarker.close()
        return
    run_dir = ROOT / "results" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir.mkdir(parents=True)
    camera = cap = None
    start = time.perf_counter()
    process = psutil.Process()
    detector = FallDetector(config["fall"])
    metrics, events = [], []
    source_index = 0
    sequence_seen = -1
    last_sample_time = -100
    last_model_ms = -1
    previous_source_time = -1
    source_fps = 0
    exit_reason = "user quit"
    error_message = None
    actual_capture_size = None
    try:
        if args.video:
            path = Path(args.video).resolve()
            if not path.is_file():
                raise RuntimeError("Video file does not exist: " + str(path))
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise RuntimeError("Video could not open. Try an MP4 with H.264 encoding.")
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            if not 0 < source_fps < 1000:
                raise RuntimeError("Video has no usable FPS metadata; convert to a constant-frame-rate MP4.")
        else:
            camera = LatestCamera(cv2, config)
        print("CPU test started. Q: quit | A: acknowledge/reset alert | S: save annotated snapshot")
        print("Experimental baseline: no automatic rover control. Results:", run_dir)
        while True:
            now = time.perf_counter()
            if args.duration and now - start >= args.duration:
                exit_reason = "duration reached"
                break
            if camera:
                if camera.failure:
                    raise RuntimeError(camera.failure)
                item = camera.get()
                if item is None or item[0] == sequence_seen:
                    if item is None and now - start > 10:
                        raise RuntimeError("No camera frames within 10 seconds")
                    time.sleep(0.002)
                    continue
                sequence_seen, frame, captured_at = item
                source_time = captured_at - start
            else:
                ok, frame = cap.read()
                if not ok:
                    exit_reason = "end of video"
                    break
                # CAP_PROP_POS_MSEC handles variable frame durations where supported;
                # index/FPS is a documented constant-rate fallback.
                reported_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                source_time = reported_time if reported_time > 0 else source_index / source_fps
                source_index += 1
                captured_at = time.perf_counter()
            if source_time <= previous_source_time:
                raise RuntimeError("Source timestamps are not increasing; convert the recording to constant frame rate")
            previous_source_time = source_time
            if source_time - last_sample_time + 0.000001 < config["inference_interval_seconds"]:
                continue
            if source_time <= last_sample_time:
                raise RuntimeError("Video timestamps moved backward; convert this recording to constant frame rate")
            last_sample_time = source_time
            height, width = frame.shape[:2]
            actual_capture_size = [width, height]
            scaled_width = min(width, config["input_width"])
            resized = cv2.resize(frame, (scaled_width, round(height * scaled_width / width)))
            rh, rw = resized.shape[:2]
            inference_started = time.perf_counter()
            landmarks = []
            if landmarker:
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
                model_ms = max(last_model_ms + 1, round(source_time * 1000))
                last_model_ms = model_ms
                result = landmarker.detect_for_video(image, model_ms)
                if result.pose_landmarks:
                    landmarks = result.pose_landmarks[0]
            inference_ms = (time.perf_counter() - inference_started) * 1000
            observation = observation_from_landmarks(landmarks, rw, rh, source_time, config["visibility_threshold"])
            state, event = detector.update(observation, source_time) if landmarker else ("DISABLED", None)
            if event:
                events.append(event)
                print("POSSIBLE FALL (experimental):", json.dumps(event))
            if landmarks:
                for a, b in EDGES:
                    if min(landmarks[a].visibility, landmarks[b].visibility) >= config["visibility_threshold"]:
                        p1 = (int(landmarks[a].x * rw), int(landmarks[a].y * rh))
                        p2 = (int(landmarks[b].x * rw), int(landmarks[b].y * rh))
                        cv2.line(resized, p1, p2, (60,220,80), 2)
                        cv2.circle(resized, p1, 3, (0,220,255), -1)
            age_ms = (time.perf_counter() - captured_at) * 1000
            ram_mb = process.memory_info().rss / 1048576
            metrics.append({"source_time_seconds": round(source_time,4), "inference_ms": round(inference_ms,2),
                            "frame_age_ms": round(age_ms,2), "ram_mb": round(ram_mb,1),
                            "pose_found": bool(landmarks), "full_body_reliable": observation is not None,
                            "state": state})
            if not args.headless:
                overlay = resized.copy()
                cv2.rectangle(overlay, (0,0), (rw,min(rh,105)), (10,10,10), -1)
                resized = cv2.addWeighted(overlay,0.75,resized,0.25,0)
                lines = ["CPU POSE TEST | " + state,
                         f"Inference {inference_ms:.0f} ms | frame age {age_ms:.0f} ms | RAM {ram_mb:.0f} MB",
                         "Full body: " + ("visible" if observation else "missing / uncertain"),
                         "Q quit | A reset | S snapshot | Experimental fall rules"]
                for i, line in enumerate(lines):
                    cv2.putText(resized,line,(8,22+i*24),cv2.FONT_HERSHEY_SIMPLEX,0.46,(255,255,255),1,cv2.LINE_AA)
                cv2.imshow("CSE499B - Laptop pose and fall test", resized)
                delay = 1
                if args.video:
                    delay = max(1,min(100,round((start + source_time - time.perf_counter()) * 1000)))
                key = cv2.waitKey(delay) & 0xFF
                if key in (ord("q"),27):
                    break
                if key == ord("a"):
                    detector.reset()
                    events.append({"source_time_seconds":source_time,"action":"acknowledge/reset"})
                if key == ord("s"):
                    cv2.imwrite(str(run_dir / f"snapshot_{len(metrics)}.jpg"), resized)
                if cv2.getWindowProperty("CSE499B - Laptop pose and fall test",cv2.WND_PROP_VISIBLE) < 1:
                    break
    except Exception as error:
        exit_reason = "error"
        error_message = str(error)
        raise
    finally:
        if camera:
            camera.close()
        if cap:
            cap.release()
        if landmarker:
            landmarker.close()
        cv2.destroyAllWindows()
        elapsed = time.perf_counter() - start
        with (run_dir / "metrics.csv").open("w",newline="") as output:
            columns = list(metrics[0]) if metrics else ["source_time_seconds","state"]
            writer = csv.DictWriter(output,fieldnames=columns)
            writer.writeheader()
            writer.writerows(metrics)
        (run_dir / "events.json").write_text(json.dumps(events,indent=2))
        summary = {"platform":platform.platform(),"processor":platform.processor(),
                   "python":platform.python_version(),"mediapipe":mp.__version__,"opencv":cv2.__version__,
                   "source":args.video or f"camera {config['camera_index']}","cpu_only":True,
                   "actual_capture_size":actual_capture_size,
                   "elapsed_seconds":round(elapsed,2),"processed_frames":len(metrics),
                   "wall_clock_processed_fps":round(len(metrics)/max(elapsed,0.001),2),
                   "mean_inference_ms":round(float(np.mean([m['inference_ms'] for m in metrics])),2) if metrics else None,
                   "p95_frame_age_ms":round(float(np.percentile([m['frame_age_ms'] for m in metrics],95)),2) if metrics else None,
                   "peak_sampled_ram_mb":max((m['ram_mb'] for m in metrics),default=0),
                   "full_body_reliable_fraction":round(sum(m['full_body_reliable'] for m in metrics)/len(metrics),3) if metrics else None,
                   "possible_fall_events":sum('candidate_time_seconds' in e for e in events),
                   "exit_reason":exit_reason,"error":error_message,"config":config,
                   "metric_note":"Frame age starts when OpenCV returns a frame; camera driver buffering is not measured. Video FPS is playback-paced unless headless. Confirmation delay is from rule candidate, not labelled fall onset."}
        (run_dir / "summary.json").write_text(json.dumps(summary,indent=2))
        print(json.dumps(summary,indent=2))
        print("Saved results:",run_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as error:
        print("ERROR:",error,file=sys.stderr)
        sys.exit(1)
