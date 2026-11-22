"""Conservative live identity confirmation, independent of inference and the UI."""
from dataclasses import dataclass
import time


# Starting points for this prototype, not calibrated accuracy guarantees.
MATCH_MODES = {'Balanced': (0.40, 0.06), 'Strict': (0.50, 0.10)}


def overlap(a, b):
    ax, ay, aw, ah = (float(v) for v in a[:4])
    bx, by, bw, bh = (float(v) for v in b[:4])
    intersection = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return intersection / max(1, aw * ah + bw * bh - intersection)


@dataclass
class Track:
    row: object
    name: str
    count: int
    since: float
    seen: float


class StableRecognizer:
    """Require consecutive, unambiguous observations of the same spatial face.

    Unknown/poor frames immediately remove the name. Missing detections and
    ambiguous overlaps discard history rather than carrying a previous label.
    """
    def __init__(self, confirmations=3, minimum_seconds=0.25, maximum_gap=1.2):
        self.confirmations = confirmations
        self.minimum_seconds = minimum_seconds
        self.maximum_gap = maximum_gap
        self.reset()

    def reset(self):
        self.tracks = []

    def update(self, found, gallery, now=None):
        now = time.monotonic() if now is None else now
        candidates = [[index for index, track in enumerate(self.tracks)
                       if 0 <= now - track.seen <= self.maximum_gap and overlap(row, track.row) >= 0.3]
                      for row, _ in found]
        uses = [sum(index in matches for matches in candidates) for index in range(len(self.tracks))]
        tracks, result = [], []
        for (row, label), matches in zip(found, candidates):
            if label not in gallery:
                result.append((row, label))
                continue
            previous = self.tracks[matches[0]] if len(matches) == 1 and uses[matches[0]] == 1 else None
            if previous and previous.name == label:
                track = Track(row, label, previous.count + 1, previous.since, now)
            else:
                track = Track(row, label, 1, now, now)
            tracks.append(track)
            confirmed = track.count >= self.confirmations and now - track.since >= self.minimum_seconds
            result.append((row, label if confirmed else 'Checking…'))
        self.tracks = tracks
        return result
