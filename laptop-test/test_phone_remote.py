import http.client
import json
import socketserver
from threading import Thread
import time
import unittest
from unittest.mock import patch

import numpy as np

from phone_remote import PhoneRemote, RemoteError, RemoteState, lan_address
from rover_control import RoverControl
from test_rover_app import ESP32Stub, wait_for


class Clock:
    now = 100.0
    def __call__(self): return self.now


class Rover:
    status = 'Connected'
    def __init__(self): self.commands=[]
    def hold(self, direction): self.commands.append(direction); return self.status=='Connected'
    def stop(self): self.commands.append('S')


class StateTest(unittest.TestCase):
    def setUp(self):
        self.clock=Clock()
        self.state=RemoteState(self.clock,self.clock)
        self.rover=Rover()
        self.state.attach_rover(self.rover)
        self.state.feed(b'jpeg','Ready','Fixture',self.clock())
        self.session=self.state.pair(self.state.pin)
        self.rover.commands.clear()

    def begin(self, sequence=1, epoch=None):
        return self.state.control(self.session,{'operation':'begin','direction':'F','sequence':sequence,
                                                'epoch':self.state.epoch if epoch is None else epoch})

    def test_pairing_replaces_prior_phone_and_stops_movement(self):
        self.begin()
        other=self.state.pair(self.state.pin)
        self.assertNotEqual(other,self.session)
        self.assertEqual(self.rover.commands[-1],'S')
        with self.assertRaises(RemoteError): self.state.snapshot(self.session)

    def test_lease_expiry_stops_and_rejects_delayed_hold_and_begin(self):
        epoch=self.state.epoch
        lease=self.begin()['lease']
        self.clock.now+=.41
        self.state.sweep()
        self.assertEqual(self.rover.commands,['F','S'])
        for message in ({'operation':'hold','sequence':2,'lease':lease}, {'operation':'begin','sequence':3}):
            with self.assertRaises(RemoteError):
                self.state.control(self.session,{**message,'direction':'F','epoch':epoch})
        self.assertEqual(self.rover.commands,['F','S'])
        self.begin(sequence=4)
        self.assertEqual(self.rover.commands[-1],'F')

    def test_stop_arriving_before_begin_prevents_late_movement(self):
        epoch=self.state.epoch
        self.state.control(self.session,{'operation':'stop','sequence':2})
        with self.assertRaises(RemoteError): self.begin(sequence=1,epoch=epoch)
        self.assertEqual(self.rover.commands,['S'])

    def test_desktop_stop_invalidates_queued_phone_start(self):
        epoch=self.state.epoch
        self.state.stop()
        with self.assertRaises(RemoteError): self.begin(epoch=epoch)
        self.assertEqual(self.rover.commands,['S'])

    def test_camera_stop_and_stale_video_do_not_interrupt_renewed_movement(self):
        epoch=self.state.epoch
        lease=self.begin()['lease']
        for sequence in range(2,27):
            self.clock.now+=.1
            self.state.control(self.session,{'operation':'hold','direction':'F','sequence':sequence,'epoch':epoch,'lease':lease})
        self.assertFalse(self.state.snapshot(self.session)['video_live'])
        self.assertTrue(self.state.snapshot(self.session)['can_drive'])
        self.state.feed(None,'Camera stopped','',0)
        self.state.control(self.session,{'operation':'hold','direction':'F','sequence':27,'epoch':epoch,'lease':lease})
        self.assertNotIn('S',self.rover.commands)
        self.assertIsNotNone(self.state.lease)

    def test_driving_can_start_without_any_camera_video(self):
        self.state.feed(None,'Camera unavailable','',0)
        self.begin()
        self.assertEqual(self.rover.commands,['F'])
        self.assertTrue(self.state.snapshot(self.session)['can_drive'])

    def test_disconnected_rover_never_accepts_a_direction(self):
        self.rover.status='Disconnected'
        with self.assertRaises(RemoteError): self.begin()
        self.assertNotIn('F',self.rover.commands)

    def test_bad_pairing_is_rate_limited_and_unicode_does_not_crash(self):
        for _ in range(5):
            with self.assertRaises(RemoteError) as caught: self.state.pair('বাংলা')
            self.assertEqual(caught.exception.status,403)
        with self.assertRaises(RemoteError) as caught: self.state.pair(self.state.pin)
        self.assertEqual(caught.exception.status,429)
        self.clock.now+=61
        self.assertTrue(self.state.pair(self.state.pin))

    def test_session_expiry_stops_movement(self):
        self.begin()
        self.clock.now+=3601
        self.state.sweep()
        self.assertEqual(self.rover.commands[-1],'S')
        with self.assertRaises(RemoteError): self.state.snapshot(self.session)

    def test_invalid_direction_and_input_types_are_rejected(self):
        for sequence,message in enumerate(({'direction':'X'}, {'epoch':True}, {'direction':'http://example.com'}),1):
            with self.assertRaises(RemoteError):
                self.state.control(self.session,{'operation':'begin','direction':'F','epoch':self.state.epoch,'sequence':sequence,**message})
        with self.assertRaises(RemoteError):
            self.state.control(self.session,{'operation':'begin','direction':'F','epoch':self.state.epoch,'sequence':True})
        self.assertNotIn('F',self.rover.commands)

    def test_laptop_address_can_be_found_without_camera_configuration(self):
        with patch('phone_remote.socket.gethostbyname_ex',return_value=('fixture',[],['127.0.0.1','169.254.0.1','192.168.1.20'])):
            self.assertEqual(lan_address(), '192.168.1.20')


