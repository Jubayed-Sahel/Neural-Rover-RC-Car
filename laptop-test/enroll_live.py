"""Enroll a named, consenting participant from one continuous clear camera view.

Never saves images, sends Telegram messages or connects to the rover.
"""
import argparse
from collections import Counter
from pathlib import Path
import time

from face_recognition_demo import FaceEngine, read_gallery, read_profiles, save_person
from photo_enrollment import validate_profile
from recognition_policy import overlap
from rtsp_source import RTSPCamera, load_settings

ROOT = Path(__file__).resolve().parent


def collect_samples(camera,engine,duration=60,target=3,progress=print):
    samples = []
    issues = Counter()
    deadline = time.monotonic()+duration
    previous_seq = -1
    previous_row = None
    generation = camera.generation
    last_face = last_sample = 0
    next_progress = 0
    issue = 'Waiting for a clear, well-lit face.'
    while time.monotonic() < deadline and len(samples) < target:
        if camera.failure:
            raise RuntimeError(camera.failure)
        item = camera.get()
        if generation != camera.generation:
            samples.clear()
            previous_row = None
            generation = camera.generation
        if item is None or item[0] == previous_seq:
            time.sleep(.02)
        else:
            previous_seq,frame,retrieved = item
            rows = engine.detect_upright(frame)
            now = time.monotonic()
            if len(rows) != 1:
                issue = 'Keep exactly one face in view.'
                if now-last_face > 2:
                    samples.clear()
                    previous_row = None
            else:
                row = rows[0]
                if previous_row is not None and (now-last_face > 2 or overlap(previous_row,row) < .3):
                    samples.clear()
                previous_row,last_face = row,now
                issue = engine.quality_issue(row,frame,enrollment=True)
                if issue is None and now-last_sample >= .8:
                    sample = engine.embed(frame,row)
                    if generation != camera.generation or time.perf_counter()-retrieved > 2:
                        issue = 'Waiting for a fresh camera frame.'
                    elif samples and float(samples[0] @ sample) < .35:
                        issue = 'Views are inconsistent; keep the same person in view and face the camera.'
                    elif samples and max(float(old @ sample) for old in samples) >= .995:
                        issue = 'Turn slightly for a different view.'
                    else:
                        samples.append(sample)
                        last_sample = now
                        progress(f'Accepted view {len(samples)}/{target}.')
                        issue = 'Turn slightly left or right for the next view.'
            if issue:
                issues[issue] += 1
        if time.monotonic() >= next_progress:
            progress(f'{len(samples)}/{target} views. {issue or "Hold still briefly."}')
            next_progress = time.monotonic()+5
    if len(samples) < 3:
        dominant = issues.most_common(1)
        reason = dominant[0][0] if dominant else 'No usable views arrived.'
        raise ValueError(f'Enrollment not saved: only {len(samples)} distinct usable view(s). {reason}')
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',help='Display name of the consenting person who will be the only face in view; prompted if omitted')
    parser.add_argument('--duration',type=float,default=60)
    parser.add_argument('--samples',type=int,choices=(3,4,5),default=3)
    args = parser.parse_args()
    print('Keep exactly one consenting person in view, light the face from the front, and turn slightly for distinct views.',flush=True)
    name,_ = validate_profile(args.name if args.name is not None else input('Display name: '))
    if not 10 <= args.duration <= 180:
        parser.error('--duration must be between 10 and 180 seconds')
    engine = FaceEngine()
    camera = RTSPCamera(load_settings(ROOT/'camera.local.json'))
    try:
        samples = collect_samples(camera,engine,args.duration,args.samples)
    finally:
        camera.close()
    # Read again after capture to preserve profiles that changed during the test.
    gallery = read_gallery()
    name = next((saved for saved in gallery if saved.casefold()==name.casefold()),name)
    fields = read_profiles().get(name,{'id':'','role':''})
    save_person(gallery,name,samples,fields,append=name in gallery)
    print(f'Saved {name}: {len(read_gallery()[name])} distinct local templates. No images saved.',flush=True)
    print('Restart the dashboard to load the updated profile list.',flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,RuntimeError) as error:
        raise SystemExit(str(error))
