"""Optional text-only alerts sent to one paired Telegram private chat."""
from datetime import datetime
import json
from pathlib import Path
from queue import Empty, Full, Queue
import re
from threading import Event, Thread
from urllib.request import Request, urlopen

SETTINGS = Path(__file__).resolve().parent / 'telegram.local.json'


def call_bot(token, method, payload):
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Invalid Telegram bot token format.')
    request = Request(f'https://api.telegram.org/bot{token}/{method}',
                      data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=8) as response:
            body = json.load(response)
        if not body.get('ok'):
            raise ValueError('Telegram rejected the request.')
        return body['result']
    except (OSError, ValueError, KeyError) as error:
        status = getattr(error, 'code', None)
        suffix = f' (HTTP {status})' if status else ''
        raise RuntimeError(f'Telegram request failed{suffix}. Check the token, private chat and internet connection.') from None


def send_text(settings, text):
    return call_bot(settings['token'], 'sendMessage', {'chat_id': settings['chat_id'], 'text': text})


def load_alert_settings(path=None):
    path = Path(path) if path is not None else SETTINGS
    if not path.exists():
        return None
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', config['token']) or type(config['chat_id']) is not int or config['chat_id'] <= 0:
            raise ValueError
        return config
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print('Telegram settings are invalid. Re-run 10_CONFIGURE_TELEGRAM.bat; recognition still works locally.')
        return None


class MatchGate:
    def __init__(self, cooldown=60):
        self.cooldown = cooldown
        self.streaks = {}
        self.last_sent = {}
        self.previous = None

    def reset(self):
        self.streaks.clear()
        self.previous = None

    def observe(self, identities, now, enqueue):
        if self.previous is not None and now - self.previous > 1.5:
            self.reset()
        self.previous = now
        self.streaks = {name: self.streaks.get(name, 0) + 1 for name in set(identities)}
        for name, frames in self.streaks.items():
            if frames >= 3 and now - self.last_sent.get(name, float('-inf')) >= self.cooldown:
                if enqueue(name):
                    self.last_sent[name] = now


class TelegramAlerts:
    def __init__(self, settings, send=send_text):
        self.settings = settings
        self.send = send
        self.queue = Queue(maxsize=8)
        self.stopped = Event()
        self.status = 'Ready; waiting for matches'
        self.thread = Thread(target=self.run, daemon=True)
        self.thread.start()

    def enqueue(self, name):
        if self.stopped.is_set():
            return False
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self.queue.put_nowait(f'Neural Rover: possible match for {name} at {stamp} (PC local time).')
            return True
        except Full:
            return False

    def close(self):
        self.stopped.set()

    def run(self):
        while not self.stopped.is_set():
            try:
                text = self.queue.get(timeout=0.2)
            except Empty:
                continue
            try:
                if not self.stopped.is_set():
                    self.send(self.settings, text)
                    self.status = 'Sent at ' + datetime.now().strftime('%H:%M:%S')
                    print('Telegram alert sent.', flush=True)
            except (RuntimeError, OSError):
                self.status = 'Delivery failed; check internet and bot setup'
                print('Telegram alert failed. Check the bot setup and internet connection.', flush=True)
            finally:
                self.queue.task_done()
