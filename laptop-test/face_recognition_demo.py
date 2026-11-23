"""Local, consent-based face recognition for the Tapo RTSP feed."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
from threading import Event, Lock, Thread
import time
from urllib.request import Request, urlopen
import zipfile

import cv2
import numpy as np

from alert_people import load_watch_names
from rtsp_source import RTSPCamera, load_settings
from telegram_alerts import MatchGate, TelegramAlerts, load_alert_settings
from recognition_policy import MATCH_MODES, StableRecognizer, overlap

ROOT = Path(__file__).resolve().parent
GALLERY = ROOT / 'faces.local.json'
MODEL_BASE = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/'
MODELS = (
    ('face_detection_yunet/face_detection_yunet_2023mar.onnx', '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4', 232589),
)
ARCFACE_URL = 'https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip'
ARCFACE_NAME = 'w600k_mbf.onnx'
ARCFACE_SHA = '9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f'
ARCFACE_SIZE = 13616099
# Same five-point template OpenCV uses to align a YuNet face onto a 112x112 crop.
ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)
SAMPLES = 5
FEATURE_SIZE = 512


def model_path(relative, digest, size):
    path = ROOT / 'models' / relative.split('/')[-1]
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        print(f'Downloading {path.name} ({size / 1_000_000:.1f} MB)...', flush=True)
        with urlopen(MODEL_BASE + relative, timeout=30) as response:
            data = response.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError('Model download failed its integrity check. Retry on a working internet connection.')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    return str(path)


def arcface_path():
    path = ROOT / 'models' / ARCFACE_NAME
    if path.exists() and path.stat().st_size == ARCFACE_SIZE and hashlib.sha256(path.read_bytes()).hexdigest() == ARCFACE_SHA:
        return str(path)
    print('Downloading ArcFace recognizer (13.6 MB)...', flush=True)
    request = Request(ARCFACE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        data = archive.read(ARCFACE_NAME)
    if len(data) != ARCFACE_SIZE or hashlib.sha256(data).hexdigest() != ARCFACE_SHA:
        raise RuntimeError('ArcFace download failed its integrity check. Retry on a working internet connection.')
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return str(path)


def align_face(frame, row):
    row = np.asarray(row, dtype=np.float32).reshape(-1)
    source = np.array([
        [row[4], row[5]],
        [row[6], row[7]],
        [row[8], row[9]],
        [row[10], row[11]],
        [row[12], row[13]],
    ], dtype=np.float32)
    matrix, _ = cv2.estimateAffinePartial2D(source, ARCFACE_DST)
    if matrix is None:
        raise ValueError('Could not align the face.')
    return cv2.warpAffine(frame, matrix, (112, 112), flags=cv2.INTER_LINEAR)


def unit(feature):
    vector = np.asarray(feature, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(vector)
    if vector.size != FEATURE_SIZE or not np.isfinite(norm) or norm < 1e-6:
        raise ValueError('Invalid face template. Re-enroll the person.')
    return vector / norm


def identify(feature, gallery, threshold=0.40, margin=0.06):
    """Reject low similarity and ambiguous identities; similarity is not probability."""
    feature = unit(feature)
    scores = sorted(((float(np.max(templates @ feature)), name) for name, templates in gallery.items()), reverse=True)
    if not scores:
        return 'Unknown', None
    best, name = scores[0]
    if best < threshold or (len(scores) > 1 and best - scores[1][0] < margin):
        return 'Unknown', best
    return name, best


def read_document(path=None):
    path = Path(path) if path is not None else GALLERY
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(document, dict):
            raise ValueError
        if document.get('version') == 2:
            if not isinstance(document.get('people'), dict) or not isinstance(document.get('profiles',{}), dict):
                raise ValueError
        return document
    except (ValueError, UnicodeError):
        raise ValueError('Saved profiles are unreadable. Keep faces.local.json for recovery; run 04_CHECK_SETUP before enrolling again.') from None


def read_gallery(path=None):
    document = read_document(path)
    if not document:
        return {}
    if document.get('version') != 2:
        print('Saved faces belong to the old recognizer. Enroll again with 08_ENROLL_TAPO_FACE.bat.')
        return {}
    try:
        return {name: np.stack([unit(sample) for sample in samples]) for name, samples in document['people'].items()}
    except (ValueError, TypeError):
        raise ValueError('A saved face template is invalid. Keep faces.local.json for recovery and run 04_CHECK_SETUP.') from None


def read_profiles(path=None):
    document = read_document(path)
    profiles = document.get('profiles', {}) if document.get('version') == 2 else {}
    return {name:{key:value for key,value in fields.items() if key in ('id','role') and isinstance(value,str)}
            for name,fields in profiles.items() if isinstance(fields,dict)}


def save_person(gallery, name, samples, profile=None, append=False, path=None):
    samples = [unit(sample) for sample in samples]
    if append and name in gallery:
        if any(float(np.max(gallery[name] @ sample)) < 0.35 for sample in samples):
            raise ValueError('The new photos do not match this saved profile. Use clearer photos, or choose Replace photos if the old enrollment was incorrect.')
        samples = [*gallery[name], *samples]
    distinct = []
    for sample in samples:
        if not distinct or max(float(old @ sample) for old in distinct) < 0.995:
            distinct.append(sample)
    if not distinct or len(distinct) > 30:
        raise ValueError('Keep 1–30 distinct photos per person. Replace photos to start a fresh profile.')
    people = {key: values.tolist() for key, values in gallery.items()}
    people[name] = np.stack(distinct).tolist()
    profiles = read_profiles(path)
    if profile is not None:
        profiles[name] = profile
    write_gallery(people, profiles, path)


def remove_person(name, path=None):
    path = Path(path) if path is not None else GALLERY
    document = json.loads(path.read_text(encoding='utf-8'))
    people, profiles = document['people'], document.get('profiles', {})
    people.pop(name, None)
    profiles.pop(name, None)
    write_gallery(people, profiles, path)


def write_gallery(people, profiles, path=None):
    path = Path(path) if path is not None else GALLERY
    if path.exists():
        previous = json.loads(path.read_text(encoding='utf-8'))
        backup = path.with_name('faces.legacy.local.json')
        if previous.get('version') != 2 and not backup.exists():
            shutil.copyfile(path, backup)
    pending = path.with_name('faces.pending.local.json')
    pending.write_text(json.dumps({'version': 2, 'people': people, 'profiles': profiles}), encoding='utf-8')
    pending.replace(path)


def rotated_point_to_original(x, y, turns, width, height):
    """Map a point in np.rot90(image, turns) back onto the original image."""
    turns %= 4
    if turns == 0:
        return x, y
    if turns == 1:
        return width - 1 - y, x
    if turns == 2:
        return width - 1 - x, height - 1 - y
    return y, height - 1 - x


def unrotate_detection(row, turns, width, height):
    row = np.asarray(row, dtype=np.float32)
    if turns % 4 == 0:
        return row.copy()
    out = row.copy()
    x, y, w, h = (float(value) for value in row[:4])
    corners = [rotated_point_to_original(px, py, turns, width, height)
               for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    out[0], out[1] = min(xs), min(ys)
    out[2], out[3] = max(xs) - out[0], max(ys) - out[1]
    for index in range(5):
        px, py = rotated_point_to_original(float(row[4 + 2 * index]), float(row[5 + 2 * index]), turns, width, height)
        out[4 + 2 * index], out[5 + 2 * index] = px, py
    return out


def multiple_of_32(image):
    height, width = image.shape[:2]
    pad_w = (32 - width % 32) % 32
    pad_h = (32 - height % 32) % 32
    if not pad_w and not pad_h:
        return image
    return cv2.copyMakeBorder(image, 0, pad_h, 0, pad_w, cv2.BORDER_CONSTANT, value=(0, 0, 0))


class FaceEngine:
    def __init__(self, mode='Balanced'):
        self.threshold, self.margin = MATCH_MODES[mode]
        detector = model_path(*MODELS[0])
        # YuNet misses sideways faces. 0.6 keeps tilted faces that are still a real face.
        self.detector = cv2.FaceDetectorYN.create(detector, '', (320, 320), 0.6, 0.3, 100)
        self.recognizer = cv2.dnn.readNetFromONNX(arcface_path())
        self.recognizer.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.recognizer.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.orientation = 0
        self.frame_index = 0
        self.confirmed = False

    def _oriented_view(self, frame, turns):
        view = frame if turns % 4 == 0 else np.ascontiguousarray(np.rot90(frame, turns))
        # Bound detection work on high-resolution streams; embed from full-size
        # pixels after mapping the landmarks back. Padding is detector-only.
        scale = min(1.0, 960 / max(view.shape[:2]))
        small = cv2.resize(view, (max(1, round(view.shape[1] * scale)), max(1, round(view.shape[0] * scale)))) if scale < 1 else view
        sx, sy = view.shape[1] / small.shape[1], view.shape[0] / small.shape[0]
        detected = multiple_of_32(small)
        self.detector.setInputSize((detected.shape[1], detected.shape[0]))
        _, rows = self.detector.detect(detected)
        mapped = []
        for row in ([] if rows is None else rows):
            row = row.copy()
            row[:14:2] *= sx
            row[1:14:2] *= sy
            mapped.append(row)
        return view, mapped

    def _detect_oriented(self, frame, turns):
        height, width = frame.shape[:2]
        _, rows = self._oriented_view(frame, turns)
        return [unrotate_detection(row, turns, width, height) for row in rows]

    def detect_upright(self, frame):
        return self._detect_oriented(frame, 0)

    def detect(self, frame):
        # Reuse the angle that worked. Scan sideways and upside-down only when
        # that angle is empty or this is a periodic check, so lying down does
        # not cost four detections on every frame.
        self.frame_index += 1
        rows = self._detect_oriented(frame, self.orientation)
        if rows and self.frame_index % 8 != 0:
            return rows
        if not rows and self.frame_index % 3 != 0:
            return []
        found = {self.orientation: rows}
        for turns in (0, 1, 2, 3):
            if turns not in found:
                found[turns] = self._detect_oriented(frame, turns)
        best_turns, best_rows = max(
            found.items(),
            key=lambda item: max((float(row[-1]) for row in item[1]), default=0.0),
        )
        if not best_rows:
            self.orientation = 0
            return []
        self.orientation = best_turns
        return best_rows

    def _match_view(self, frame, turns, gallery):
        """Recognize on the turned picture with YuNet's own landmarks, then map the box back."""
        view, rows = self._oriented_view(frame, turns)
        height, width = frame.shape[:2]
        faces = []
        best_sim = -1.0
        named = False
        for row in rows:
            original = unrotate_detection(row, turns, width, height)
            issue = self.quality_issue(row, view)
            if issue:
                faces.append((original, issue))
                continue
            try:
                label, sim = identify(self.embed(view, row), gallery, self.threshold, self.margin)
            except (cv2.error, ValueError):
                faces.append((original, 'Unknown'))
                continue
            if sim is not None and sim > best_sim:
                best_sim = sim
            if label != 'Unknown':
                named = True
            faces.append((original, label))
        return turns, faces, best_sim, named

    def identify_faces(self, frame, gallery):
        # Keep upright faces as well as rotated ones. Select duplicate boxes by
        # detector confidence, never by whichever rotation happens to name someone.
        self.frame_index += 1
        views = [self._match_view(frame, 0, gallery)]
        if self.orientation:
            views.append(self._match_view(frame, self.orientation, gallery))
        if not any(view[1] for view in views) or self.frame_index % 12 == 0:
            scanned = {view[0] for view in views}
            views.extend(self._match_view(frame, turns, gallery) for turns in (1, 3, 2) if turns not in scanned)
        candidates = sorted(((row, label, view[0]) for view in views for row, label in view[1]),
                            key=lambda item: float(item[0][-1]), reverse=True)
        kept = []
        for candidate in candidates:
            if not any(overlap(candidate[0], previous[0]) > 0.35 for previous in kept):
                kept.append(candidate)
        self.orientation = next((turns for _, _, turns in kept if turns), 0)
        return [(row, label) for row, label, _ in kept]

    def usable(self, row, frame):
        row = np.asarray(row, dtype=np.float32)
        if row.size < 15 or not np.all(np.isfinite(row)):
            return False
        height, width = frame.shape[:2]
        xs, ys = row[4:14:2], row[5:14:2]
        inside = xs.min() >= 0 and ys.min() >= 0 and xs.max() < width and ys.max() < height
        return bool(inside and min(float(row[2]), float(row[3])) >= 40)

    def quality_issue(self, row, frame, enrollment=False):
        if not self.usable(row, frame):
            return 'Move closer; keep the whole face visible.'
        if min(float(row[2]), float(row[3])) < (70 if enrollment else 50):
            return 'Face too small; move closer.'
        try:
            # Measure real face pixels; affine padding can otherwise make a
            # featureless crop appear sharp at its artificial black boundary.
            x,y,w,h = (float(value) for value in row[:4])
            height,width = frame.shape[:2]
            crop = frame[max(0,int(y+.15*h)):min(height,int(y+.85*h)),
                         max(0,int(x+.15*w)):min(width,int(x+.85*w))]
            crop = cv2.resize(crop,(80,80),interpolation=cv2.INTER_AREA if min(crop.shape[:2]) > 80 else cv2.INTER_LINEAR)
        except (cv2.error, ValueError):
            return 'Face alignment failed; face the camera.'
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        if brightness < 35:
            return 'Too dark; add light in front of the face.'
        if brightness > 225:
            return 'Too bright; avoid direct glare.'
        if float(gray.std()) < 12 or cv2.Laplacian(gray, cv2.CV_64F).var() < (35 if enrollment else 20):
            return 'Face looks blurry; hold still or use a sharper photo.'
        return None

    def embed(self, frame, row):
        aligned = align_face(frame, row)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        self.recognizer.setInput(blob)
        return unit(self.recognizer.forward())


