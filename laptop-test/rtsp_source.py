"""Private RTSP settings and isolated, latest-frame-only network capture."""
import ipaddress
import json
import multiprocessing as mp
import os
from pathlib import Path
from queue import Empty, Full
import re
import time
from urllib.parse import quote

STATUS = {0: "CONNECTING", 1: "STREAMING", 2: "RECONNECTING", 3: "FAILED", 4: "STOPPED"}


def validate_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError('Camera settings must be an object. Open Camera setup to configure the Tapo C212.')
    host = str(settings.get("host", "")).strip()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not host or len(host) > 253 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
            raise ValueError("Enter only the camera IP address or hostname, without a URL or port")
    if not all(isinstance(settings.get(key), str) and settings[key] for key in ('username','password')):
        raise ValueError("Camera-account username and password are required")
    if settings.get("stream", "stream1") not in ("stream1", "stream2"):
        raise ValueError("Stream must be stream1 or stream2")
    for key, default, low, high in (("port",554,1,65535), ("timeout_ms",4000,500,15000),
                                    ("max_attempts",5,1,20)):
        value = settings.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"Invalid {key}")
    for key, default, low, high in (("retry_seconds",2,0.1,30), ("stale_seconds",2,0.1,30)):
        value = settings.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not low <= value <= high:
            raise ValueError(f"Invalid {key}")
    return {**settings, "host": host}


def save_settings(path, settings):
    path = Path(path)
    settings = validate_settings(settings)
    pending = path.with_name('camera.pending.local.json')
    pending.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    pending.replace(path)


def load_settings(path):
    try:
        return validate_settings(json.loads(Path(path).read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise ValueError("Camera settings missing. Run 05_CONFIGURE_TAPO.bat first.") from None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError("Camera settings are unreadable; run 05_CONFIGURE_TAPO.bat again.") from None


def stream_url(settings):
    settings = validate_settings(settings)
    host = settings["host"]
    if ":" in host:
        host = f"[{host}]"
    user = quote(str(settings["username"]), safe="")
    password = quote(str(settings["password"]), safe="")
    return f"rtsp://{user}:{password}@{host}:{settings.get('port',554)}/{settings.get('stream','stream1')}"


def put_latest(queue, item):
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        try:
            queue.put_nowait(item)
        except Full:
            pass  # A frame may be dropped; never wait behind an old frame.


def capture_loop(open_capture, settings, frames, state, generation, attempts, stop):
    """Transport loop separated from OpenCV so outage behavior is testable."""
    sequence = 0
    failures = 0
    while not stop.is_set():
        attempts.value += 1
        state.value = 0 if generation.value == 0 else 2
        cap = None
        received = False
        try:
            cap = open_capture()
            if cap.isOpened():
                generation.value += 1
                misses = 0
                while not stop.is_set():
                    ok, frame = cap.read()
                    # One empty read is normal on this camera: a Wi-Fi pause or a
                    # corrupt packet. Reconnecting on it drops a healthy session.
                    if not ok or frame is None:
                        misses += 1
                        if misses >= 5:
                            break
                        continue
                    misses = 0
                    sequence += 1
                    received = True
                    put_latest(frames, (sequence, frame, time.perf_counter(), generation.value))
                    state.value = 1
        except Exception:
            # Backend exceptions can contain authenticated URLs. Never publish them.
            pass
        finally:
            state.value = 2
            if cap is not None:
                cap.release()
        failures = 1 if received else failures + 1
        if failures >= settings.get("max_attempts",5):
            state.value = 3
            return
        if stop.wait(settings.get("retry_seconds",2)):
            break
    state.value = 4


def capture_worker(settings, frames, state, generation, attempts, stop):
    # OpenCV/FFmpeg native diagnostics can include the full RTSP URL. Suppress
    # them only inside this disposable capture process, never the main app.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 2)
        # Video only: the camera's audio track makes FFmpeg abort the whole session.
        # A short read timeout does the same while the laptop is busy decoding.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|allowed_media_types;video|fflags;nobuffer+discardcorrupt|flags;low_delay"
        os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
        import cv2
        timeout = settings.get("timeout_ms",4000)
        url = stream_url(settings)
        def open_capture():
            capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 20000])
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return capture
        capture_loop(open_capture, settings, frames, state, generation, attempts, stop)


class RTSPCamera:
    def __init__(self, settings, worker=capture_worker):
        self.settings = validate_settings(settings)
        ctx = mp.get_context("spawn")
        self.frames = ctx.Queue(maxsize=1)
        self.state = ctx.Value("i",0)
        self.session = ctx.Value("i",0)
        self.attempts = ctx.Value("i",0)
        self.stop = ctx.Event()
        self.latest = None
        self.process = ctx.Process(target=worker, args=(self.settings,self.frames,self.state,
                                                      self.session,self.attempts,self.stop),daemon=True)
        self.process.start()

    @property
    def status(self):
        if self.state.value == 1 and self.latest is not None and time.perf_counter() - self.latest[2] > self.settings.get("stale_seconds",2):
            return "NO NEW FRAME"
        return STATUS[self.state.value]

    @property
    def generation(self):
        return self.session.value

    @property
    def failure(self):
        if self.state.value == 3 or not self.process.is_alive() and not self.stop.is_set():
            return "RTSP connection failed. Check camera power, network, IP, local camera account and stream; then restart."
        return None

    def get(self):
        while True:
            try:
                self.latest = self.frames.get_nowait()
            except Empty:
                break
        if self.state.value != 1 or self.latest is None:
            return None
        if self.latest[3] != self.generation or time.perf_counter() - self.latest[2] > self.settings.get("stale_seconds",2):
            return None
        return self.latest[:3]

    def close(self):
        self.stop.set()
        self.process.join(timeout=0.5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        self.frames.close()
        self.frames.cancel_join_thread()
