# Neural Rover — face recognition and driving

**Browser workspace:** Double-click `00_START_NEURAL_ROVER.bat`. Daily operation now takes place at `http://127.0.0.1:8765/`, without running scripts manually. Use **Mission control**, **People library**, **Devices & network**, **Telegram alerts**, and **Demo readiness**. **Connect phone** shows the remote address and code. Camera setup is under **Devices & network**; enrollment starts with **People library → Add person**. The detailed desktop button names below refer to the legacy troubleshooting interface.

## Start

On a new Windows computer, install 64-bit Python 3.12 with Tkinter, then run `01_INSTALL.bat`. Run it once on this PC too if the new WebSocket dependency is missing. The first model check downloads the verified models, about 14 MB. Later face matching works offline on the LAN. Open **00_START_NEURAL_ROVER.bat** for the dashboard.

Before today's test, run **04_CHECK_SETUP.bat**. It verifies Python, dependency versions, cached model hashes, detector inference, the desktop interface and local configuration without opening devices or sending messages. Complete any ACTION items. Missing weights require `01_INSTALL.bat` while internet is available; the setup check itself does not download anything.

If the camera is not yet configured on this computer, click **Camera setup…** in the dashboard or use [the C212 setup guide](TAPO_START_HERE.md). Your existing local configuration is reused if you run from the same folder. The project uses the **Tapo C212**; LILYGO is not required.

## Enroll with photos

In **People**, enter the display name and optional ID and role. Click **Choose & check photos…**, select 1–10 JPG/PNG/WebP files of the same consenting person, and review the photo report before clicking **Save person**. Start with 3–5 clear photos with slight changes of angle and lighting. Each photo must show exactly one clear, fully visible face. The report explains skipped blurry, dark, overexposed, small or duplicate photos. Inconsistent identities block the batch; check that every photo shows the intended person. These checks are heuristics and can reject a usable photo or accept a poor one.

To improve someone already saved, select their profile and keep **Add photos** selected. **Replace photos** discards that person's old templates after confirmation. Up to 30 distinct templates can be stored per person. You can edit ID, role and alert preference without choosing more photos. Use **New person** to clear the form. Stop the camera first to change profiles. The app stores templates and profile details locally, without copying the original photos.

Older SFace enrollments cannot be used with the current ArcFace model. Re-enroll from photos; the first save preserves the old gallery in `faces.legacy.local.json`. Compatible ArcFace enrollments are preserved.

If you do not have photos, **07_ENROLL_FROM_CAMERA.bat** can enroll a named, consenting participant from the configured Tapo feed. Stop the dashboard camera, run the shortcut, enter the person's display name and keep exactly that person in view. Light the face from the front and turn slightly left and right. It requires three clear, distinct, consistent views and stores only local templates. A failed attempt saves nothing; views collected before a reconnect or a lost track are discarded. Restart the dashboard afterwards. If the name already exists, compatible new views are added rather than replacing it.

## Recognize and notify

Click **Start camera**. Faces are labeled with a matched name or **Unknown**. The panel also displays the matched person's role if provided. Start with clear light and the camera near face height.

**Checking…** means the same spatial face must match across at least three consecutive analyses spanning at least 0.25 seconds. An unknown/poor frame or ambiguous tracking immediately removes the name. **Balanced** is the starting mode; try **Strict** if unknown people receive names. Changes apply on the next camera start. Both use provisional thresholds, not calibrated confidence percentages. Use **Test a photo…** on a different photo from enrollment before the live test; it saves nothing. Scroll the People pane if controls are below the window.

