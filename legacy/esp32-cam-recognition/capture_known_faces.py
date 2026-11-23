import time
from pathlib import Path

import cv2
import onnxruntime as ort

if hasattr(ort, "preload_dlls"):
    try:
        ort.preload_dlls(directory="")
    except Exception:
        pass

from insightface.app import FaceAnalysis

from rover_common import ROOT, LatestFrameReader, load_config, safe_person_name


config = load_config()
person = safe_person_name(input("Enter the person's name: "))

if not person:
    raise SystemExit("A valid name is required.")

person_directory = ROOT / "known_faces" / person
person_directory.mkdir(parents=True, exist_ok=True)

providers = ["CPUExecutionProvider"]
if "CUDAExecutionProvider" in ort.get_available_providers():
    providers.insert(0, "CUDAExecutionProvider")

print("Loading buffalo_l face detector...")
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

reader = LatestFrameReader(config["stream_url"])
saved_count = len(list(person_directory.glob("*.jpg")))
target = int(config["capture_target"])
last_sequence = -1
last_faces = []
last_detection_time = 0.0

print("SPACE saves a frame when exactly one face is visible.")
print("Q exits. Target:", target, "images.")

try:
    while True:
        frame, sequence = reader.latest()

        if frame is None:
            time.sleep(0.05)
            continue

        if sequence == last_sequence:
            time.sleep(0.005)
            continue

        last_sequence = sequence

        if time.monotonic() - last_detection_time >= 0.20:
            last_faces = analyser.get(frame)
            last_detection_time = time.monotonic()

        preview = frame.copy()

        for face in last_faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            colour = (0, 220, 80) if len(last_faces) == 1 else (0, 165, 255)
            cv2.rectangle(preview, (x1, y1), (x2, y2), colour, 2)

        status = f"{person}: {saved_count}/{target} saved"
        instruction = "SPACE: save   Q: finish"

        cv2.putText(preview, status, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(preview, instruction, (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        if len(last_faces) != 1:
            cv2.putText(
                preview,
                "Show exactly one clear face",
                (10, preview.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
            )

        cv2.imshow("Capture known face", preview)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), ord("Q")):
            break

        if key == 32:
            if len(last_faces) != 1:
                print("Not saved: exactly one detected face is required.")
                continue

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            image_path = person_directory / f"{timestamp}_{saved_count + 1:02d}.jpg"
            cv2.imwrite(str(image_path), frame)
            saved_count += 1
            print("Saved:", image_path.name)

finally:
    reader.close()
    cv2.destroyAllWindows()

print(f"Finished. {saved_count} image(s) stored for {person}.")
