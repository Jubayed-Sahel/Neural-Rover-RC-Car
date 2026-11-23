"""Offline readiness check: never opens a camera, sends alerts or drives a rover."""
from dataclasses import dataclass
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


@dataclass
class Check:
    level: str
    title: str
    detail: str


def inspect_gallery(path):
    if not path.exists():
        return Check('ACTION','People','Enroll 3–5 clear photos per person in the dashboard.')
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(document,dict):
            raise ValueError
        if document.get('version') != 2:
            return Check('ACTION','People','Legacy gallery: re-enroll photos in the dashboard. The old file is backed up on the first save.')
        people = document['people']
        if not isinstance(people,dict):
            raise ValueError
        for name,samples in people.items():
            if not isinstance(name,str) or not name.strip() or not isinstance(samples,list) or not samples:
                raise ValueError
            for sample in samples:
                if (not isinstance(sample,list) or len(sample) != 512
                    or not all(type(value) in (int,float) and math.isfinite(value) for value in sample)
                    or sum(value*value for value in sample) < 1e-12):
                    raise ValueError
        if not people:
            return Check('ACTION','People','No current profiles. Enroll photos in the dashboard.')
        return Check('PASS','People',f'{len(people)} current profile(s). Test with different photos and live faces.')
    except (OSError,ValueError,KeyError,TypeError):
        return Check('ACTION','People','Gallery is unreadable or invalid. Keep the original file and resolve it before enrollment.')


def check_models(root):
    from face_recognition_demo import ARCFACE_NAME, ARCFACE_SHA, ARCFACE_SIZE, MODELS, FaceEngine
    expected = [(relative.split('/')[-1],digest,size) for relative,digest,size in MODELS]
    expected.append((ARCFACE_NAME,ARCFACE_SHA,ARCFACE_SIZE))
    for name,digest,size in expected:
        path = root/'models'/name
        if not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return Check('FAIL','Models','Missing or damaged weights. Run 01_INSTALL.bat with internet before the live test.')
    # With both cached files verified, initialization uses the local weights.
    engine = FaceEngine()
    import numpy as np
    engine.detect_upright(np.zeros((320,320,3),dtype=np.uint8))
    return Check('PASS','Models','Both hashes verified; detector inference and recognizer initialization passed offline.')


def local_checks(root=ROOT):
    root = Path(root)
    from rtsp_source import load_settings
    from alert_people import load_watch_names
    from telegram_alerts import load_alert_settings
    checks = [inspect_gallery(root/'faces.local.json')]
    try:
        load_settings(root/'camera.local.json')
        checks.append(Check('PASS','Tapo setup','Local configuration is valid. Live connectivity still needs testing.'))
    except (OSError,ValueError):
        checks.append(Check('ACTION','Tapo setup','Open Camera setup in the dashboard or run 05_CONFIGURE_TAPO.bat.'))
    # The default application paths are used only for the actual installation.
    if root.resolve() == ROOT:
        telegram = load_alert_settings()
        marked = load_watch_names()
        try:
            document = json.loads((root/'faces.local.json').read_text(encoding='utf-8'))
            active = set(document['people']) if isinstance(document,dict) and document.get('version') == 2 else set()
        except (OSError,ValueError,KeyError,TypeError):
            active = set()
        if telegram:
            checks.append(Check('PASS','Telegram setup','Private chat configuration found; phone delivery is not verified.'))
            checks.append(Check('PASS' if marked & active else 'ACTION','Alert choices',
                                f'{len(marked & active)} current profile(s) marked.' if marked & active else 'Mark a current, saved person for alerts before starting recognition.'))
        else:
            checks.append(Check('OPTIONAL','Telegram setup','Run 10_CONFIGURE_TELEGRAM.bat to pair your phone, then 11_TEST_TELEGRAM.bat yourself.'))
    checks.append(Check('ACTION','Rover','Connect to the main ESP32 IP in Rover controls; test stops with the wheels raised.'))
    return checks


def main():
    checks = []
    runtime_ok = sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8
    checks.append(Check('PASS' if runtime_ok else 'FAIL','Python','64-bit Python 3.12 required.'))
    dependencies_ok = True
    for requirement in (ROOT/'requirements-lock.txt').read_text().splitlines():
        if not requirement.strip() or requirement.startswith('#'):
            continue
        name,expected = requirement.split('==',1)
        try:
            actual = version(name)
        except PackageNotFoundError:
            actual = 'missing'
        ok = actual == expected
        dependencies_ok &= ok
        checks.append(Check('PASS' if ok else 'FAIL',name,f'{actual}; expected {expected}.'))
    try:
        with tempfile.TemporaryFile(dir=ROOT) as handle:
            handle.write(b'readiness')
        checks.append(Check('PASS','Folder','Writable for local setup and profile files.'))
    except OSError:
        checks.append(Check('FAIL','Folder','Extract the ZIP to a writable folder before running the app.'))
    if dependencies_ok and runtime_ok:
        try:
            checks.append(check_models(ROOT))
        except Exception:
            checks.append(Check('FAIL','Models','Model initialization failed. Run 01_INSTALL.bat and keep the error shown there.'))
        try:
            import tkinter as tk
            from rover_app import App
            root = tk.Tk()
            root.withdraw()
            try:
                app = App(root)
                root.update_idletasks()
                app.close()
            finally:
                if tk._default_root is not None:
                    root.destroy()
            checks.append(Check('PASS','Dashboard','Desktop interface initialized with all devices disconnected.'))
        except Exception:
            checks.append(Check('FAIL','Dashboard','Desktop interface could not initialize. Run 01_INSTALL.bat.'))
        checks.extend(local_checks())
    print('NEURAL ROVER - SETUP CHECK\n')
    for check in checks:
        print(f'[{check.level}] {check.title}: {check.detail}')
    print('\nNo camera, physical rover, or Telegram connection was attempted.')
    failed = any(check.level == 'FAIL' for check in checks)
    print('Fix FAIL items before opening the dashboard.' if failed else 'Software checks passed. Complete ACTION items during your live test.')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
