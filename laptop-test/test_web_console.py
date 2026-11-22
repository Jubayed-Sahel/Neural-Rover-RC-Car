"""Browser API tests isolated from real camera, rover, gallery and Telegram."""
import base64
from http.cookiejar import CookieJar
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request
from unittest.mock import patch
import numpy as np
from photo_enrollment import PhotoReview, UploadedPhoto
from web_console import Console


class FakeRover:
    status='Connected'
    def __init__(self,address): self.commands=[]
    def hold(self,direction): self.commands.append(direction);return True
    def stop(self): self.commands.append('S')
    def close(self): self.stop();self.status='Disconnected'


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory();self.root=Path(self.folder.name)
        self.sent=[]
        self.console=Console(root=self.root,rover_factory=FakeRover,
            bot_call=self.bot,bot_send=lambda *args:self.sent.append(args))
        self.port=self.console.start('127.0.0.1',0,auto_camera=False)
        self.url=f'http://127.0.0.1:{self.port}'
        self.client=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
        self.call('/')

    def tearDown(self):
        self.console.close();self.folder.cleanup()

    def bot(self,token,method,payload):
        if method=='getMe': return {'username':'test_rover_bot'}
        return [{'message':{'text':self.console.pending_pair['code'],'chat':{'type':'private','id':123}}}]

    def call(self,path,body=None,headers=None):
        extra={'Origin':self.url,'Content-Type':'application/json'} if body is not None else {}
        extra.update(headers or {})
        req=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=extra)
        with self.client.open(req,timeout=4) as response:
            data=response.read()
            return json.loads(data) if response.headers.get_content_type()=='application/json' else data

    def action(self,name,body=None): return self.call('/api/console/'+name,body or {})
    def wait(self):
        for _ in range(100):
            task=self.console.snapshot()['task']
            if task['status']!='running': return task
            time.sleep(.01)
        self.fail('Job did not finish')

    def test_assets_admin_access_and_no_private_values(self):
        self.assertIn(b'Mission control',self.call('/'))
        self.assertIn(b'function render',self.call('/console.js'))
        self.assertIn(b'--teal',self.call('/console.css'))
        self.action('camera/save',{'host':'192.168.43.10','username':'demo','password':'PRIVATE-PASSWORD','stream':'stream1'})
        self.action('camera/save',{'host':'192.168.43.11','username':'demo','password':'','stream':'stream2'})
        self.assertEqual(json.loads(self.console.camera_path.read_text())['password'],'PRIVATE-PASSWORD')
        state=self.call('/api/console/state')
        self.assertNotIn('PRIVATE-PASSWORD',json.dumps(state))
        outsider=build_opener(ProxyHandler({}))
        with self.assertRaises(HTTPError) as error: outsider.open(self.url+'/api/console/state')
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError): self.call('/api/console/state',headers={'Host':'evil.example'})
        with self.assertRaises(HTTPError): self.call('/api/console/camera/stop',{},headers={'Origin':'http://evil.example'})

    def test_uploaded_review_profile_edit_and_remove(self):
        vector=np.zeros(512,dtype=np.float32);vector[0]=1
        review=PhotoReview(samples=[vector],accepted=['view.jpg'])
        def review_upload(photos,engine):
            self.assertIsInstance(photos[0],UploadedPhoto)
            self.assertEqual(photos[0].data,b'fixture')
            return review
        with patch('web_console.review_photos',side_effect=review_upload),patch.object(self.console,'_engine',return_value=object()):
            self.action('photos/review',{'photos':[{'name':'view.jpg','data':base64.b64encode(b'fixture').decode()}]})
            task=self.wait();self.assertEqual(task['status'],'done')
        self.action('people/save',{'name':'Test participant','role':'Team','notify':True,'review_id':task['result']['id']})
        people=self.console.profile_list();self.assertEqual(people[0]['templates'],1);self.assertTrue(people[0]['notify'])
        self.action('people/save',{'name':'Test participant','role':'Owner','notify':False})
        self.assertEqual(self.console.profile_list()[0]['role'],'Owner')
        self.assertFalse(list(self.root.glob('*.jpg')))
        with self.assertRaises(HTTPError): self.action('people/delete',{'name':'Test participant'})
        self.action('people/delete',{'name':'Test participant','confirmed':True})
        self.assertEqual(self.console.profile_list(),[])

    def test_telegram_pair_and_test_only_use_mock_sender(self):
        self.action('telegram/begin',{'token':'123:FAKE_TOKEN'})
        self.assertEqual(self.wait()['status'],'done')
        self.assertNotIn('FAKE_TOKEN',json.dumps(self.console.snapshot()))
        self.action('telegram/complete');self.assertEqual(self.wait()['status'],'done')
        self.assertTrue(self.console.snapshot()['telegram']['configured']);self.assertEqual(self.sent,[])
        self.action('telegram/test');self.assertEqual(self.wait()['status'],'done');self.assertEqual(len(self.sent),1)

    def test_video_stop_does_not_interrupt_admin_driving_and_phone_cannot_steal(self):
        self.action('rover/connect',{'address':'192.168.43.120'})
        state=self.console.state;admin=self.console.admin_token
        phone=state.pair(state.pin)
        epoch=state.snapshot(admin)['epoch']
        begun=self.call('/api/control',{'operation':'begin','direction':'F','sequence':1,'epoch':epoch})
        self.action('camera/stop')
        self.assertTrue(state.snapshot(admin)['control_active'])
        with self.assertRaises(Exception): state.control(phone,{'operation':'begin','direction':'B','sequence':1,'epoch':epoch})
        state.control(admin,{'operation':'hold','direction':'F','lease':begun['lease'],'epoch':epoch,'sequence':2})
        state.control(phone,{'operation':'stop','sequence':2})
        self.assertFalse(state.snapshot(admin)['control_active'])

    def test_failed_capture_initialization_resumes_requested_camera(self):
        self.console.camera_wanted=True
        with patch.object(self.console,'stop_camera'),patch.object(self.console,'start_camera') as restart:
            with self.assertRaises(ValueError): self.console.capture_review()
            restart.assert_called_once()


if __name__=='__main__': unittest.main()
