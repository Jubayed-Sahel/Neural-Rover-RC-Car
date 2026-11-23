# Neural Rover final demo runbook

## Start the demo

1. Turn on **CAR** on Phone 1. Leave mobile data off for the local camera and driving checks.
2. Connect the demo laptop and Phone 2 to CAR over Wi-Fi. Ethernet can provide internet to the laptop separately. Power the Tapo C212 and the rover.
3. Double-click `START_ROVER.bat` on the laptop and open [Mission control](http://127.0.0.1:8765/). The demo laptop already has dependencies and face models. On a replacement laptop, run `INSTALL_ROVER.bat` while online and verify with `CHECK_SETUP.bat`.

## Find the current IP addresses

| Device | Where to look | Where to use it |
| --- | --- | --- |
| Tapo camera | On Phone 2, open Tapo **Device Info**. In Phone 1's CAR client list, look for MAC `b8:fb:b3:52:e4:9a`. Last verified at `192.168.89.54`. | **Devices & network → Tapo camera** |
| Demo laptop | Click **Connect phone** in the dashboard, or run `ipconfig` and read **Wireless LAN adapter Wi-Fi → IPv4 Address**. Last verified at `192.168.89.30`. | On Phone 2, open the displayed remote address including port `8765` and enter the pairing code. |
| Main ESP32 | Phone 1 shows MAC addresses only. The main ESP32 MAC is `8C-94-DF-90-79-A8`, last verified at `192.168.89.176`. While on CAR, run `Get-NetNeighbor -InterfaceAlias Wi-Fi -AddressFamily IPv4 \| Where-Object LinkLayerAddress -eq '8C-94-DF-90-79-A8'` in PowerShell, or read the ESP32 serial output if the neighbor entry is missing. | **Devices & network → Main ESP32** or the ESP32 field in **Mission control** |

Recheck the addresses after restarting the hotspot or reconnecting a device. On the laptop itself, always open the dashboard at `127.0.0.1:8765`.

## Verify the Tapo feed

1. In **Mission control**, select **Camera preview → Start / apply**. Look for **LIVE**. The demo camera uses **stream1**, verified at **1920 × 1080**. Try **stream2** if video stutters.
2. If the IP changed, update it under **Devices & network**. Leave the password field blank to keep the saved password.
3. If the laptop reports **401 Unauthorized** while Phone 2 can see video, check **Tapo → Device Settings → Advanced Settings → Camera Account**. Save the exact local camera username and password in the dashboard. If RTSP port **554** refuses connections, verify the IP and check that the Camera Account is set up.
4. For recognition, enroll consenting participants in **People library**, select **Face recognition → Start / apply**, and verify the intended profile appears before enabling alerts.

## Next rehearsal: dashboard driving

1. Raise the drive wheels. Click **Connect** beside the saved address in **Mission control**. Wait for **Connected**. If the address changed, enter its current IP and connect again to save it locally.
2. Under **Mission control → Manual driving**, briefly hold a direction and release. Verify the wheels stop on release, then check **STOP** and **Escape** before a floor test.
3. If connection fails, check the controller's power and current CAR address. For optional phone driving, pair Phone 2 after verifying laptop control.

## Last rehearsal: Telegram through Phone 1

1. Turn on **Phone 1 mobile data** while keeping CAR on.
2. Temporarily unplug laptop Ethernet when safe to do so. This verifies that delivery uses CAR mobile data. Unplugging can interrupt remote support.
3. In **Telegram alerts**, pair the intended private chat if needed. Click **Send a test notification**, then confirm the message arrives in Telegram on Phone 2.
4. If recognition-triggered alerts are part of the demo, mark a consenting enrolled profile for alerts, enable them, and verify a separate recognition-triggered message.

## Handoff status as of 23 November 2026

- Verified on the demo laptop: dashboard, cached face model initialization, and live Tapo preview over CAR with Phone 1 mobile data off.
- The main ESP32 was identified and dashboard driving worked. Check stopping during rehearsal, verify phone pairing if needed, and confirm Telegram delivery over CAR mobile data.
- Keep camera credentials, pairing codes, bot tokens, and face templates on the devices. Local settings files are excluded from Git.
