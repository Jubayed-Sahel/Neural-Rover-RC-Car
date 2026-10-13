"""Experimental single-person temporal baseline, independent of camera/model."""
from collections import deque
from dataclasses import dataclass
import math


@dataclass
class Observation:
    time: float
    hip_y: float
    body_scale: float
    torso_angle: float


class FallDetector:
    def __init__(self, settings):
        self.settings = settings
        self.history = deque()
        self.candidate = None
        self.low_since = None
        self.last_time = None
        self.latched = False
        self.state = "UNKNOWN"
        self.reason = "Waiting for a visible full body"

    def reset(self):
        self.history.clear()
        self.candidate = self.low_since = self.last_time = None
        self.latched = False
        self.state = "UNKNOWN"
        self.reason = "Reset; waiting for reliable tracking"

    def update(self, observation, timestamp):
        event = None
        if self.last_time is not None and (
            timestamp <= self.last_time or
            timestamp - self.last_time > self.settings["max_gap_seconds"]
        ):
            self.history.clear()
            self.candidate = self.low_since = None
        self.last_time = timestamp
        if observation is None:
            self.history.clear()
            self.candidate = self.low_since = None
            self.state = "UNKNOWN"
            self.reason = "Full body missing or low landmark confidence"
            return self.state, event
        if self.latched:
            self.state = "POST_FALL"
            self.reason = "Possible-fall alert latched; press A to acknowledge/reset"
            return self.state, event
        self.history.append(observation)
        while self.history and timestamp - self.history[0].time > self.settings["descent_window_seconds"]:
            self.history.popleft()
        horizontal = observation.torso_angle >= self.settings["horizontal_angle_degrees"]
        # Require an earlier upright pose, not an already-lying person at startup.
        references = [o for o in self.history if o.torso_angle < 35 and timestamp - o.time >= 0.08]
        reference = min(references, key=lambda o: o.hip_y) if references else None
        drop = ((observation.hip_y - reference.hip_y) / reference.body_scale) if reference else 0
        if self.candidate is None and horizontal and drop >= self.settings["minimum_drop_body_units"]:
            self.candidate = (timestamp, reference.hip_y, reference.body_scale)
            self.low_since = timestamp
        if self.candidate is not None:
            started, baseline_y, scale = self.candidate
            low = horizontal and (observation.hip_y - baseline_y) / scale >= self.settings["minimum_drop_body_units"]
            if timestamp - started > self.settings["candidate_timeout_seconds"] or not low:
                self.candidate = self.low_since = None
            else:
                self.state = "POSSIBLE_FALL"
                self.reason = "Observed descent and horizontal posture; checking persistence"
                if timestamp - self.low_since >= self.settings["minimum_low_seconds"]:
                    self.latched = True
                    self.state = "POST_FALL"
                    self.reason = "Experimental possible-fall alert; requires human review"
                    event = {"source_time_seconds": timestamp, "candidate_time_seconds": started,
                             "confirmation_delay_seconds": timestamp - started, "reason": self.reason}
                return self.state, event
        self.state = "NORMAL"
        self.reason = "No fall transition observed (not a guarantee of safety)"
        return self.state, event


def observation_from_landmarks(landmarks, width, height, timestamp, visibility):
    required = (11, 12, 23, 24, 25, 26, 27, 28)
    if not landmarks or any(
        min(landmarks[i].visibility, landmarks[i].presence) < visibility or
        not (0 <= landmarks[i].x <= 1 and 0 <= landmarks[i].y <= 1)
        for i in required
    ):
        return None
    def midpoint(a, b):
        return ((landmarks[a].x + landmarks[b].x) * width / 2,
                (landmarks[a].y + landmarks[b].y) * height / 2)
    shoulder = midpoint(11, 12)
    hip = midpoint(23, 24)
    scale = max(p.y * height for p in (landmarks[i] for i in required)) - min(
        p.y * height for p in (landmarks[i] for i in required))
    if scale < 40:
        return None
    angle = math.degrees(math.atan2(abs(hip[0] - shoulder[0]), abs(hip[1] - shoulder[1])))
    return Observation(timestamp, hip[1], scale, angle)
