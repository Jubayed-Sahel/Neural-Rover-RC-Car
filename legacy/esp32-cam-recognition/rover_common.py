import json
import re
import threading
import time
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def safe_person_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:60]


class LatestFrameReader:
    """Continuously decodes the MJPEG stream and keeps only its newest frame."""

    def __init__(self, stream_url):
        self.stream_url = stream_url
        self.capture = None
        self.frame = None
        self.sequence = 0
        self.connected = False
        self.running = True
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _open(self):
        if self.capture is not None:
            self.capture.release()

        self.capture = cv2.VideoCapture(self.stream_url)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.connected = self.capture.isOpened()

    def _read_loop(self):
        while self.running:
            if self.capture is None or not self.capture.isOpened():
                self._open()
                if not self.connected:
                    time.sleep(1.0)
                    continue

            success, frame = self.capture.read()

            if not success:
                self.connected = False
                self.capture.release()
                time.sleep(0.5)
                continue

            with self.lock:
                self.frame = frame
                self.sequence += 1
                self.connected = True

    def latest(self):
        with self.lock:
            if self.frame is None:
                return None, self.sequence
            return self.frame.copy(), self.sequence

    def close(self):
        self.running = False
        if self.capture is not None:
            self.capture.release()
        self.thread.join(timeout=2.0)
