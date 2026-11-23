# CSE499B — Neural Rover face recognition

## Current project

The Windows Python dashboard enrolls consenting participants from uploaded photos, recognizes known people on the Tapo C212 feed, sends optional Telegram alerts for selected people, and provides manual rover control over the existing ESP32 WebSocket. Face recognition and driving are independent. Fall detection is no longer part of this project.

The C212 stays stationary for the demo. Position it where faces are clearly visible. The PC or demo laptop processes video locally; the Arduino firmware remains unchanged. An optional paired phone dashboard runs on the laptop's local network and combines Tapo video with manual driving. Public internet control and Cloudflare access are outside this build. Video loss does not disable driving, while a failed or stale control connection still stops movement.

## University deployment

The chosen portable network is the user's **phone hotspot**. Prepare the exact phone, camera and demonstration laptop on that network at home. Use 2.4 GHz and match the main controller's existing CAR network settings unless intentionally changing firmware. A Tapo configured only for home Wi-Fi needs to be joined to the demo hotspot before travelling. Power alone does not supply a video connection.

The same hotspot can be brought to university. Initial camera onboarding and model installation must be completed beforehand while online. Check current IP addresses after a move or power cycle. The camera, laptop and ESP32 need local connectivity; Telegram also needs internet. Whether the hotspot phone can simultaneously act as the remote must be rehearsed on that phone. A second phone may be needed for initial onboarding or as a controller.

Bring original power adapters, chargers, a power strip and charged rover batteries. A 20–30 minute cold-start rehearsal with the actual demonstration laptop, hotspot and all devices is still required. Follow the [university hotspot guide](../../laptop-test/TAPO_START_HERE.md#university-demo-using-your-phone-hotspot). Neither hotspot compatibility nor physical rover stopping has been verified by software tests.

## Run the demonstration

1. On a new demo laptop, run `laptop-test/01_INSTALL.bat` with internet, then `04_CHECK_SETUP.bat`. Configure the C212 in the dashboard's Camera setup or with `05_CONFIGURE_TAPO.bat`. Put the laptop, Tapo and main ESP32 on the same reachable network; the current main firmware expects `CAR`.
2. Open `00_START_NEURAL_ROVER.bat`. Enter name and optional ID/role, Choose & check photos, review the quality report and save the profile. Re-enroll legacy SFace profiles. Add varied photos to improve a current profile, then test using a separate photo.
3. Start the camera and check that the person matches in a different view. Test an unenrolled person, two faces in frame, different lighting, and the intended camera height.
4. Pair your private Telegram bot chat, mark the desired profiles, and run the test-message launcher. Enable Telegram before starting the camera. Verify that repeated sightings respect the cooldown and Unknown faces produce no alerts.
5. Place the rover on a stand with wheels off the floor. Enter its ESP32 IP address, connect, and verify hold-to-drive, release-to-stop, STOP, loss of focus, and network loss. Confirm the existing firmware is flashed and its command timeout is enabled before driving on the floor.

## Evidence to collect

Record laptop performance with both camera and recognition active. For each held-out attempt record the expected identity, actual label, lighting and distance. Include unenrolled faces and report false matches and missed matches separately. Validate Telegram on the actual phone and motor behavior on the physical rover. The prototype is not an access-control system and does not perform liveness checks.

See the [operating guide](../../laptop-test/FACE_START_HERE.md) and [verification notes](../../laptop-test/VERIFY.md).

Follow the operating guide's complete system test for today's integration run. The Tapo C212 remains the chosen camera; no LILYGO setup or replacement firmware is needed.