def prefer_view(found, current):
    if found[3] != current[3]:
        return found[3]
    if found[2] != current[2]:
        return found[2] > current[2]
    return bool(found[1]) and not current[1]


DISPLAY_WIDTH = 1280


def display_frame(frame):
    """Build a steady preview. Stream 2 is small, so enlarge it sharply instead of stretching it in the window."""
    height, width = frame.shape[:2]
    if width == DISPLAY_WIDTH:
        return frame, 1.0
    scale = DISPLAY_WIDTH / width
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    shown = cv2.resize(frame, (DISPLAY_WIDTH, max(1, int(round(height * scale)))), interpolation=interpolation)
    if scale > 1:
        soft = cv2.GaussianBlur(shown, (0, 0), 0.8)
        shown = cv2.addWeighted(shown, 1.25, soft, -0.25, 0)
    return shown, scale


class FaceAnalyst:
    """Recognize faces off the preview thread so the camera image is not stalled."""

    def __init__(self, engine, gallery, enroll, watch, gate, alerts):
        self.engine = engine
        self.gallery = gallery
        self.enroll = enroll
        self.watch = watch
        self.gate = gate
        self.alerts = alerts
        self.lock = Lock()
        self.engine_lock = Lock()
        self.pending = None
        self.faces = []
        self.message = 'Starting camera'
        self.sample = None
        self.detections = 0
        self.stable = StableRecognizer()
        self.stop = Event()
        self.thread = Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def submit(self, seq, frame):
        with self.lock:
            self.pending = (seq, frame)

    def view(self):
        with self.lock:
            return list(self.faces), self.message, self.sample

    def capture_sample(self):
        with self.lock:
            sample = self.sample
        if sample is None:
            return None
        frame, row = sample
        with self.engine_lock:
            return self.engine.embed(frame, row)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)

    def run(self):
        last_seq = -1
        while not self.stop.is_set():
            with self.lock:
                item = self.pending
                self.pending = None
            if item is None or item[0] == last_seq:
                time.sleep(0.005)
                continue
            last_seq = item[0]
            self.examine(item[1])

    def examine(self, frame):
        with self.engine_lock:
            matched = []
            if self.enroll or not self.gallery:
                rows = self.engine.detect(frame)
                faces = []
                for row in rows:
                    label = 'Face' if self.enroll else 'Unknown'
                    colour = (30, 210, 240)
                    if not self.engine.usable(row, frame):
                        label = 'Face too small or clipped'
                    faces.append((row, label, colour))
                sample = (frame, rows[0]) if self.enroll and len(rows) == 1 and self.engine.usable(rows[0], frame) else None
            else:
                found = self.engine.identify_faces(frame, self.gallery)
                found = self.stable.update(found, self.gallery)
                faces = []
                for row, label in found:
                    colour = (80, 200, 60) if label in self.gallery else (30, 210, 240)
                    if label in self.watch:
                        matched.append(label)
                    faces.append((row, label, colour))
                rows = [row for row, _ in found]
                sample = None
        message = 'No face' if not rows else f'Faces: {len(rows)}'
        if not self.enroll and not self.gallery:
            message += ' | No one enrolled yet'
        elif self.watch:
            message += ' | Telegram armed'
        if self.gate is not None:
            self.gate.observe(matched, time.monotonic(), self.alerts.enqueue)
        with self.lock:
            self.faces = faces
            self.message = message
            self.sample = sample
            self.detections += len(faces)