class HTTPTest(unittest.TestCase):
    def setUp(self):
        self.remote=PhoneRemote(port=0)
        self.addCleanup(self.remote.close)
        self.host=f'127.0.0.1:{self.remote.port}'
        self.cookie=None

    def request(self, method, path, body=None, origin=True):
        connection=http.client.HTTPConnection('127.0.0.1',self.remote.port,timeout=3)
        headers={}
        if origin: headers['Origin']='http://'+self.host
        if self.cookie: headers['Cookie']=self.cookie
        if body is not None: headers['Content-Type']='application/json'
        connection.request(method,path,json.dumps(body) if body is not None else None,headers)
        response=connection.getresponse()
        status,cookie=response.status,response.getheader('Set-Cookie')
        value=response.read()
        connection.close()
        return status,value,cookie

    def pair(self):
        status,value,cookie=self.request('POST','/api/pair',{'code':self.remote.pin})
        self.assertEqual(status,200)
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=Strict',cookie)
        self.cookie=cookie.split(';')[0]

    def test_camera_and_status_require_pairing_and_page_contains_no_pin(self):
        for path in ('/api/status','/video'):
            status,body,_=self.request('GET',path)
            self.assertEqual(status,401)
            self.assertNotIn(b'Fixture',body)
        status,body,_=self.request('GET','/')
        self.assertEqual(status,200)
        self.assertNotIn(self.remote.pin.encode(),body)
        self.pair()
        status,body,_=self.request('GET','/api/status')
        self.assertEqual(status,200)
        self.assertFalse(json.loads(body)['can_drive'])

    def test_cross_origin_requests_cannot_pair_or_drive(self):
        status,_,_=self.request('POST','/api/pair',{'code':self.remote.pin},origin=False)
        self.assertEqual(status,403)
        self.assertIsNone(self.remote.state.session)
        self.pair()
        status,_,_=self.request('POST','/api/control',{'operation':'stop','sequence':1},origin=False)
        self.assertEqual(status,403)

    def test_video_serves_actual_jpeg_and_stale_status_hides_it(self):
        self.pair()
        self.remote.publish(np.zeros((40,60,3),np.uint8),'Fixture video','Fixture',time.perf_counter())
        connection=http.client.HTTPConnection('127.0.0.1',self.remote.port,timeout=3)
        connection.request('GET','/video',headers={'Cookie':self.cookie})
        response=connection.getresponse()
        self.assertEqual(response.status,200)
        self.assertIn('multipart',response.getheader('Content-Type'))
        first=response.read(100)
        self.assertIn(b'Content-Type: image/jpeg',first)
        response.close();connection.close()
        self.remote.publish(None,'Stopped','No current video',0)
        status,body,_=self.request('GET','/api/status')
        self.assertEqual(status,200)
        self.assertFalse(json.loads(body)['video_live'])

    def test_phone_commands_reach_real_localhost_websocket_and_stop(self):
        server=socketserver.TCPServer(('127.0.0.1',0),ESP32Stub)
        server.commands=[]
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        rover=RoverControl('127.0.0.1',port=server.server_address[1])
        try:
            self.assertTrue(wait_for(lambda:rover.status=='Connected'))
            self.remote.state.attach_rover(rover)
            self.pair()
            status,body,_=self.request('GET','/api/status')
            state=json.loads(body)
            self.assertTrue(state['can_drive'])
            self.assertFalse(state['video_live'])
            status,body,_=self.request('POST','/api/control',{'operation':'begin','direction':'F','epoch':state['epoch'],'sequence':1})
            self.assertEqual(status,200)
            self.assertTrue(wait_for(lambda:'F' in server.commands))
            status,_,_=self.request('POST','/api/control',{'operation':'stop','sequence':2})
            self.assertEqual(status,200)
            self.assertTrue(wait_for(lambda:server.commands[-1]=='S'))
        finally:
            self.remote.state.attach_rover(None)
            rover.close();server.shutdown();server.server_close()
        self.assertEqual(server.commands[-1],'S')


if __name__ == '__main__':
    unittest.main()
