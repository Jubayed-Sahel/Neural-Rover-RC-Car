"""Download Google's official Lite pose model once; offline use afterward."""
from pathlib import Path
import hashlib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
EXPECTED_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"


def main():
    target = ROOT / "models" / "pose_landmarker_lite.task"
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(".download")
        try:
            print("Downloading official MediaPipe Pose Landmarker Lite model...")
            with urllib.request.urlopen(URL, timeout=90) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if not zipfile.is_zipfile(temporary):
                raise RuntimeError("Download is not a valid task bundle")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    if not zipfile.is_zipfile(target):
        raise RuntimeError("Model is corrupt; remove it and rerun installation")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError("Model checksum differs from the verified bundle; remove it and rerun, or investigate upstream changes")
    print("Model ready:", target)
    print("SHA256:", digest)


if __name__ == "__main__":
    main()
