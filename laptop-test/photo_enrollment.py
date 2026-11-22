"""Extract face templates locally from consenting participants' photos."""
import re
import io
from dataclasses import dataclass, field
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps


def validate_profile(name, person_id='', role=''):
    name, person_id, role = (value.strip() for value in (name, person_id, role))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,39}', name) or name.casefold() == 'unknown':
        raise ValueError('Use a unique display name (1–40 Latin letters, digits, spaces, hyphens or underscores).')
    if len(person_id) > 40 or len(role) > 60 or any(not c.isprintable() for c in person_id + role):
        raise ValueError('Use printable ID and role values, up to 40 and 60 characters respectively.')
    return name, {'id': person_id, 'role': role}


@dataclass
class PhotoReview:
    samples: list = field(default_factory=list)
    accepted: list = field(default_factory=list)
    rejected: list = field(default_factory=list)

    def summary(self):
        lines = [f'{len(self.samples)} usable photo(s), {len(self.rejected)} skipped.']
        lines.extend(f'{name}: {reason}' for name, reason in self.rejected)
        if len(self.samples) < 3:
            lines.append('Tip: add 3–5 clear photos with slight angle and lighting changes.')
        return '\n'.join(lines)


@dataclass
class UploadedPhoto:
    name: str
    data: bytes


def review_photos(paths, engine):
    """Review all photos before saving. Never silently accept a mixed identity set."""
    if not 1 <= len(paths) <= 10:
        raise ValueError('Choose 1–10 photos of the same person.')
    review = PhotoReview()
    for raw_path in paths:
        uploaded = isinstance(raw_path, UploadedPhoto)
        path = Path(raw_path.name) if uploaded else Path(raw_path)
        try:
            if (len(raw_path.data) if uploaded else path.stat().st_size) > 20_000_000:
                raise ValueError('File is larger than 20 MB.')
            with Image.open(io.BytesIO(raw_path.data) if uploaded else path) as image:
                if image.width * image.height > 24_000_000:
                    raise ValueError('Photo exceeds 24 megapixels.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1280, 1280))
                frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
            rows = engine.detect_upright(frame)
            if len(rows) != 1 or not engine.usable(rows[0], frame):
                raise ValueError('Use a photo with exactly one clear, fully visible face.')
            issue = engine.quality_issue(rows[0], frame, enrollment=True)
            if issue:
                raise ValueError(issue)
            sample = engine.embed(frame, rows[0])
            if any(float(old @ sample) >= 0.995 for old in review.samples):
                raise ValueError('Duplicate view; use another angle or lighting condition.')
            review.samples.append(sample)
            review.accepted.append(path.name)
        except (OSError, ValueError, Image.DecompressionBombError, cv2.error) as error:
            review.rejected.append((path.name, str(error)))
    if len(review.samples) > 1:
        similarities = np.stack(review.samples) @ np.stack(review.samples).T
        # A medoid allows frontal/turned variation but every sample must agree
        # with the same representative; no chain of unrelated photos is accepted.
        medoid = int(np.argmax(np.median(similarities, axis=1)))
        if np.min(similarities[medoid]) < 0.30:
            raise ValueError('These photos do not consistently match one person. Choose clear photos of the same person and check again.')
    return review


def extract_samples(paths, engine):
    """Strict compatibility entry point used by scripts: no partial import."""
    review = review_photos(paths, engine)
    if review.rejected:
        raise ValueError(review.summary())
    return review.samples
