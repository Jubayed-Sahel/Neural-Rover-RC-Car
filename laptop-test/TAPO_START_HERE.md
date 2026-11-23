# Tapo C212 setup

1. Add the camera in the Tapo app. Put the camera and computer on the same reachable home network (the computer may be on Ethernet).
2. In the camera settings, open **Advanced Settings → Camera Account**. Create local camera credentials separate from your Tapo login.
3. Find its local IP in Device Info or the router's connected devices. Run `05_CONFIGURE_TAPO.bat`, enter that IP and the credentials, and choose `stream1`.
4. Run `06_PREVIEW_TAPO.bat` for a camera-only check, or start the camera from `00_START_NEURAL_ROVER.bat`. Close any other preview that may be consuming the stream.

If playback fails, check camera power, Privacy Mode, same-network connectivity, the IP and local credentials. Try `stream2` if needed; the lower-quality stream can make small faces harder to recognize. Confirm separately with VLC using the [official Tapo RTSP instructions](https://www.tp-link.com/us/support/faq/2680/). Do not share the authenticated RTSP URL or the local settings file.

## University demo using your phone hotspot

**The camera needs both power and a working local network. Power alone will not provide a live stream to the laptop.** Once set up, local viewing can work without internet; onboarding and cloud services have different requirements. Complete initial setup while internet is available. [TP-Link camera FAQ](https://www.tp-link.com/sg/support/faq/2742/)

The chosen portable network is your **phone hotspot**. Connect the **Tapo C212, demonstration laptop and main ESP32** to it. The phone remote uses that same local network. Do not depend on university Wi-Fi for the core demonstration.

### Prepare at home before moving anything

1. **Use the exact hotspot phone you will take to university.** Set its hotspot to **2.4 GHz** with compatible WPA2 security. The current controller sketch expects the network name **CAR** and its existing default password **car123456**, both case-sensitive. Matching these avoids changing the ESP32 firmware just for the demo. Configure enough connected-device slots for the camera, laptop and ESP32; a separate remote phone needs another slot. Keep the hotspot phone charged and check its automatic hotspot-shutdown behavior.
2. **For iPhone:** the hotspot name follows the device name; changing the name is under Settings → General → About → Name. Use Personal Hotspot's **Maximize Compatibility** option where available. Android menu names vary; look for the hotspot's band/security settings. [Apple hotspot instructions](https://support.apple.com/en-gb/111785)
3. **Move the camera onto this hotspot before the demonstration day.** A camera configured only for your home Wi-Fi will not automatically join an unfamiliar CAR hotspot. Use the Tapo app's supported network setup procedure. TP-Link documents matching an existing SSID, password and encryption type, or resetting/reconfiguring when settings cannot be matched. Check your model's instructions and preserve settings before any reset. If resetting clears the local Camera Account, configure that account again and update the dashboard. Do this at home while online. [TP-Link network-change guidance](https://www.tp-link.com/us/support/faq/3840/)
4. **Allow for a second phone during setup.** If the hotspot-hosting phone cannot also perform the Tapo onboarding steps, borrow a second phone with the Tapo app and connect it to the hotspot. This is a setup contingency, not a proven requirement for every phone.
5. **Join the actual demo laptop to CAR.** Install Python/dependencies and download models in advance. Run `04_CHECK_SETUP.bat` on that laptop. The shareable ZIP excludes model weights, local credentials and enrolled profiles; it does not reproduce the configured desktop by itself. Either configure and enroll on the laptop, or transfer compatible `.local.json` files privately between your own computers. Keep those files out of shared ZIPs and Git. Do not copy the desktop virtual environment as a laptop installation.
6. **Check the camera and rover IP addresses on this hotspot.** Their old home-network IPs may be wrong, and hotspot DHCP can change addresses after a restart. Find the camera's address in the Tapo app/device information or hotspot client list, and update Camera setup. Find the main ESP32's address in the hotspot client list or from its working mDNS/serial information, then enter its numerical IP under Rover controls. `rover.local` resolution is a convenience, not a demo prerequisite. Phone hotspots may not offer address reservations, so do not assume addresses will stay fixed.
7. **Run `13_START_PHONE_REMOTE.bat` with other rover dashboards closed.** Open **Phone remote** on the laptop, read the newly displayed address, open that address in the phone browser, and enter the pairing code. Use this laptop address for the unified Tapo view and driving page. If Windows requires inbound access for Python, handle the permission yourself for the intended local/private network; do not disable the firewall as a workaround.
8. **Test the hotspot phone as the remote.** We have not verified whether your particular phone can browse a client laptop while hosting the hotspot, or whether it isolates clients. Confirm it at home. If it cannot, use a second phone/tablet connected to the hotspot as the remote. If the camera, laptop and ESP32 cannot reach each other through that hotspot at all, choose a working network device before the demo; application code cannot remove hotspot isolation.
9. **Rehearse the exact event sequence:** power everything off, turn the hotspot on first, then power the camera and ESP32, connect the laptop, verify addresses, start the app and pair the remote. Raise the wheels for initial motor checks. Run the actual laptop, phone, camera and rover together for at least 20–30 minutes. Repeat after another power cycle. Confirm recognition, control and stop behavior, and phone alerts if enabled. This rehearsal has not yet been completed on the hotspot.

### What requires internet?

- The configured Tapo feed, cached recognition models and local rover control use the local network. The hotspot must remain on and permit communication even if its internet uplink is unavailable.
- Telegram delivery requires mobile internet. Local recognition and driving do not depend on successful Telegram delivery. The phone/carrier may tie hotspot availability to cellular service, so test the actual phone rather than assuming it will offer an offline hotspot.
- Video loss does **not** disable driving in the updated phone remote. Losing the hotspot or the phone–laptop–ESP32 control connection is different: the control link must work, and stale movement commands expire.

### Power and packing

Bring the **camera's original adapter**, laptop charger, hotspot-phone charger/power bank, charged rover batteries and an extension/power strip. Check the camera's own voltage/polarity label if changing its supply. The current tested plan keeps Tapo stationary and powered through its adapter. Mounting it on the moving rover would also require a suitable mobile power solution; that has not been verified. Do not assume the rover's existing supply or an ordinary USB cable is suitable for the camera.

### At university

Use the same phone, hotspot name, password, security mode and equipment as the successful rehearsal. Power on the hotspot first; then camera, rover and laptop. Check IPs, run the launcher, and use the current address and pairing code shown in the app. You should not need to repeat Wi-Fi onboarding if the saved hotspot settings are unchanged and the devices reconnect, but **zero configuration on the day is not guaranteed**. Leave time for address checks, power and lighting adjustments.
