import csv
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

if hasattr(ort, "preload_dlls"):
    try:
        ort.preload_dlls(directory="")
    except Exception as error:
        print("CUDA DLL preload warning:", error)

from insightface.app import FaceAnalysis

from rover_common import ROOT, LatestFrameReader, load_config


config = load_config()
known_faces_directory = ROOT / "known_faces"
logs_directory = ROOT / "logs"
snapshots_directory = ROOT / "snapshots"
logs_directory.mkdir(exist_ok=True)
snapshots_directory.mkdir(exist_ok=True)

providers = ["CPUExecutionProvider"]
if "CUDAExecutionProvider" in ort.get_available_providers():
    providers.insert(0, "CUDAExecutionProvider")

print("Execution providers:", providers)
print("Loading buffalo_l...")

analyser = FaceAnalysis(
    name="buffalo_l",
    allowed_modules=["detection", "recognition"],
    providers=providers,
)
analyser.prepare(
    ctx_id=0,
    det_thresh=float(config["detection_threshold"]),
    det_size=(int(config["detection_size"]),) * 2,
)


def largest_face(faces):
    return max(
        faces,
        key=lambda face: (
            (face.bbox[2] - face.bbox[0])
            * (face.bbox[3] - face.bbox[1])
        ),
    )


def load_gallery():
    gallery = {}
    known_faces_directory.mkdir(exist_ok=True)

    for person_directory in sorted(known_faces_directory.iterdir()):
        if not person_directory.is_dir():
            continue

        embeddings = []

        for image_path in sorted(person_directory.iterdir()):
            if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue

            image = cv2.imread(str(image_path))
            if image is None:
                continue

            faces = analyser.get(image)
            if not faces:
                print("No enrollment face detected in:", image_path)
                continue

            embeddings.append(largest_face(faces).normed_embedding)

        if embeddings:
            average = np.mean(embeddings, axis=0)
            average /= np.linalg.norm(average)
            gallery[person_directory.name] = average
            print(f"Registered {person_directory.name}: {len(embeddings)} image(s)")

    return gallery


gallery = load_gallery()
if not gallery:
    print("WARNING: no known people were loaded.")
    print("Run 04_CAPTURE_FACES.bat before expecting named matches.")


def identify(embedding):
    best_name = "Unknown"
    best_score = -1.0

    for name, reference in gallery.items():
        score = float(np.dot(embedding, reference))
        if score > best_score:
            best_name = name
            best_score = score

    if best_score < float(config["recognition_threshold"]):
        best_name = "Unknown"

    return best_name, best_score


log_path = logs_directory / "recognition_log.csv"
last_logged = {}


def log_recognition(name, score):
    if name in {"Unknown", "Too small"}:
        return

    now = time.time()
    cooldown = float(config["event_log_cooldown_seconds"])

    if now - last_logged.get(name, 0.0) < cooldown:
        return

    new_file = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if new_file:
            writer.writerow(["timestamp", "person", "similarity"])
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), name, f"{score:.4f}"])

    last_logged[name] = now


reader = LatestFrameReader(config["stream_url"])
last_sequence = -1
last_inference_time = 0.0
display_frame = None

print("Stream:", config["stream_url"])
print("Q: quit   S: save snapshot")

try:
    while True:
        frame, sequence = reader.latest()

        if frame is None:
            time.sleep(0.05)
            continue

        if sequence == last_sequence:
            time.sleep(0.005)
            continue

        if time.monotonic() - last_inference_time < float(config["inference_interval_seconds"]):
            time.sleep(0.005)
            continue

        last_sequence = sequence
        last_inference_time = time.monotonic()
        faces = analyser.get(frame)
        display_frame = frame.copy()

        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            face_width = x2 - x1

            if face_width < int(config["minimum_face_width"]):
                name = "Too small"
                score = 0.0
                colour = (0, 165, 255)
            else:
                name, score = identify(face.normed_embedding)
                colour = (0, 220, 80) if name != "Unknown" else (0, 0, 255)
                log_recognition(name, score)

            cv2.rectangle(display_frame, (x1, y1), (x2, y2), colour, 2)
            label = name if name == "Too small" else f"{name}  {score:.2f}"
            cv2.putText(
                display_frame,
                label,
                (x1, max(24, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                colour,
                2,
            )

        provider_label = "GPU" if providers[0] == "CUDAExecutionProvider" else "CPU"
        cv2.putText(
            display_frame,
            f"buffalo_l | {provider_label} | faces {len(faces)}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Neural Rover face recognition", display_frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), ord("Q")):
            break

        if key in (ord("s"), ord("S")):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = snapshots_directory / f"recognition_{timestamp}.jpg"
            cv2.imwrite(str(path), display_frame)
            print("Snapshot saved:", path)

finally:
    reader.close()
    cv2.destroyAllWindows()
