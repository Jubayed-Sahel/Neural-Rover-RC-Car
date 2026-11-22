from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

import numpy as np

import enroll_live


class Clock:
    now = 0
    def monotonic(self): return self.now


class Camera:
    generation = 1
    failure = None
    def __init__(self,clock,reconnect=False):
        self.clock,self.index,self.reconnect = clock,0,reconnect
    def get(self):
        self.clock.now += 1
        self.index += 1
        if self.reconnect and self.index >= 3: self.generation = 2
        return self.index,np.full((150,150,3),self.index,np.uint8),time.perf_counter()


class Engine:
    def __init__(self,poor=False): self.poor = poor
    def detect_upright(self,frame): return [np.array([20,20,100,100])]
    def quality_issue(self,*args,**kwargs): return 'Too dark; add light.' if self.poor else None
    def embed(self,frame,row):
        theta = int(frame[0,0,0])*.2
        vector = np.zeros(512,dtype=np.float32)
        vector[:2] = np.cos(theta),np.sin(theta)
        return vector


class LiveEnrollmentTest(unittest.TestCase):
    def test_collects_distinct_consistent_views_without_saving_images(self):
        clock = Clock()
        camera = Camera(clock)
        progress = []
        with patch.object(enroll_live.time,'monotonic',clock.monotonic):
            samples = enroll_live.collect_samples(camera,Engine(),20,3,progress.append)
        self.assertEqual(len(samples),3)
        self.assertTrue(all(sample.shape == (512,) for sample in samples))
        self.assertIn('Accepted view 3/3.',progress)

    def test_reconnect_discards_previous_session_templates(self):
        clock = Clock()
        camera = Camera(clock,reconnect=True)
        with patch.object(enroll_live.time,'monotonic',clock.monotonic):
            samples = enroll_live.collect_samples(camera,Engine(),20,3,lambda _:None)
        self.assertEqual(len(samples),3)
        # Session 1 had two views; the returned batch starts at frame 3.
        self.assertAlmostEqual(float(samples[0][0]),float(np.cos(.6)),places=5)

    def test_poor_faces_never_return_a_partial_enrollment(self):
        clock = Clock()
        camera = Camera(clock)
        with patch.object(enroll_live.time,'monotonic',clock.monotonic):
            with self.assertRaisesRegex(ValueError,'Enrollment not saved.*Too dark'):
                enroll_live.collect_samples(camera,Engine(poor=True),10,3,lambda _:None)


if __name__ == '__main__':
    unittest.main()
