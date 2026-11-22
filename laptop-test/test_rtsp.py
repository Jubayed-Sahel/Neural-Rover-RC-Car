from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import threading
import time
import unittest
from urllib.parse import urlsplit, unquote
from rtsp_source import RTSPCamera, capture_loop, load_settings, put_latest, stream_url, validate_settings


def settings(**overrides):
    return {"host":"127.0.0.1","username":"test_user","password":"not-a-real-camera-secret",
            "retry_seconds":0.1,"max_attempts":2,"stale_seconds":1, **overrides}


class TransportTest(unittest.TestCase):
    def test_url_encodes_special_credentials(self):
        value = stream_url(settings(username="a@b",password="p:/?# @"))
        parsed = urlsplit(value)
        self.assertEqual(unquote(parsed.username),"a@b")
        self.assertEqual(unquote(parsed.password),"p:/?# @")
        self.assertEqual(parsed.hostname,"127.0.0.1")

    def test_reject_url_instead_of_host(self):
        for host in ("rtsp://user:secret@host", "a/b", "host:554"):
            with self.assertRaises(ValueError):
                validate_settings(settings(host=host))

    def test_ipv6_url(self):
        self.assertIn("@[::1]:554/stream1",stream_url(settings(host="::1")))

    def test_missing_file_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError,"05_CONFIGURE_TAPO"):
            load_settings(Path(__file__).parent / "file-that-does-not-exist.local.json")

    def test_latest_queue_drops_old_frames(self):
        queue = Queue(maxsize=1)
        put_latest(queue,"old")
        put_latest(queue,"new")
        self.assertEqual(queue.qsize(),1)
        self.assertEqual(queue.get_nowait(),"new")

    def test_failures_have_bounded_retries_and_release(self):
        releases=[]
        class Closed:
            def isOpened(self): return False
            def release(self): releases.append(True)
        state,gen,attempts = [SimpleNamespace(value=0) for _ in range(3)]
        capture_loop(Closed,settings(),Queue(1),state,gen,attempts,threading.Event())
        self.assertEqual(state.value,3)
        self.assertEqual(attempts.value,2)
        self.assertEqual(len(releases),2)

    def test_reconnect_updates_session_and_publishes_new_frame(self):
        stop=threading.Event()
        opened=[]
        class Capture:
            def __init__(self): self.reads=0
            def isOpened(self): return True
            def read(self):
                self.reads+=1
                if self.reads == 1: return True, len(opened)
                if len(opened)==2: stop.set()
                return False,None
            def release(self): pass
        def open_capture():
            opened.append(True)
            return Capture()
        state,gen,attempts = [SimpleNamespace(value=0) for _ in range(3)]
        frames=Queue(1)
        capture_loop(open_capture,settings(),frames,state,gen,attempts,stop)
        self.assertEqual(gen.value,2)
        self.assertEqual(frames.get_nowait()[1],2)
        self.assertEqual(state.value,4)

    def test_stale_and_previous_session_frames_rejected(self):
        camera=RTSPCamera.__new__(RTSPCamera)
        camera.settings=settings()
        camera.frames=Queue(1)
        camera.state=SimpleNamespace(value=1)
        camera.session=SimpleNamespace(value=2)
        camera.latest=(1,"old",time.perf_counter(),1)
        self.assertIsNone(camera.get())
        camera.latest=(2,"stale",time.perf_counter()-3,2)
        self.assertIsNone(camera.get())
        camera.latest=(3,"fresh",time.perf_counter(),2)
        self.assertEqual(camera.get()[1],"fresh")
        camera.state.value=2
        self.assertIsNone(camera.get())

    def test_real_worker_can_fail_and_exit_without_camera(self):
        camera=RTSPCamera(settings(port=1,timeout_ms=500,max_attempts=1))
        try:
            deadline=time.monotonic()+12
            while camera.failure is None and time.monotonic()<deadline:
                time.sleep(0.05)
            self.assertIsNotNone(camera.failure)
            self.assertNotIn("not-a-real-camera-secret",camera.failure)
            self.assertIsNone(camera.get())
        finally:
            camera.close()
        self.assertFalse(camera.process.is_alive())


if __name__ == "__main__":
    unittest.main()
