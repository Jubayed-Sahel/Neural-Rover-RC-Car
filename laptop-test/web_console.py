"""One-launch local browser application for the complete Neural Rover workflow."""
import argparse
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.cookies import SimpleCookie
from ipaddress import ip_address
import json
from pathlib import Path
import secrets
from threading import Event, RLock, Thread
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler
import webbrowser

import cv2

from alert_people import load_watch_names, save_watch_names
from enroll_live import collect_samples
from face_recognition_demo import FaceEngine, identify, read_gallery, read_profiles, remove_person, save_person
from phone_remote import Handler, PhoneRemote, RemoteError, RemoteState, lan_address
from photo_enrollment import PhotoReview, UploadedPhoto, review_photos, validate_profile
from rover_app import Monitor
from rover_control import RoverControl
from rtsp_source import RTSPCamera, load_settings, save_settings
from telegram_alerts import call_bot, load_alert_settings, send_text

ROOT = Path(__file__).resolve().parent


class Console:
    def __init__(self, root=ROOT, monitor_factory=Monitor, engine_factory=FaceEngine,
                 camera_factory=RTSPCamera, rover_factory=RoverControl,
                 bot_call=call_bot, bot_send=send_text):
        self.root = Path(root)
        self.lock = RLock()
        self.camera_lock = RLock()
        self.monitor_factory,self.engine_factory = monitor_factory,engine_factory
        self.camera_factory,self.rover_factory = camera_factory,rover_factory
        self.bot_call,self.bot_send = bot_call,bot_send
        self.admin_token = secrets.token_urlsafe(32)
        self.state = RemoteState()
        self.state.admin_session = self.admin_token
        self.remote = self.monitor = self.rover = None
        self.engine = None
        self.mode,self.preview,self.alerts_enabled = 'Balanced',False,False
        self.camera_wanted = False
        self.camera_message = 'Camera stopped'
        self.rover_address = ''
        self.profile_fields = {}
        self.events = deque(maxlen=40)
        self.event_counter = 0
        self.last_match_events = {}
        self.task = None
        self.review = None
        self.pending_pair = None
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancel_job = Event()
        self.finished = Event()
        self.started = time.monotonic()
        self.add_event('system','Workspace ready','Camera, recognition and driving can be managed here.')

    @property
    def gallery_path(self): return self.root/'faces.local.json'
    @property
    def watch_path(self): return self.root/'alert_people.local.json'
    @property
    def telegram_path(self): return self.root/'telegram.local.json'
    @property
    def camera_path(self): return self.root/'camera.local.json'

    def add_event(self, kind, title, detail=''):
        with self.lock:
            self.event_counter += 1
            self.events.appendleft({'id':self.event_counter,'kind':kind,'title':title,'detail':detail,
                                    'time':datetime.now().strftime('%H:%M:%S')})

    def start(self, host='0.0.0.0', port=8765, auto_camera=True):
        self.remote = PhoneRemote(host,port,state=self.state,handler_class=ConsoleHandler,application=self)
        self.pump_thread = Thread(target=self.pump,daemon=True)
        self.pump_thread.start()
        if auto_camera and self.camera_path.exists():
            try: self.start_camera()
            except (ValueError,OSError): self.camera_message = 'Configure the Tapo connection in Devices.'
        return self.remote.port

    def start_camera(self, mode=None, preview=None):
        with self.camera_lock:
            self.stop_camera(remember=False)
            if mode is not None:
                if mode not in ('Balanced','Strict'): raise ValueError('Choose Balanced or Strict matching.')
                self.mode = mode
            if preview is not None: self.preview = bool(preview)
            settings = load_settings(self.camera_path)
            gallery = read_gallery(self.gallery_path)
            self.profile_fields = read_profiles(self.gallery_path)
            watching = load_watch_names(self.watch_path) & set(gallery)
            telegram = load_alert_settings(self.telegram_path) if self.alerts_enabled else None
            self.camera_wanted = True
            self.monitor = self.monitor_factory(settings,gallery,watching,telegram,self.preview,self.mode)
            self.camera_message = 'Connecting to Tapo…'
            self.add_event('camera','Camera starting','Preview' if self.preview else 'Recognition · '+self.mode)

    def stop_camera(self, remember=True):
        with self.camera_lock:
            if remember: self.camera_wanted = False
            monitor,self.monitor = self.monitor,None
            if monitor:
                monitor.stop.set()
                monitor.thread.join(timeout=4)
                if monitor.thread.is_alive():
                    self.monitor = monitor
                    raise ValueError('Camera is still stopping. Wait briefly and try again.')
            self.camera_message = 'Camera stopped'
            if self.remote:
                self.remote.publish(None,self.camera_message,'No current video',0)

    def restart_if_running(self):
        if self.camera_wanted:
            self.start_camera()

    def pump(self):
        previous_live = False
        while not self.finished.wait(.06):
            monitor = self.monitor
            if not monitor or not self.remote: continue
            with monitor.lock:
                frame,status,names,retrieved = monitor.latest
            if monitor.stop.is_set() or (frame is not None and time.perf_counter()-retrieved > 2):
                frame,names = None,()
            if not monitor.thread.is_alive(): frame,names = None,()
            self.camera_message = status
            labels = [name + (f" ({self.profile_fields[name]['role']})" if self.profile_fields.get(name,{}).get('role') else '') for name in names]
            self.remote.publish(frame,status,'Recognized: '+', '.join(labels) if labels else 'No live matches',retrieved)
            live = frame is not None
            if live and not previous_live: self.add_event('camera','Camera connected','Live Tapo video is available.')
            previous_live = live
            for name in names:
                if time.monotonic()-self.last_match_events.get(name,-100) >= 10:
                    self.last_match_events[name] = time.monotonic()
                    self.add_event('match','Face match',name)

    def profile_list(self):
        gallery = read_gallery(self.gallery_path)
        profiles = read_profiles(self.gallery_path)
        watch = load_watch_names(self.watch_path)
        return [{'name':name,'id':profiles.get(name,{}).get('id',''),'role':profiles.get(name,{}).get('role',''),
                 'templates':len(samples),'notify':name in watch} for name,samples in sorted(gallery.items())]

    def safe_camera(self):
        try:
            config = load_settings(self.camera_path)
            return {'configured':True,'host':config['host'],'username':config['username'],
                    'stream':config.get('stream','stream1'),'password_saved':True}
        except (ValueError,OSError):
            return {'configured':False,'host':'','username':'','stream':'stream1','password_saved':False}

    def snapshot(self):
        control = self.state.snapshot(self.admin_token)
        try: people,error = self.profile_list(),None
        except (ValueError,OSError) as problem: people,error = [],str(problem)
        camera = self.safe_camera()
        address = lan_address(camera['host'] if camera['configured'] else None)
        with self.lock:
            pair = None if self.pending_pair is None else {key:self.pending_pair[key] for key in ('username','code')}
            return {'application':'Neural Rover','control':control,'people':people,'profile_error':error,
                    'camera':{**camera,'running':bool(self.monitor and self.monitor.thread.is_alive()),
                              'status':self.camera_message,'preview':self.preview,'mode':self.mode,
                              'metrics':getattr(self.monitor,'metrics',{}) if self.monitor else {}},
                    'rover':{'address':self.rover_address,'connected':control['rover_connected'],
                             'status':self.rover.status if self.rover else 'Disconnected'},
                    'telegram':{'configured':bool(load_alert_settings(self.telegram_path)),
                                'enabled':self.alerts_enabled,'pairing':pair},
                    'phone':{'url':f'http://{address}:{self.remote.port}/' if address and self.remote else '',
                             'code':self.state.pin,'paired':bool(self.state.session and self.state.clock()<self.state.session_until)},
                    'task':dict(self.task) if self.task else None,
                    'review':self.review['public'] if self.review else None,
                    'events':list(self.events),'uptime_seconds':int(time.monotonic()-self.started)}

    def _engine(self):
        if self.engine is None: self.engine = self.engine_factory()
        return self.engine

    def submit(self, kind, action):
        with self.lock:
            if self.task and self.task['status']=='running':
                raise RemoteError(409,'Finish or cancel the current operation first.')
            self.cancel_job.clear()
            identifier = secrets.token_hex(8)
            self.task = {'id':identifier,'kind':kind,'status':'running','message':'Working…','result':None}
        def run():
            try:
                result = action()
                with self.lock:
                    self.task.update(status='done',message='Completed',result=result)
            except (ValueError,OSError,RuntimeError) as problem:
                with self.lock: self.task.update(status='error',message=str(problem),result=None)
            except Exception:
                with self.lock: self.task.update(status='error',message='Operation failed. Check the device settings and try again.',result=None)
        self.pool.submit(run)
        return {'task_id':identifier}

    def progress(self, text):
        with self.lock:
            if self.task: self.task['message'] = text

    def ensure_idle(self):
        if self.task and self.task['status']=='running':
            raise RemoteError(409,'Finish or cancel the current operation first.')

    @staticmethod
    def photos(body):
        items = body.get('photos')
        if not isinstance(items,list) or not 1 <= len(items) <= 10: raise ValueError('Choose 1–10 photos.')
        result = []
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not isinstance(item.get('data'),str):
                raise ValueError('Invalid photo upload.')
            data = item['data'].split(',',1)[-1]
            try: decoded = base64.b64decode(data,validate=True)
            except (ValueError,TypeError): raise ValueError('Invalid photo encoding.') from None
            name = Path(item['name']).name[:160]
            result.append(UploadedPhoto(name,decoded))
        return result

    def cache_review(self, review):
        identifier = secrets.token_hex(12)
        public = {'id':identifier,'count':len(review.samples),'accepted':review.accepted,
                  'rejected':review.rejected,'summary':review.summary()}
        with self.lock: self.review = {'samples':review.samples,'public':public}
        return public

    def capture_review(self):
        wanted = self.camera_wanted
        self.stop_camera(remember=False)
        camera = None
        console = self
        class Capture:
            @property
            def generation(self): return camera.generation
            @property
            def failure(self): return camera.failure
            def get(self):
                if console.cancel_job.is_set() or console.finished.is_set(): raise ValueError('Live enrollment cancelled. Nothing was saved.')
                item = camera.get()
                if item and console.remote:
                    seq,frame,retrieved = item
                    h,w = frame.shape[:2]
                    scale = min(780/w,440/h,1)
                    view = cv2.resize(frame,(round(w*scale),round(h*scale)))
                    console.remote.publish(cv2.cvtColor(view,cv2.COLOR_BGR2RGB),'Collecting clear enrollment views…','Enrollment preview',retrieved)
                return item
        try:
            camera = self.camera_factory(load_settings(self.camera_path))
            samples = collect_samples(Capture(),self._engine(),60,3,self.progress)
            return self.cache_review(PhotoReview(samples=samples,accepted=['Live view 1','Live view 2','Live view 3']))
        finally:
            if camera: camera.close()
            if self.remote: self.remote.publish(None,'Capture finished','No current video',0)
            if wanted and not self.finished.is_set(): self.start_camera()

    def action(self, name, body):
        if name == 'task/cancel': self.cancel_job.set(); return {'cancelled':True}
        self.ensure_idle()
        if name == 'camera/start':
            self.start_camera(body.get('mode',self.mode),body.get('preview',False)); return {'started':True}
        if name == 'camera/stop':
            self.stop_camera();self.add_event('camera','Camera stopped','Driving remains independent.');return {'stopped':True}
        if name == 'camera/save':
            old = {}
            try: old = load_settings(self.camera_path)
            except (ValueError,OSError): pass
            config = {**old,'host':body.get('host',''),'username':body.get('username',''),
                      'password':body.get('password') or old.get('password',''),'stream':body.get('stream','stream1')}
            save_settings(self.camera_path,config)
            self.add_event('camera','Camera settings saved')
            self.restart_if_running()
            return {'saved':True}
        if name == 'rover/connect':
            address = body.get('address','')
            if not isinstance(address,str): raise ValueError('Enter the main ESP32 IPv4 address.')
            self.state.attach_rover(None)
            if self.rover: self.rover.close();self.rover=None
            self.rover = self.rover_factory(address)
            self.rover_address = address.strip()
            self.state.attach_rover(self.rover)
            self.add_event('rover','Rover connection requested')
            return {'connecting':True}
        if name == 'rover/disconnect':
            self.state.attach_rover(None)
            if self.rover: self.rover.close();self.rover=None
            self.add_event('rover','Rover disconnected');return {'disconnected':True}
        if name == 'photos/review':
            photos = self.photos(body)
            self.review = None
            return self.submit('photo review',lambda:self.cache_review(review_photos(photos,self._engine())))
        if name == 'photos/test':
            photos = self.photos(body)
            if len(photos)!=1: raise ValueError('Choose one separate photo for testing.')
            def test():
                review = review_photos(photos,self._engine())
                if not review.samples: raise ValueError(review.summary())
                gallery = read_gallery(self.gallery_path)
                if not gallery: raise ValueError('Save a person before testing recognition.')
                thresholds = (.50,.10) if self.mode=='Strict' else (.40,.06)
                label,score = identify(review.samples[0],gallery,*thresholds)
                return {'label':label,'similarity':round(score,3),'note':'Similarity is not a probability; use a photo not used for enrollment.'}
            return self.submit('photo test',test)
        if name == 'people/capture':
            validate_profile(body.get('name',''))
            self.review = None
            return self.submit('live enrollment',self.capture_review)
        if name == 'people/save':
            fields = [body.get(key,'') for key in ('name','id','role')]
            if not all(isinstance(value,str) for value in fields): raise ValueError('Enter text profile details.')
            person,profile = validate_profile(*fields)
            gallery = read_gallery(self.gallery_path)
            person = next((saved for saved in gallery if saved.casefold()==person.casefold()),person)
            if body.get('review_id'):
                if not self.review or self.review['public']['id'] != body['review_id']: raise ValueError('Check the photos or collect live views before saving.')
                samples = self.review['samples']
                if not samples: raise ValueError('No usable views. Choose clearer photos.')
                append = body.get('mode','add')!='replace'
                if person in gallery and not append and body.get('confirm_replace') is not True:
                    raise ValueError('Confirm replacement before discarding existing templates.')
            elif person in gallery:
                samples,append = list(gallery[person]),False
            else: raise ValueError('Check photos or collect live views before saving a new person.')
            save_person(gallery,person,samples,profile,append=append,path=self.gallery_path)
            watch = load_watch_names(self.watch_path)
            (watch.add if body.get('notify') is True else watch.discard)(person)
            save_watch_names(watch,self.watch_path)
            self.review = None
            self.profile_fields = read_profiles(self.gallery_path)
            self.restart_if_running()
            self.add_event('people','Profile saved',person)
            return {'saved':True,'name':person}
        if name == 'people/delete':
            person = body.get('name')
            if person not in read_gallery(self.gallery_path): raise ValueError('Select an existing person.')
            if body.get('confirmed') is not True: raise ValueError('Confirm removal first.')
            remove_person(person,self.gallery_path)
            watch = load_watch_names(self.watch_path);watch.discard(person);save_watch_names(watch,self.watch_path)
            self.restart_if_running();self.add_event('people','Profile removed',person)
            return {'removed':True}
        if name == 'telegram/enable':
            enabled = body.get('enabled') is True
            if enabled and not load_alert_settings(self.telegram_path): raise ValueError('Pair a private Telegram chat first.')
            if enabled and not load_watch_names(self.watch_path): raise ValueError('Mark a saved person for alerts first.')
            self.alerts_enabled = enabled
            self.restart_if_running();self.add_event('telegram','Alerts enabled' if enabled else 'Alerts paused')
            return {'enabled':enabled}
        if name == 'telegram/begin':
            token = body.get('token')
            if not isinstance(token,str): raise ValueError('Enter a bot token.')
            token = token.strip()
            def begin():
                bot = self.bot_call(token,'getMe',{})
                self.pending_pair = {'token':token,'username':bot['username'],'code':'rover-'+secrets.token_hex(5)}
                return {'username':bot['username'],'code':self.pending_pair['code']}
            return self.submit('Telegram pairing',begin)
        if name == 'telegram/complete':
            if not self.pending_pair: raise ValueError('Validate the bot token first.')
            pending = dict(self.pending_pair)
            def complete():
                updates = self.bot_call(pending['token'],'getUpdates',{'allowed_updates':['message'],'timeout':0})
                for update in reversed(updates):
                    message = update.get('message',{});chat=message.get('chat',{})
                    if chat.get('type')=='private' and message.get('text')==pending['code']:
                        path = self.telegram_path.with_name('telegram.pending.local.json')
                        path.write_text(json.dumps({'token':pending['token'],'chat_id':chat['id']}),encoding='utf-8')
                        path.replace(self.telegram_path)
                        self.pending_pair=None;self.add_event('telegram','Private chat paired')
                        return {'paired':True}
                raise ValueError('Pairing code not found. Send it in the private bot chat, then check again.')
            return self.submit('Telegram pairing',complete)
        if name == 'telegram/test':
            settings = load_alert_settings(self.telegram_path)
            if not settings: raise ValueError('Pair your private chat first.')
            def test_alert():
                self.bot_send(settings,'Neural Rover: notification test from the dashboard.')
                self.add_event('telegram','Test notification sent')
                return {'sent':True}
            return self.submit('Telegram test',test_alert)
        if name == 'readiness':
            def check():
                from check_setup import check_models,inspect_gallery
                people = inspect_gallery(self.gallery_path)
                models = check_models(ROOT)
                return {'checks':[vars(models),vars(people),
                    {'level':'PASS' if self.safe_camera()['configured'] else 'ACTION','title':'Camera setup','detail':'Verify the saved camera address on the demo hotspot.'},
                    {'level':'PASS' if self.rover and self.rover.status=='Connected' else 'ACTION','title':'Rover','detail':'Verify directions and physical stops with wheels raised.'},
                    {'level':'ACTION','title':'Portable network','detail':'Rehearse this exact phone hotspot and demonstration laptop before university.'}]}
            return self.submit('readiness check',check)
        if name == 'session/shutdown':
            self.state.stop()
            Thread(target=self.close,daemon=True).start()
            return {'closed':True}
        raise RemoteError(404,'Unknown operation.')

    def close(self):
        if self.finished.is_set(): return
        self.finished.set();self.cancel_job.set();self.state.stop()
        try: self.stop_camera()
        except ValueError: pass
        if self.rover: self.rover.close()
        if self.remote: self.remote.close()
        self.pool.shutdown(wait=False,cancel_futures=True)


