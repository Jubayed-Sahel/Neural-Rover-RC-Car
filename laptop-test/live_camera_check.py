"""Explicit live Tapo test. Saves aggregate metrics, never images or templates.

No Telegram API calls or rover commands are made. Use --compare to test the two
streams sequentially. This is an operational test, not an accuracy evaluation.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import time

import numpy as np

from face_recognition_demo import FaceEngine, read_document, read_gallery
from rtsp_source import RTSPCamera, load_settings

ROOT = Path(__file__).resolve().parent


def summarize(values):
    if not values:
        return None
    return {'median':round(float(np.median(values)),2),
            'p95':round(float(np.percentile(values,95)),2),
            'max':round(float(max(values)),2)}


def examine(settings, engine, gallery, duration, analyze_interval=.25, camera_factory=RTSPCamera):
    camera = camera_factory(settings)
    started = time.monotonic()
    previous_seq = -1
    previous_retrieved = None
    first_seq = first_retrieved = last_seq = last_retrieved = None
    next_analysis = 0
    shapes, labels, quality, states = Counter(),Counter(),Counter(),[]
    age_ms, gaps_ms, inference_ms, widths = [],[],[],[]
    observed = analyses = detections = match_frames = reconnects = stale_results = 0
    generation = None
    failure = None
    try:
        while time.monotonic() - started < duration:
            if camera.failure:
                failure = camera.failure
                break
            status = camera.status
            if not states or states[-1]['status'] != status:
                states.append({'seconds':round(time.monotonic()-started,2),'status':status})
            item = camera.get()
            if item is None or item[0] == previous_seq:
                time.sleep(.01)
                continue
            seq,frame,retrieved = item
            previous_seq = seq
            if generation is not None and generation != camera.generation:
                reconnects += 1
                previous_retrieved = None
            generation = camera.generation
            observed += 1
            shapes[f'{frame.shape[1]}x{frame.shape[0]}'] += 1
            age_ms.append(max(0,time.perf_counter()-retrieved)*1000)
            if previous_retrieved is not None:
                gaps_ms.append((retrieved-previous_retrieved)*1000)
            previous_retrieved = retrieved
            if first_seq is None:
                first_seq,first_retrieved = seq,retrieved
            last_seq,last_retrieved = seq,retrieved
            if time.monotonic() < next_analysis:
                continue
            before = time.perf_counter()
            found = engine.identify_faces(frame,gallery)
            inference_ms.append((time.perf_counter()-before)*1000)
            analyses += 1
            next_analysis = time.monotonic()+analyze_interval
            # Do not report matches from an expired image or an old session.
            if generation != camera.generation or time.perf_counter()-retrieved > settings.get('stale_seconds',2):
                stale_results += 1
                continue
            detections += len(found)
            match_frames += int(any(label in gallery for _,label in found))
            for row,label in found:
                widths.append(float(row[2]))
                # Store only category counts. Never write a matched person's name.
                labels['known_candidate' if label in gallery else 'unknown' if label == 'Unknown' else 'quality_guidance'] += 1
                if label not in gallery and label != 'Unknown':
                    bucket = next((kind for prefix,kind in (
                        ('Move closer','clipped_or_too_small'),('Face too small','too_small'),
                        ('Too dark','too_dark'),('Too bright','too_bright'),
                        ('Face looks blurry','blurry_or_low_contrast'),('Face alignment','alignment'))
                        if label.startswith(prefix)), 'other')
                    quality[bucket] += 1
    finally:
        camera.close()
    elapsed = time.monotonic()-started
    if not observed and failure is None:
        failure = 'No video frames arrived during this timed test.'
    capture_seconds = (last_retrieved-first_retrieved) if observed > 1 else 0
    return {
        'stream':settings.get('stream','stream1'),'duration_seconds':round(elapsed,2),
        'video_received':bool(observed),'failure':failure,'resolutions':dict(shapes),
        'frames_observed':observed,'capture_fps_estimate':round((last_seq-first_seq)/capture_seconds,2) if capture_seconds > 0 else None,
        'connection_attempts':camera.attempts.value,'reconnects':reconnects,
        'frame_age_at_read_ms':summarize(age_ms),'observed_frame_gap_ms':summarize(gaps_ms),
        'analyses':analyses,'inference_ms':summarize(inference_ms),'face_detections':detections,
        'face_width_pixels':summarize(widths),'face_categories':dict(labels),'quality_guidance_counts':dict(quality),
        'frames_with_known_candidate':match_frames,'stale_results_discarded':stale_results,
        'camera_states':states,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=float,default=20,help='Seconds per stream (5–120)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stream',choices=('stream1','stream2'))
    mode.add_argument('--compare',action='store_true')
    args = parser.parse_args()
    if not 5 <= args.duration <= 120:
        parser.error('--duration must be between 5 and 120 seconds')
    settings = load_settings(ROOT/'camera.local.json')
    document = read_document()
    gallery = read_gallery()
    engine = FaceEngine()
    selected = args.stream or settings.get('stream','stream1')
    streams = [selected] + ([other for other in ('stream1','stream2') if other != selected] if args.compare else [])
    report = {'timestamp_pc_local':datetime.now().astimezone().isoformat(),
              'gallery_version':document.get('version'),'current_profiles':len(gallery),
              'identity_accuracy_evaluated':False,'frames_saved':0,'templates_saved':0,
              'telegram_contacted':False,'rover_contacted':False,'tests':[]}
    for stream in streams:
        print(f'Testing {stream} for {args.duration:g} seconds; no images or templates will be saved.',flush=True)
        try:
            result = examine({**settings,'stream':stream},engine,gallery,args.duration)
        except Exception:
            # Backend exceptions can include device URLs. Keep output redacted.
            result = {'stream':stream,'video_received':False,'failure':'Camera/model check failed; inspect saved setup and the offline model check.'}
        report['tests'].append(result)
        print(json.dumps(result,indent=2),flush=True)
    folder = ROOT/'results'
    folder.mkdir(exist_ok=True)
    path = folder/f'live_camera_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Aggregate report saved:',path.name)
    if not gallery:
        print('Named recognition was not verified: enroll current profiles first. Live model inference was exercised with an empty gallery.')
    return int(any(not test.get('video_received') or test.get('failure') for test in report['tests']))


if __name__ == '__main__':
    raise SystemExit(main())
