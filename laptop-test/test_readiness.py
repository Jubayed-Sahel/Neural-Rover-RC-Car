import json
from pathlib import Path
import tempfile
from threading import Event, Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import alert_people
from check_setup import inspect_gallery
import face_recognition_demo as faces
import rover_app
from recognition_policy import StableRecognizer
from rtsp_source import load_settings, save_settings, validate_settings
from telegram_alerts import TelegramAlerts, load_alert_settings


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_alert_launcher_uses_current_gallery_and_rejects_legacy(self):
        path = self.folder/'faces.local.json'
        sample = np.eye(512,dtype=np.float32)[0]
        with patch.object(faces,'GALLERY',path), patch.object(alert_people,'GALLERY',path):
            faces.save_person({},'Fixture',[sample])
            self.assertEqual(alert_people.enrolled_names(),['Fixture'])
            path.write_text(json.dumps({'version':1,'people':{'Old':[]}}))
            with self.assertRaisesRegex(ValueError,'Re-enroll'):
                alert_people.enrolled_names()

    def test_report_identifies_missing_legacy_valid_and_damaged_profiles(self):
        path = self.folder/'faces.local.json'
        self.assertEqual(inspect_gallery(path).level,'ACTION')
        path.write_text(json.dumps({'version':1,'people':{}}))
        self.assertIn('Legacy',inspect_gallery(path).detail)
        with patch.object(faces,'GALLERY',path):
            faces.save_person({},'Fixture',[np.eye(512,dtype=np.float32)[0]])
            self.assertEqual(inspect_gallery(path).level,'PASS')
        path.write_text(json.dumps({'version':2,'people':{'Bad':[[0]*512]}}))
        self.assertEqual(inspect_gallery(path).level,'ACTION')
        path.write_text('[]')
        self.assertEqual(inspect_gallery(path).level,'ACTION')

    def test_camera_save_is_validated_before_overwrite(self):
        path = self.folder/'camera.local.json'
        settings = {'host':'127.0.0.1','username':'fixture','password':'fixture-only','stream':'stream2'}
        save_settings(path,settings)
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            save_settings(path,{**settings,'stream':'wrong'})
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(load_settings(path)['host'],'127.0.0.1')
        self.assertFalse((self.folder/'camera.pending.local.json').exists())
        for invalid in ([],None,{'host':'127.0.0.1','username':{},'password':1}):
            with self.assertRaises(ValueError):
                validate_settings(invalid)

    def test_corrupt_local_files_produce_recovery_messages_without_dumping_contents(self):
        gallery,watch,telegram = [self.folder/name for name in ('faces.local.json','alert_people.local.json','telegram.local.json')]
        for path in (gallery,watch,telegram): path.write_text('[]')
        with patch.object(faces,'GALLERY',gallery):
            with self.assertRaisesRegex(ValueError,'recovery'):
                faces.read_gallery()
        with patch.object(alert_people,'WATCH',watch):
            self.assertEqual(alert_people.load_watch_names(),set())
        with patch('telegram_alerts.SETTINGS',telegram):
            self.assertIsNone(load_alert_settings())

    def test_alert_worker_exposes_delivery_failure_and_success_without_network(self):
        def fail(*args): raise RuntimeError('simulated failure')
        for sender,expected in ((fail,'Delivery failed'),(lambda *args:None,'Sent at')):
            with self.subTest(expected=expected):
                alerts = TelegramAlerts({},send=sender)
                try:
                    self.assertTrue(alerts.enqueue('Fixture'))
                    deadline = time.monotonic()+2
                    while expected not in alerts.status and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertIn(expected,alerts.status)
                    self.assertNotIn('Fixture',alerts.status)
                finally:
                    alerts.close()
                    alerts.thread.join(timeout=1)
                self.assertFalse(alerts.thread.is_alive())

    def test_full_monitor_confirms_faces_rejects_unknown_and_gates_mock_alerts(self):
        labels = ['Known']*5 + ['Unknown']*3 + ['Known']*5
        sent, published = [],[]
        monitor = rover_app.Monitor.__new__(rover_app.Monitor)
        monitor.stop,monitor.lock = Event(),Lock()
        def publish(frame,status,names=(),retrieved=0):
            if frame is not None: published.append(names)
        monitor.publish = publish
        class Camera:
            failure = None
            generation = 1
            def __init__(self,*args): self.calls=0; self.item=None
            def get(self):
                index = self.calls//2
                if index >= len(labels):
                    monitor.stop.set()
                    return None
                if self.calls%2 == 0:
                    self.item = (index,np.full((120,120,3),index,np.uint8),time.perf_counter())
                self.calls += 1
                return self.item
            def close(self): pass
        class Engine:
            def __init__(self,*args): pass
            def identify_faces(self,frame,gallery):
                index = int(frame[0,0,0])
                return [(np.array([10,10,80,80]),labels[index])]
        class Alerts:
            status = 'Ready'
            def __init__(self,*args): pass
            def enqueue(self,name): sent.append(name); return True
            def close(self): pass
        with patch.object(rover_app,'RTSPCamera',Camera),patch.object(rover_app,'FaceEngine',Engine),patch.object(rover_app,'TelegramAlerts',Alerts),patch.object(rover_app,'StableRecognizer',lambda:StableRecognizer(minimum_seconds=0)):
            monitor.run({}, {'Known':1}, {'Known'}, {'fixture':True}, False, 'Balanced')
        self.assertEqual(published[:2],[(),()])
        self.assertEqual(published[2],('Known',))
        self.assertEqual(published[5:10],[()]*5)
        self.assertEqual(published[10],('Known',))
        self.assertEqual(sent,['Known'])

    def test_disconnect_stops_before_closing(self):
        operations=[]
        app = rover_app.App.__new__(rover_app.App)
        app.held = 'held'
        app.rover = SimpleNamespace(stop=lambda:operations.append('stop'),close=lambda:operations.append('close'))
        app.rover_status = SimpleNamespace(set=lambda status:operations.append(status))
        app.disconnect_rover()
        self.assertEqual(operations,['stop','close','Disconnected'])
        self.assertIsNone(app.rover)
        self.assertIsNone(app.held)


if __name__ == '__main__':
    unittest.main()
