"""Interactive local credentials. Never pass camera passwords on the command line."""
from getpass import getpass
from pathlib import Path
from rtsp_source import save_settings

ROOT = Path(__file__).resolve().parent


def main():
    print("Use the LOCAL Camera Account created in Tapo settings, not your TP-Link login.")
    print("Credentials stay in camera.local.json on this computer. Do not share that file.")
    settings = {
        "host": input("Camera IP address: ").strip(),
        "username": input("Local camera username: ").strip(),
        "password": getpass("Local camera password (hidden): "),
        "stream": input("Stream [stream1 / stream2; default stream2]: ").strip() or "stream2",
        "port":554,"timeout_ms":4000,"max_attempts":5,"retry_seconds":2,"stale_seconds":2}
    save_settings(ROOT / 'camera.local.json', settings)
    print('Saved locally. Next: 06_PREVIEW_TAPO.bat (camera only), then 00_START_NEURAL_ROVER.bat for recognition and driving.')


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError):
        print("Could not save settings. Check the IP, stream choice and folder permissions, then retry.")
        raise SystemExit(1)
