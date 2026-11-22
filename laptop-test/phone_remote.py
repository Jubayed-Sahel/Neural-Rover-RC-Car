"""Paired LAN phone remote sharing the desktop's video and rover connection.

No camera credentials, face templates or arbitrary network destinations are
accepted by this server. Only one paired phone can drive at a time. A short
movement lease, ordered inputs and stop epochs reject delayed commands.
"""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
import json
from pathlib import Path
import secrets
import socket
from threading import Event, RLock, Thread
import time
from urllib.parse import urlsplit

import cv2

ROOT = Path(__file__).resolve().parent


class RemoteError(Exception):
    def __init__(self, status, message):
        self.status,self.message = status,message
        super().__init__(message)


class RemoteState:
    def __init__(self, clock=time.monotonic, frame_clock=time.perf_counter):
        self.lock = RLock()
        self.clock,self.frame_clock = clock,frame_clock
        self.pin = f'{secrets.randbelow(100_000_000):08d}'
        self.session = None
        self.session_until = 0
        self.admin_session = None
        self.admin_sequence = 0
        self.bad_pairs = []
        self.rover = None
        self.jpeg = None
        self.frame_time = None
        self.frame_version = 0
        self.camera_status = 'Start camera on the laptop.'
        self.matches = 'No live matches'
        self.epoch,self.last_sequence = 0,0
        self.lease = None
        self.lease_owner = None
        self.deadline = 0
        self.closed = False

    def _stop(self):
        self.lease = None
        self.lease_owner = None
        self.deadline = 0
        self.epoch += 1
        if self.rover:
            self.rover.stop()

    def stop(self):
        with self.lock:
            self._stop()

    def attach_rover(self, rover):
        with self.lock:
            self._stop()
            self.rover = rover

    def _fresh(self):
        return self.jpeg is not None and self.frame_time is not None and 0 <= self.frame_clock()-self.frame_time <= 2

    def feed(self, jpeg, status, matches, retrieved):
        with self.lock:
            self.jpeg,self.frame_time = jpeg,retrieved if jpeg is not None else None
            self.camera_status,self.matches = status,matches
            self.frame_version += 1

    def _sweep(self):
        if self.lease and (self.clock() > self.deadline
                           or self.rover is None or self.rover.status != 'Connected'
                           or (self.lease_owner == self.session and self.clock() >= self.session_until)):
            self._stop()

    def sweep(self):
        with self.lock:
            self._sweep()

    def _auth(self, session):
        if not self.closed and session and self.admin_session and isinstance(session,str) and session.isascii() and secrets.compare_digest(session,self.admin_session):
            return
        if (self.closed or not session or not self.session
            or not isinstance(session,str) or not session.isascii()
            or not secrets.compare_digest(session,self.session) or self.clock() >= self.session_until):
            raise RemoteError(401,'Pair this phone using the code on the laptop.')

    def pair(self, code):
        with self.lock:
            if self.closed:
                raise RemoteError(503,'Phone remote stopped.')
            now = self.clock()
            self.bad_pairs = [stamp for stamp in self.bad_pairs if now-stamp < 60]
            if len(self.bad_pairs) >= 5:
                raise RemoteError(429,'Too many attempts. Wait one minute and check the laptop code.')
            if not isinstance(code,str) or not code.isascii() or not secrets.compare_digest(code,self.pin):
                self.bad_pairs.append(now)
                raise RemoteError(403,'Incorrect pairing code.')
            self._stop()
            self.session = secrets.token_urlsafe(32)
            self.session_until = now+3600
            self.last_sequence = 0
            self.bad_pairs.clear()
            return self.session

    def snapshot(self, session):
        with self.lock:
            self._auth(session)
            self._sweep()
            fresh = self._fresh()
            connected = bool(self.rover and self.rover.status == 'Connected')
            return {'video_live':fresh,'camera_status':self.camera_status,
                    'matches':self.matches if fresh else 'No current video',
                    'rover_connected':connected,'can_drive':connected,
                    'control_active':bool(self.lease),'control_owner':('laptop' if self.lease_owner == self.admin_session else 'phone') if self.lease else None,
                    'epoch':self.epoch,'sequence':self.admin_sequence if session == self.admin_session else self.last_sequence}

    def video(self, session):
        with self.lock:
            self._auth(session)
            self._sweep()
            return (self.frame_version,self.jpeg) if self._fresh() else (self.frame_version,None)

    def control(self, session, message):
        with self.lock:
            self._auth(session)
            self._sweep()
            sequence = message.get('sequence')
            is_admin = session == self.admin_session
            previous = self.admin_sequence if is_admin else self.last_sequence
            if type(sequence) is not int or not 1 <= sequence <= 2**53 or sequence <= previous:
                raise RemoteError(409,'Old input ignored. Release and press again.')
            if is_admin:
                self.admin_sequence = sequence
            else:
                self.last_sequence = sequence
            operation = message.get('operation')
            if operation == 'stop':
                self._stop()
                return {'epoch':self.epoch}
            if operation not in ('begin','hold') or message.get('direction') not in ('F','B','L','R'):
                raise RemoteError(400,'Invalid movement command.')
            if type(message.get('epoch')) is not int or message['epoch'] != self.epoch:
                raise RemoteError(409,'Controls were stopped. Release and press again.')
            if not self.rover or self.rover.status != 'Connected':
                self._stop()
                raise RemoteError(409,'Connect the rover from the laptop before driving.')
            if operation == 'begin':
                if self.lease and self.lease_owner != session:
                    raise RemoteError(409,'Another controller is driving. Press STOP before taking control.')
                if self.lease:
                    self.rover.stop()
                self.lease = secrets.token_urlsafe(24)
                self.lease_owner = session
            elif not self.lease or self.lease_owner != session or not isinstance(message.get('lease'),str) or not message['lease'].isascii() or not secrets.compare_digest(message['lease'],self.lease):
                raise RemoteError(409,'Movement expired. Release and press again.')
            if not self.rover.hold(message['direction']):
                self._stop()
                raise RemoteError(409,'Rover connection unavailable.')
            self.deadline = self.clock()+.4
            return {'lease':self.lease,'epoch':self.epoch}

    def close(self):
        with self.lock:
            self._stop()
            self.closed = True
            self.session = None
            self.jpeg = None


class RemoteServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self,*args):
        pass  # Do not log pairing codes, cookies, camera images or profile labels.

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie',''))
            return cookie['rover_session'].value if 'rover_session' in cookie else None
        except Exception:
            return None

    def headers_for(self, status, kind, length=None, cookie=None):
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        if length is not None:
            self.send_header('Content-Length',str(length))
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()

    def reply(self, status, value, cookie=None):
        data = json.dumps(value).encode()
        self.headers_for(status,'application/json',len(data),cookie)
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        video_started = False
        try:
            if path == '/':
                data = (ROOT/'phone_remote.html').read_bytes()
                self.headers_for(200,'text/html; charset=utf-8',len(data))
                self.wfile.write(data)
            elif path == '/api/status':
                self.reply(200,self.server.state.snapshot(self.session()))
            elif path == '/video':
                session = self.session()
                self.server.state.snapshot(session)
                self.headers_for(200,'multipart/x-mixed-replace; boundary=roverframe')
                video_started = True
                previous = -1
                while not self.server.finished.wait(.04):
                    version,jpeg = self.server.state.video(session)
                    if jpeg is None or version == previous:
                        continue
                    previous = version
                    self.wfile.write(b'--roverframe\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(jpeg)).encode()+b'\r\n\r\n'+jpeg+b'\r\n')
                    self.wfile.flush()
                self.close_connection = True
            else:
                self.reply(404,{'error':'Not found.'})
        except RemoteError as error:
            if path == '/video':
                # If streaming already started, terminate rather than emitting
                # a second set of HTTP headers into the multipart body.
                if not video_started:
                    self.reply(error.status,{'error':error.message})
                else:
                    self.close_connection = True
            else:
                self.reply(error.status,{'error':error.message})
        except (BrokenPipeError,ConnectionError,TimeoutError,OSError):
            self.close_connection = True

    def do_POST(self):
        try:
            # Mutations are same-origin JSON only. Neither CORS nor arbitrary
            # outgoing addresses are supported by the phone server.
            if self.headers.get('Origin') != 'http://'+self.headers.get('Host',''):
                raise RemoteError(403,'Open this page directly using the address shown on the laptop.')
            if self.headers.get_content_type() != 'application/json':
                raise RemoteError(415,'JSON required.')
            if self.headers.get('Transfer-Encoding'):
                raise RemoteError(400,'Unsupported request encoding.')
            try:
                length = int(self.headers.get('Content-Length','0'))
            except ValueError:
                raise RemoteError(400,'Invalid request length.') from None
            if not 1 <= length <= 2048:
                raise RemoteError(413,'Request is too large or empty.')
            try:
                message = json.loads(self.rfile.read(length))
            except (ValueError,UnicodeError):
                raise RemoteError(400,'Invalid JSON.') from None
            if not isinstance(message,dict):
                raise RemoteError(400,'JSON object required.')
            path = urlsplit(self.path).path
            if path == '/api/pair':
                session = self.server.state.pair(message.get('code'))
                self.reply(200,{'paired':True},f'rover_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')
            elif path == '/api/control':
                self.reply(200,self.server.state.control(self.session(),message))
            else:
                raise RemoteError(404,'Not found.')
        except RemoteError as error:
            self.close_connection = True
            self.reply(error.status,{'error':error.message})
        except (BrokenPipeError,ConnectionError,TimeoutError,OSError):
            self.server.state.stop()
            self.close_connection = True


class PhoneRemote:
    def __init__(self, host='127.0.0.1', port=8765, state=None, handler_class=Handler, application=None):
        self.state = state if state is not None else RemoteState()
        self.server = RemoteServer((host,port),handler_class)
        self.server.state = self.state
        self.server.application = application
        self.server.finished = Event()
        self.port = self.server.server_address[1]
        self.last_frame = None
        self.thread = Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True)
        self.watchdog = Thread(target=self.watch,daemon=True)
        self.thread.start()
        self.watchdog.start()

    @property
    def pin(self):
        return self.state.pin

    def publish(self, frame, status, matches, retrieved):
        if frame is self.last_frame:
            with self.state.lock:
                self.state.camera_status,self.state.matches = status,matches
            return
        self.last_frame = frame
        jpeg = None
        if frame is not None:
            try:
                ok,encoded = cv2.imencode('.jpg',cv2.cvtColor(frame,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,80])
                if ok:
                    jpeg = encoded.tobytes()
            except (cv2.error,ValueError,TypeError):
                status = 'Video unavailable. Driving is independent of the camera.'
        self.state.feed(jpeg,status,matches,retrieved)

    def watch(self):
        while not self.server.finished.wait(.05):
            self.state.sweep()

    def close(self):
        self.state.close()
        self.server.finished.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.watchdog.join(timeout=1)


def lan_address(camera_host=None):
    """Choose the interface used to reach the camera; no UDP packet is sent."""
    try:
        if camera_host:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
                probe.connect((camera_host,554))
                address = probe.getsockname()[0]
            if address != '0.0.0.0':
                return address
    except OSError:
        pass
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            ip = IPv4Address(address)
            if ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_unspecified:
                return address
    except (OSError,ValueError):
        pass
    return None
