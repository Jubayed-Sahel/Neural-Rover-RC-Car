"""Behavioral regression tests; synthetic vectors do not measure model accuracy."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

import face_recognition_demo as faces
from photo_enrollment import review_photos
from recognition_policy import StableRecognizer


def row(x=0, y=0, size=100, confidence=.95):
    return np.array([x,y,size,size,x+30,y+35,x+70,y+35,x+50,y+55,x+35,y+75,x+65,y+75,confidence],dtype=np.float32)


class RecognitionTest(unittest.TestCase):
    def setUp(self):
        self.a, self.b = np.eye(faces.FEATURE_SIZE,dtype=np.float32)[:2]

    def test_rejects_ambiguous_and_unknown_identity(self):
        gallery = {'A':np.array([self.a]),'B':np.array([faces.unit(self.a+.1*self.b)])}
        self.assertEqual(faces.identify(self.a,gallery)[0],'Unknown')
        self.assertEqual(faces.identify(self.b,{'A':np.array([self.a])})[0],'Unknown')
        self.assertEqual(faces.identify(self.a*7,{'A':np.array([self.a])})[0],'A')

    def test_name_requires_frames_and_elapsed_time_then_drops_immediately(self):
        stable = StableRecognizer()
        gallery = {'A':1}
        for now in (0,.01,.02):
            self.assertEqual(stable.update([(row(),'A')],gallery,now)[0][1],'Checking…')
        self.assertEqual(stable.update([(row(),'A')],gallery,.3)[0][1],'A')
        self.assertEqual(stable.update([(row(),'Unknown')],gallery,.4)[0][1],'Unknown')
        self.assertEqual(stable.update([(row(),'A')],gallery,.5)[0][1],'Checking…')

    def test_disappearance_gap_and_identity_change_reset_evidence(self):
        for reset in ('missing','gap','identity','reset'):
            with self.subTest(reset=reset):
                stable = StableRecognizer()
                gallery = {'A':1,'B':1}
                for now in (0,.2,.4):
                    stable.update([(row(),'A')],gallery,now)
                if reset == 'missing': stable.update([],gallery,.5)
                if reset == 'reset': stable.reset()
                label = 'B' if reset == 'identity' else 'A'
                now = 2 if reset == 'gap' else .6
                self.assertEqual(stable.update([(row(),label)],gallery,now)[0][1],'Checking…')

    def test_two_people_do_not_share_history_and_ambiguous_overlap_resets(self):
        stable = StableRecognizer()
        gallery = {'A':1,'B':1}
        for now in (0,.2,.4):
            result = stable.update([(row(),'A'),(row(220),'B')],gallery,now)
        self.assertEqual([label for _,label in result],['A','B'])
        # Two detections compete for the previous A track: neither inherits it.
        result = stable.update([(row(5),'A'),(row(10),'A')],gallery,.6)
        self.assertEqual([label for _,label in result],['Checking…','Checking…'])

    def test_quality_guidance_for_dark_blurry_clipped_and_small_faces(self):
        engine = faces.FaceEngine.__new__(faces.FaceEngine)
        self.assertIn('dark',engine.quality_issue(row(),np.zeros((150,150,3),np.uint8)))
        self.assertIn('blurry',engine.quality_issue(row(),np.full((150,150,3),125,np.uint8)))
        self.assertIn('visible',engine.quality_issue(row(-60),np.full((150,150,3),125,np.uint8)))
        self.assertIn('small',engine.quality_issue(row(size=60),np.full((150,150,3),125,np.uint8),enrollment=True))
        bad = row(); bad[4] = np.nan
        self.assertFalse(engine.usable(bad,np.zeros((150,150,3),np.uint8)))

    def test_detector_is_bounded_and_landmarks_return_to_original_pixels(self):
        class Detector:
            def setInputSize(self,size): self.size = size
            def detect(self,image): return None,np.array([row(100,50)])
        engine = faces.FaceEngine.__new__(faces.FaceEngine)
        engine.detector = Detector()
        frame = np.zeros((1000,2000,3),np.uint8)
        view, rows = engine._oriented_view(frame,0)
        self.assertIs(view,frame)
        self.assertLessEqual(max(engine.detector.size),960)
        np.testing.assert_allclose(rows[0][:14],row(100,50)[:14]/.48,rtol=1e-5)
        self.assertEqual(rows[0][-1],row()[-1])

    def test_rotated_and_upright_people_are_both_kept(self):
        engine = faces.FaceEngine.__new__(faces.FaceEngine)
        engine.frame_index,engine.orientation = 11,0
        views = {0:[(row(),'A')],1:[(row(220),'B')],2:[],3:[(row(2,confidence=.8),'Unknown')]}
        engine._match_view = lambda frame,turns,gallery:(turns,views[turns],0,False)
        found = engine.identify_faces(None,{'A':1,'B':1})
        self.assertEqual([label for _,label in found],['A','B'])
        self.assertEqual(engine.orientation,1)

    def test_add_preserves_profiles_deduplicates_and_rejects_wrong_person(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'faces.local.json'
            with patch.object(faces,'GALLERY',path):
                faces.save_person({},'A',[self.a],{'role':'Student'})
                new = faces.unit(self.a+.3*self.b)
                faces.save_person(faces.read_gallery(),'A',[self.a,new],append=True)
                self.assertEqual(len(faces.read_gallery()['A']),2)
                self.assertEqual(faces.read_profiles()['A']['role'],'Student')
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError,'do not match'):
                    faces.save_person(faces.read_gallery(),'A',[self.b],append=True)
                self.assertEqual(path.read_bytes(),before)

    def test_photo_review_reports_bad_files_and_duplicates_without_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            first,second,bad = [Path(folder)/name for name in ('one.png','two.png','bad.png')]
            Image.new('RGB',(100,100)).save(first)
            Image.new('RGB',(100,100)).save(second)
            bad.write_text('invalid photo')
            a = self.a
            class Engine:
                def detect_upright(self,frame): return [row()]
                def usable(self,*args): return True
                def quality_issue(self,*args,**kwargs): return None
                def embed(self,*args): return a
            review = review_photos([first,second,bad],Engine())
            self.assertEqual(len(review.samples),1)
            self.assertEqual(len(review.rejected),2)
            self.assertIn('Duplicate',review.rejected[0][1])
            self.assertFalse((Path(folder)/'faces.local.json').exists())

    def test_mixed_people_in_enrollment_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder)/f'{n}.png' for n in range(2)]
            for path in paths: Image.new('RGB',(100,100)).save(path)
            embeddings = iter([self.a,self.b])
            class Engine:
                def detect_upright(self,frame): return [row()]
                def usable(self,*args): return True
                def quality_issue(self,*args,**kwargs): return None
                def embed(self,*args): return next(embeddings)
            with self.assertRaisesRegex(ValueError,'same person'):
                review_photos(paths,Engine())


if __name__ == '__main__':
    unittest.main()
