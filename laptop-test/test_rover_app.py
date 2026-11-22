import base64
import hashlib
import json
from pathlib import Path
import socketserver
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import face_recognition_demo as faces
from photo_enrollment import extract_samples, validate_profile
from rover_control import RoverControl
from telegram_alerts import MatchGate, TelegramAlerts


def wait_for(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class ESP32Stub(socketserver.StreamRequestHandler):
    def handle(self):
        request = self.rfile.readline()
        headers = {}
        while (line := self.rfile.readline()).strip():
            key, value = line.decode().split(':', 1)
            headers[key.lower()] = value.strip()
        if not request.startswith(b'GET /ws '):
            return
        answer = base64.b64encode(hashlib.sha1((headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        self.wfile.write(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+answer+b'\r\n\r\n')
        while len(header := self.rfile.read(2)) == 2:
            opcode, size = header[0] & 15, header[1] & 127
            mask = self.rfile.read(4)
            data = bytes(value ^ mask[index%4] for index,value in enumerate(self.rfile.read(size)))
            if opcode == 1:
                self.server.commands.append(data.decode())
            elif opcode == 8:
                self.wfile.write(bytes((0x88,len(data)))+data)
                return


class ProjectTest(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).parent / 'results'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_photo_enrollment_rejects_multiple_faces_and_bad_name(self):
        photo = self.folder/'sample.png'
        Image.new('RGB',(96,96)).save(photo)
        class Stub:
            def detect_upright(self, _): return [1,2]
        with self.assertRaisesRegex(ValueError,'exactly one'):
            extract_samples([photo], Stub())
        with self.assertRaises(ValueError):
            validate_profile('Unknown')

    def test_profiles_migrate_with_private_backup_and_remove(self):
        path = self.folder/'faces.local.json'
        path.write_text(json.dumps({'version':1,'people':{'Legacy':[]}}))
        a,b = np.eye(faces.FEATURE_SIZE,dtype=np.float32)[:2]
        with patch.object(faces,'GALLERY',path):
            faces.save_person({},'Person',[a],{'id':'1','role':'Demo'})
            self.assertEqual(faces.read_profiles()['Person']['role'],'Demo')
            self.assertEqual(faces.identify(a,faces.read_gallery())[0],'Person')
            self.assertEqual(faces.identify(b,faces.read_gallery())[0],'Unknown')
            self.assertTrue((self.folder/'faces.legacy.local.json').is_file())
            faces.remove_person('Person')
            self.assertEqual(faces.read_gallery(),{})
            self.assertEqual(faces.read_profiles(),{})

    def test_alert_requires_three_matches_and_respects_cooldown(self):
        sent = []
        alerts = TelegramAlerts({},send=lambda _settings,text:sent.append(text))
        try:
            gate = MatchGate()
            for t in (0,.2,.4):
                gate.observe(['Fixture','Fixture'],t,alerts.enqueue)
            self.assertTrue(wait_for(lambda:len(sent)==1))
            for t in (.6,.8,1,30,30.2,30.4):
                gate.observe(['Fixture'],t,alerts.enqueue)
            self.assertEqual(len(sent),1)
            gate.reset()
            for t in (61,61.2,61.4):
                gate.observe(['Fixture'],t,alerts.enqueue)
            self.assertTrue(wait_for(lambda:len(sent)==2))
        finally:
            alerts.close()

    def test_real_websocket_manual_lease_stop_and_disconnect(self):
        server = socketserver.TCPServer(('127.0.0.1',0),ESP32Stub)
        server.commands = []
        thread = Thread(target=server.serve_forever,daemon=True)
        thread.start()
        rover = RoverControl('127.0.0.1',port=server.server_address[1])
        try:
            self.assertTrue(wait_for(lambda:rover.status=='Connected'))
            self.assertEqual(server.commands,['S'])
            self.assertFalse(rover.hold('X'))
            self.assertTrue(rover.hold('F'))
            self.assertTrue(wait_for(lambda:'F' in server.commands))
            self.assertTrue(wait_for(lambda:server.commands[-1]=='S'))
            self.assertTrue(rover.hold('L'))
            self.assertTrue(wait_for(lambda:'L' in server.commands))
            rover.stop()
            self.assertTrue(wait_for(lambda:server.commands[-1]=='S'))
        finally:
            rover.close()
            server.shutdown()
            server.server_close()
        self.assertEqual(server.commands[-1],'S')
        self.assertFalse(rover.worker.is_alive())
