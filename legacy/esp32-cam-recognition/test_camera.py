import time

import cv2

from rover_common import LatestFrameReader, load_config


config = load_config()
stream_url = config["stream_url"]
reader = LatestFrameReader(stream_url)

print("Testing:", stream_url)
print("Close other webpages using the stream.")
print("Press Q in the video window to exit.")

start_time = time.monotonic()
displayed_frames = 0
last_sequence = -1

try:
    while True:
        frame, sequence = reader.latest()

        if frame is None:
            if time.monotonic() - start_time > 15:
                print("No camera frame received after 15 seconds.")
                print("Check the IP in config.json and the CAR hotspot.")
                break
            time.sleep(0.05)
            continue

        if sequence == last_sequence:
            time.sleep(0.005)
            continue

        last_sequence = sequence
        displayed_frames += 1

        elapsed = max(time.monotonic() - start_time, 0.001)
        fps = displayed_frames / elapsed
        height, width = frame.shape[:2]

        cv2.putText(
            frame,
            f"{width}x{height}   received {fps:.1f} FPS",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

        cv2.imshow("ESP32-CAM stream test", frame)

        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
            break

finally:
    reader.close()
    cv2.destroyAllWindows()