def start_alerts(gallery):
    if not gallery:
        return None, None, set()
    stored = load_watch_names()
    watch = stored & set(gallery)
    missing = stored - watch
    if missing:
        print('Ignored alert marks for people who are not enrolled: ' + ', '.join(sorted(missing)))
    settings = load_alert_settings()
    if settings is None:
        if watch:
            print('People are marked for alerts, but Telegram is not paired. Run 10_CONFIGURE_TELEGRAM.bat.')
        return None, None, set()
    if not watch:
        print('Telegram is paired. Nobody is marked for alerts. Run 12_MARK_ALERT_PEOPLE.bat.')
        return None, None, set()
    print('Telegram alert armed for: ' + ', '.join(sorted(watch)) + '. One message per person every 60 seconds.')
    return TelegramAlerts(settings), MatchGate(), watch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--enroll', action='store_true')
    mode.add_argument('--check', action='store_true')
    parser.add_argument('--duration', type=float, default=0, help='Optional session duration in seconds')
    parser.add_argument('--headless', action='store_true', help='Timed camera smoke test; no names or images saved')
    args = parser.parse_args()
    if args.headless and (args.duration <= 0 or args.enroll):
        parser.error('--headless requires a positive --duration and cannot enroll')
    engine = FaceEngine()
    if args.check:
        engine.detect(np.zeros((320, 320, 3), dtype=np.uint8))
        print('Both face models loaded; detector inference passed.')
        return
    gallery = read_gallery()
    alerts = gate = None
    watch = set()
    if not args.enroll and not args.headless:
        alerts, gate, watch = start_alerts(gallery)
    name = None
    if args.enroll:
        name = input('Consenting person’s display name: ').strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,39}', name) or name.casefold() == 'unknown':
            raise ValueError('Use a name of 1–40 letters, numbers, spaces, hyphens or underscores (not Unknown).')
        if name in gallery and input('Replace the existing samples for this name? [y/N] ').strip().lower() != 'y':
            return
    camera = RTSPCamera(load_settings(ROOT / 'camera.local.json'))
    window = 'Neural Rover - Local Face Recognition'
    samples = []
    count = 0
    last_seq = -1
    start = time.monotonic()
    sample_at = -10
    analyst = None
    live = None
    clean = None
    scale = 1.0
    try:
        if not args.headless:
            analyst = FaceAnalyst(engine, gallery, args.enroll, watch, gate, alerts)
            analyst.start()
            cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        while not args.duration or time.monotonic() - start < args.duration:
            if camera.failure:
                raise RuntimeError(camera.failure)
            item = camera.get()
            if item is not None and item[0] != last_seq:
                last_seq, live, _ = item
                count += 1
                if analyst is not None:
                    analyst.submit(last_seq, live)
                    clean, scale = display_frame(live)
            if args.headless:
                time.sleep(0.02)
                continue
            if clean is None:
                shown = np.zeros((720, DISPLAY_WIDTH, 3), dtype=np.uint8)
                faces = []
                message = f'Camera: {camera.status}'
            else:
                shown = clean.copy()
                faces, message, _ = analyst.view()
                if item is None and camera.status != 'STREAMING':
                    message = f'Camera: {camera.status}'
                if args.enroll:
                    message = f'Enrollment {len(samples)}/{SAMPLES} | One clear face | S to save'
                for row, label, colour in faces:
                    x, y, w, h = (int(round(float(value) * scale)) for value in row[:4])
                    cv2.rectangle(shown, (x, y), (x + w, y + h), colour, 2)
                    cv2.putText(shown, label, (max(0, x), max(48, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, colour, 2)
            cv2.rectangle(shown, (0, 0), (shown.shape[1], 34), (0, 0, 0), -1)
            cv2.putText(shown, message + ' | Q to quit', (9, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            cv2.imshow(window, shown)
            key = cv2.waitKey(1) & 255
            if key in (ord('q'), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
            if args.enroll and key == ord('s'):
                feature = None if analyst is None else analyst.capture_sample()
                if feature is None or time.monotonic() - sample_at < 0.7:
                    print('Wait briefly and make sure exactly one clear face is fully in frame.')
                    continue
                samples.append(feature)
                sample_at = time.monotonic()
                print(f'Sample {len(samples)}/{SAMPLES} saved for this session. Turn slightly for the next sample.')
                if len(samples) == SAMPLES:
                    save_person(gallery, name, samples)
                    print('Enrollment complete. Open 09_RECOGNIZE_TAPO_FACES.bat.')
                    break
            if item is None or item[0] == last_seq:
                time.sleep(0.008)
    finally:
        if analyst is not None:
            analyst.close()
        camera.close()
        cv2.destroyAllWindows()
    if args.enroll and len(samples) < SAMPLES:
        print('Enrollment cancelled; no templates were saved.')
    found = 0 if analyst is None else analyst.detections
    print(f'Frames processed: {count}; face detections: {found}.')
    if args.headless and not count:
        raise RuntimeError('No camera frames received during the timed test.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, cv2.error) as error:
        raise SystemExit(f'Face demo: {error}')
