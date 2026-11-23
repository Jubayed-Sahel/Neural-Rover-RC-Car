import json
from types import SimpleNamespace
import time
import unittest

import numpy as np

from live_camera_check import examine


class Camera:
    failure = None
    status = 'STREAMING'
    generation = 1
    attempts = SimpleNamespace(value=1)

    def __init__(self,*args):
        self.index = 0
        self.closed = False

    def get(self):
        if self.index >= 3:
            return None
        self.index += 1
        return self.index,np.full((120,160,3),self.index,np.uint8),time.perf_counter()

    def close(self):
        self.closed = True


class Engine:
    def identify_faces(self,frame,gallery):
        label = ('Private Fixture Name','Unknown','Too dark; add light in front of the face.')[int(frame[0,0,0])-1]
        return [(np.array([10,10,70,70]),label)]


class LiveCheckTest(unittest.TestCase):
    def test_only_aggregate_categories_are_saved_and_capture_is_closed(self):
        camera = Camera()
        result = examine({'stream':'stream1'},Engine(),{'Private Fixture Name':1},.05,0,lambda _:camera)
        self.assertTrue(camera.closed)
        self.assertTrue(result['video_received'])
        self.assertEqual(result['face_categories'],{'known_candidate':1,'unknown':1,'quality_guidance':1})
        self.assertEqual(result['quality_guidance_counts'],{'too_dark':1})
        self.assertEqual(result['frames_with_known_candidate'],1)
        self.assertEqual(result['resolutions'],{'160x120':3})
        self.assertNotIn('Private Fixture Name',json.dumps(result))

    def test_slow_inference_discards_expired_matches(self):
        camera = Camera()
        class SlowEngine:
            def identify_faces(self,*args):
                time.sleep(.005)
                return [(np.array([10,10,70,70]),'Known')]
        result = examine({'stream':'stream2','stale_seconds':.001},SlowEngine(),{'Known':1},.04,0,lambda _:camera)
        self.assertEqual(result['stale_results_discarded'],3)
        self.assertEqual(result['frames_with_known_candidate'],0)
        self.assertEqual(result['face_detections'],0)
        self.assertTrue(camera.closed)

    def test_camera_with_no_frames_is_reported_as_a_failure(self):
        camera = Camera()
        camera.index = 3
        result = examine({},Engine(),{},.02,0,lambda _:camera)
        self.assertFalse(result['video_received'])
        self.assertIn('No video frames',result['failure'])
        self.assertTrue(camera.closed)


if __name__ == '__main__':
    unittest.main()
