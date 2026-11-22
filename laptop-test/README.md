# Neural Rover browser workspace

Double-click **00_START_NEURAL_ROVER.bat**. It starts the local backend automatically and opens **http://127.0.0.1:8765/**. Keep the laptop running; no individual Python scripts are needed for daily operation. Run **01_INSTALL.bat** once on a new laptop, with internet, before the demonstration.

The browser workspace contains:

- **Mission control:** start/stop Tapo preview or recognition, choose matching mode, and hold buttons to drive.
- **People library:** upload enrollment photos, capture live views, edit names/roles/IDs, choose alert recipients, remove profiles, and test a separate photo.
- **Devices & network:** save camera settings and connect the main ESP32 by its hotspot IPv4 address.
- **Telegram alerts:** pair a private chat, enable/pause recognition alerts, and explicitly send a test message.
- **Demo readiness:** run local model/gallery checks and follow the phone-hotspot checklist.

Use **Connect phone** for the LAN address and pairing code. The phone receives a driving/video page; management remains on the laptop. Video failure or stopping the camera does not disable driving while the control connection remains available. Releasing a direction, pressing STOP, or losing control input stops movement. **Shut down workspace** stops the rover and closes the backend; closing a browser tab alone leaves the workspace running.

The former desktop app and numbered utilities remain available for troubleshooting. The browser workspace is the daily entry point; instructions below referring to desktop tabs describe the legacy interface.

[Operating guide](FACE_START_HERE.md) · [C212 camera setup](TAPO_START_HERE.md) · [Verification](VERIFY.md)

Run `00_START_NEURAL_ROVER.bat` after installation. The dashboard supports photo enrollment, local live face recognition, optional Telegram alerts, and manual ESP32 control. Start the camera only when needed. The package excludes all local credentials, templates, results, virtual environments, and model weights.

For the complete test, run **04_CHECK_SETUP.bat**, then follow the **Full system test** in the operating guide. Camera setup is available inside the dashboard. Re-enroll any legacy SFace profiles before recognition. The Tapo C212, test computer and main ESP32 must share a reachable network; the current controller firmware expects `CAR`.

For Tapo video and driving on a phone, run **13_START_PHONE_REMOTE.bat** and use the address and pairing code in **Phone remote**. Video and driving are independent. Keep the laptop on; the phone–laptop–ESP32 control connection must remain available.

For university, prepare and rehearse your **phone hotspot** before travelling. The [portable setup guide](TAPO_START_HERE.md#university-demo-using-your-phone-hotspot) covers camera onboarding, changing IPs, actual-laptop installation, power and cold-start checks. Powering the camera without its configured network is insufficient.
