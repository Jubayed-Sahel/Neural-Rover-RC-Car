"""Manual ESP32 commands. Movement needs a short, continuously renewed UI lease."""
from ipaddress import IPv4Address, IPv4Network
from select import select
from threading import Event, Lock, Thread
import time
from websocket import ABNF, create_connection, WebSocketException

DIRECTIONS = frozenset('FBLR')
LOCAL_NETWORKS = tuple(map(IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8')))
PING_INTERVAL = 1.0
PONG_TIMEOUT = 2.0


class RoverControl:
    def __init__(self, host, connect=create_connection, port=80):
        address = IPv4Address(host.strip())
        if not any(address in network for network in LOCAL_NETWORKS):
            raise ValueError('Enter the rover’s local IPv4 address.')
        self.url = f'ws://{address}:{port}/ws'
        self.connect = connect
        self.lock = Lock()
        self.closed = Event()
        self.wake = Event()
        self.status = 'Connecting'
        self.command = 'S'
        self.deadline = 0.0
        self.worker = Thread(target=self._run, daemon=True)
        self.worker.start()

    def hold(self, direction):
        if direction not in DIRECTIONS:
            return False
        with self.lock:
            if self.status != 'Connected' or self.closed.is_set():
                return False
            changed = self.command != direction
            self.command = direction
            self.deadline = time.monotonic() + 0.4
            if changed:
                self.wake.set()
            return True

    def stop(self):
        with self.lock:
            self.command = 'S'
            self.deadline = 0
            self.wake.set()

    def close(self):
        self.stop()
        self.closed.set()
        self.wake.set()
        self.worker.join(timeout=2)

    def _run(self):
        connection = None
        try:
            connection = self.connect(self.url, timeout=1, http_no_proxy=['*'])
            connection.send('S')
            last = 'S'
            last_send = time.monotonic()
            next_ping = last_send
            ping_payload = None
            pong_due = 0.0
            while not self.closed.is_set():
                self.wake.wait(0.05)
                self.wake.clear()
                now = time.monotonic()
                if select([connection.sock], [], [], 0)[0]:
                    opcode, frame = connection.recv_data_frame(control_frame=True)
                    if opcode == ABNF.OPCODE_CLOSE:
                        raise WebSocketException('ESP32 closed the connection')
                    if opcode == ABNF.OPCODE_PONG and frame.data == ping_payload:
                        ping_payload = None
                        with self.lock:
                            self.status = 'Connected'
                if ping_payload is not None and now >= pong_due:
                    raise WebSocketException('ESP32 heartbeat timed out')
                if ping_payload is None and now >= next_ping:
                    ping_payload = str(time.monotonic_ns()).encode('ascii')
                    connection.ping(ping_payload)
                    next_ping = now + PING_INTERVAL
                    pong_due = now + PONG_TIMEOUT
                with self.lock:
                    if now >= self.deadline:
                        self.command = 'S'
                    command = self.command
                if command != last or now - last_send >= (0.18 if command != 'S' else 0.7):
                    connection.send(command)
                    last, last_send = command, now
        except (OSError, WebSocketException):
            with self.lock:
                self.status = ('Connection lost — click Connect to retry'
                               if self.status == 'Connected'
                               else 'Connection failed — click Connect to retry')
                self.command = 'S'
                self.deadline = 0
        finally:
            if connection is not None:
                try:
                    connection.send('S')
                    connection.close(timeout=0.2)
                except (OSError, WebSocketException):
                    connection.shutdown()
            if self.closed.is_set():
                self.status = 'Disconnected'