For phone alerts, create a dedicated bot with [@BotFather](https://t.me/BotFather), run `10_CONFIGURE_TELEGRAM.bat`, and follow the pairing code instructions. If already paired, skip this. Run `11_TEST_TELEGRAM.bat` yourself to send one test message to your private chat. Mark the people you want alerts for, check **Telegram on start**, and start the camera. To change that session setting, stop and restart the camera. A marked identity must remain confirmed for three analyzed frames; alerts have a 60-second per-person cooldown within the session. Restarting the camera creates a new alert session. The dashboard reports delivery success or failure separately from recognition. Telegram receives the name and time as text, not the picture, profile ID, or templates. Delivery requires internet. Recognition and manual driving do not depend on delivery.

## Drive manually

Close any other rover control page. In **Rover controls**, enter the main ESP32's IP address (not the Tapo IP), click **Connect**, and hold one direction button. Release, move the pointer off it, lose focus, click **STOP**, or press **Escape** to stop. **Disconnect rover** stops and closes the connection. The app expires movement if the UI stops renewing it; the existing ESP32 firmware also has a command timeout if communication is lost. Test first with the wheels raised. The connection status confirms a WebSocket connection, not actual movement. Recognition and Telegram alerts never issue movement commands.

## Phone remote with Tapo video

Close other dashboard instances and run **13_START_PHONE_REMOTE.bat**, or click **Start phone remote** in the desktop app's Phone remote tab. The laptop serves the current camera view and recognition labels to a paired browser on your local network. This uses a new **laptop address**, not the old ESP32 page address, and does not require changing the existing main ESP32 firmware.

1. Keep the phone and laptop on the same reachable local network. The Tapo and ESP32 also need network access to the laptop.
2. Open the address shown in the **Phone remote** tab on the phone and enter the eight-digit code shown there. One paired phone is active; pairing another replaces it and stops any current movement. Do not share the code publicly. Pairing is temporary and expires after one hour or when sharing stops.
3. Connect the main ESP32 from **Rover controls** on the laptop. While phone sharing is on, laptop direction buttons are disabled; laptop STOP, Escape and Disconnect remain available. Use only one controller page.
4. Hold a phone direction button to drive; release, leave the button, press STOP, or leave the page to stop. Lost/expired control input and rover connection failures also stop movement. Delayed inputs cannot resume a stopped lease without another press.
5. **Camera and driving are independent.** You can drive without video, including when the stream fails or the camera is stopped. The hotspot/control connection, laptop and powered ESP32 must still work. Stopping the camera does not stop an active phone movement command; release the direction or press STOP whenever you need the rover stopped.
6. Click **Stop phone remote** before closing the laptop or changing networks. This closes the pairing session and stops phone movement.

Phone sharing uses a local HTTP service on port 8765 and does not provide public internet access. Do not publish or forward this service to the internet. If a Windows network permission is needed, handle it yourself for your intended demo network. The local service must be reachable from the phone; pairing cannot bypass a firewall or hotspot client isolation.

For the university setup, follow the [phone-hotspot rehearsal and packing guide](TAPO_START_HERE.md#university-demo-using-your-phone-hotspot) before travelling. Campus power by itself is not enough for camera streaming.

## Full system test for 22 November 2026

Use this sequence on the actual demonstration computer. Do not claim the hardware is verified until you have observed each result.

1. **Prepare the computer:** extract the latest package into a writable folder; do not run from inside the ZIP. For a new computer, run `01_INSTALL.bat` with internet, then `04_CHECK_SETUP.bat`. If the check reports a legacy SFace gallery, re-enroll before recognition. The current PC now has a current profile after live enrollment; the old gallery is backed up locally. Credentials and enrolled templates are not included in the ZIP and must be configured on the test computer.
2. **Put all devices on a reachable network:** laptop, Tapo C212 and main ESP32 must reach each other. The existing `ESP32_Controller.ino` expects a 2.4 GHz network named `CAR` with the default password `car123456`. Match that network for today's test, or deliberately update the main controller's network configuration if using another network. Telegram additionally needs internet. A guest hotspot with client isolation can prevent communication even when all devices appear connected.
3. **Verify the camera alone:** open the dashboard, click Camera setup if needed, select **Preview only**, and Start camera. Confirm fresh video and the intended view. Stop the camera before changing profiles or settings. Use stream1 for face detail if the laptop and Wi-Fi handle it; stream2 is the lower-bandwidth fallback. Close duplicate viewers.
4. **Enroll and test identities:** save 3–5 usable photos per person. Test with a different photo, then clear Preview only and start live recognition in Balanced mode with Telegram off. Include a known person, an unenrolled person, two faces, head turns, different lighting and the intended distances. Record wrong names and missed matches separately; use Strict if unknown people are incorrectly named. A poorly visible face should show quality guidance or Unknown rather than a trusted name.
5. **Verify your phone:** stop the camera, pair Telegram if needed, and run `11_TEST_TELEGRAM.bat` yourself. Confirm receipt on the phone. Mark one current profile, enable Telegram on start and restart recognition. Confirm a live alert, no alert for an unenrolled person, and no repeat for that person within the 60-second cooldown. Read the dashboard's Telegram delivery status.
6. **Verify the main controller with wheels raised:** use the existing Wi-Fi/WebSocket `Project Car Code/ESP32_Controller/ESP32_Controller.ino` baseline. `ESP32_Motor_Receiver.ino` is a different UART-only design and does not provide this dashboard's `/ws` interface. Do not replace the working firmware just to test the Python app. Connect the main ESP32 IP; check each direction, release-to-stop, pointer leaving a button, STOP, Escape, switching focus, Disconnect rover and communication loss. A lost connection must stop rather than resume movement. Reconnect manually and begin stopped.
7. **Run everything together:** with the wheels still raised, run recognition, selected-person alerts and manual controls together. Repeat the stop checks under video load. Only then test slowly on a clear floor. Run for 20–30 minutes; note inference milliseconds, video freezes, resets, wrong labels, missed labels and phone delivery. If recognition is slow, improve the view/lighting, try stream2, or reduce other work on the laptop; recheck accuracy after changing streams.
8. **Check recovery and finish:** stop/restart the camera, test camera or Wi-Fi interruption with the wheels raised, and confirm old images/names disappear. Recognition may recover its camera stream, while driving requires an explicit new connection after failure. Press STOP, disconnect the rover, stop the camera and close the dashboard before powering down.

Keep test notes in the private `results/` folder: computer used, date, camera stream/mounting height, lighting, distance, expected identity, actual label, alert delivery, stopping result and any error text. No automatic camera recording is enabled. A successful software check does not measure recognition accuracy or certify physical stopping.

## Local data and models

Keep `camera.local.json`, `faces.local.json`, `faces.legacy.local.json`, `alert_people.local.json` and `telegram.local.json` private. They are local plaintext and excluded from Git and the ZIP. The optional phone dashboard is paired and local to your network; there is no public remote endpoint or automatic image recording.

Uses OpenCV YuNet and InsightFace's Buffalo-SC ArcFace weights with OpenCV CPU inference. The weights are downloaded separately and verified by SHA-256. InsightFace lists these [pretrained weights for non-commercial research](https://github.com/deepinsight/insightface/blob/master/python-package/docs/model_zoo.md). This classroom prototype has no liveness detection.