class ConsoleHandler(Handler):
    def local(self):
        try:
            host = urlsplit('http://'+self.headers.get('Host','')).hostname
            return ip_address(self.client_address[0]).is_loopback and host in ('localhost','127.0.0.1','::1')
        except (ValueError,TypeError): return False

    def admin(self):
        if not self.local(): return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie',''))
            token = cookie['rover_admin'].value if 'rover_admin' in cookie else ''
            return bool(token and token.isascii() and secrets.compare_digest(token,self.server.application.admin_token))
        except Exception: return False

    def session(self):
        return self.server.application.admin_token if self.admin() else super().session()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            self.reply(200,{'application':'neural-rover-web-console','version':1});return
        if path == '/' and self.local():
            data = (ROOT/'web_console.html').read_bytes()
            self.headers_for(200,'text/html; charset=utf-8',len(data),
                             f'rover_admin={self.server.application.admin_token}; HttpOnly; SameSite=Strict; Path=/')
            self.wfile.write(data);return
        if path in ('/console.css','/console.js'):
            if not self.admin(): self.reply(403,{'error':'Open the dashboard on the laptop.'});return
            data = (ROOT/('web_console.css' if path.endswith('css') else 'web_console.js')).read_bytes()
            self.headers_for(200,'text/css' if path.endswith('css') else 'application/javascript',len(data))
            self.wfile.write(data);return
        if path.startswith('/api/console/'):
            if not self.admin(): self.reply(403,{'error':'Management is available only in the laptop browser.'});return
            if path == '/api/console/state':
                try: self.reply(200,self.server.application.snapshot())
                except (ValueError,OSError): self.reply(500,{'error':'Could not load local settings. Keep the original files for recovery.'})
            else: self.reply(404,{'error':'Not found.'})
            return
        super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if not path.startswith('/api/console/'):
            super().do_POST();return
        try:
            if not self.admin(): raise RemoteError(403,'Management is available only in the laptop browser.')
            if self.headers.get('Origin') != 'http://'+self.headers.get('Host',''):
                raise RemoteError(403,'Open the dashboard directly on the laptop.')
            if self.headers.get_content_type() != 'application/json' or self.headers.get('Transfer-Encoding'):
                raise RemoteError(415,'JSON required.')
            try: length = int(self.headers.get('Content-Length','0'))
            except ValueError: raise RemoteError(400,'Invalid request length.') from None
            if not 1 <= length <= 16_000_000: raise RemoteError(413,'Upload is too large. Choose fewer or smaller photos.')
            try: body = json.loads(self.rfile.read(length))
            except (ValueError,UnicodeError): raise RemoteError(400,'Invalid request data.') from None
            if not isinstance(body,dict): raise RemoteError(400,'JSON object required.')
            value = self.server.application.action(path.removeprefix('/api/console/'),body)
            self.reply(200,value)
        except RemoteError as error:
            self.close_connection=True;self.reply(error.status,{'error':error.message})
        except (ValueError,OSError) as error:
            self.close_connection=True;self.reply(400,{'error':str(error)})
        except Exception:
            self.close_connection=True;self.reply(500,{'error':'Operation failed. Check the settings and retry.'})


def existing_console(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/health',timeout=1) as response:
            return json.load(response).get('application')=='neural-rover-web-console'
    except Exception: return False


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--open-browser',action='store_true')
    parser.add_argument('--no-auto-camera',action='store_true')
    args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}/'
    if existing_console(args.port):
        if args.open_browser: webbrowser.open(url)
        return
    console=Console()
    try:
        console.start(port=args.port,auto_camera=not args.no_auto_camera)
    except OSError:
        message='Port 8765 is in use. Close the old Neural Rover desktop/phone app, then start again.'
        if args.open_browser:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,message,'Neural Rover',0x10)
        raise SystemExit(message)
    if args.open_browser: webbrowser.open(url)
    try:
        while not console.finished.wait(1): pass
    except KeyboardInterrupt:
        console.close()


if __name__=='__main__':
    main()
