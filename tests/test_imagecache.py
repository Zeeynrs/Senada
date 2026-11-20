"""Covers are kept on disk: after a restart they come from the cache, not the internet."""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, QUrl

from senada import imagecache
from senada.imagecache import ImageCache, is_image_host, looks_like_image, trim

APP = QCoreApplication.instance() or QCoreApplication([])

def _png() -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("#00ff00"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


PNG = _png()  # a small valid PNG


class Helpers(unittest.TestCase):
    def test_cover_hosts(self):
        for host in ("lh3.googleusercontent.com", "yt3.ggpht.com", "i.ytimg.com", "i.scdn.co"):
            self.assertTrue(is_image_host(host), host)
        for host in ("", "example.com", "notytimg.com", "googleusercontent.com.evil.test"):
            self.assertFalse(is_image_host(host), host)

    def test_only_images_are_kept(self):
        self.assertTrue(looks_like_image(PNG))
        self.assertTrue(looks_like_image(b"\xff\xd8\xff\xe0rest"))
        self.assertTrue(looks_like_image(b"RIFF\0\0\0\0WEBPVP8 "))
        self.assertFalse(looks_like_image(b"RIFF\0\0\0\0WAVEfmt "))
        self.assertFalse(looks_like_image(b"<html>rate limited</html>"))

    def test_trim_removes_the_least_recently_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = time.time()
            for i in range(5):
                p = Path(tmp) / f"c{i}"
                p.write_bytes(b"x" * 100)
                os.utime(p, (now - 100 + i, now - 100 + i))  # c0 is the oldest
            trim(Path(tmp), 350)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["c2", "c3", "c4"])


class DiskCache(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.body = PNG
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                test.requests.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(test.body)))
                self.end_headers()
                self.wfile.write(test.body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        hosts = patch.object(imagecache, "IMAGE_HOSTS", imagecache.IMAGE_HOSTS + ("127.0.0.1",))
        hosts.start()
        self.addCleanup(hosts.stop)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/cover.png"
        self.caches = []
        self.addCleanup(self.release_caches)

    def cache(self):
        cache = ImageCache(self.folder)
        self.caches.append(cache)
        return cache

    def release_caches(self):
        # Qt's network objects finish deleting themselves first, then the caches go
        for cache in self.caches:
            cache.close()
        for _ in range(3):
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            QCoreApplication.processEvents()
        self.caches.clear()

    def wait_stored(self, cache):
        loop = QEventLoop()
        got = []
        cache.stored.connect(lambda url: (got.append(url), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        return got

    def test_downloaded_once_then_loaded_from_disk_after_a_restart(self):
        first = self.cache()
        self.assertEqual(first.cached(self.url), "")  # downloading
        self.assertEqual(self.wait_stored(first), [self.url])
        local = first.cached(self.url)
        self.assertTrue(local.startswith("file://"), local)
        self.assertEqual(Path(QUrl(local).toLocalFile()).read_bytes(), PNG)

        restarted = self.cache()
        self.assertEqual(restarted.cached(self.url), local)
        self.assertEqual(len(self.requests), 1)

    def test_one_download_for_many_covers_of_the_same_image(self):
        cache = self.cache()
        for _ in range(5):
            cache.cached(self.url)
        self.wait_stored(cache)
        self.assertEqual(len(self.requests), 1)

    def test_a_non_image_answer_falls_back_to_the_address(self):
        self.body = b"<html>try again later</html>"
        cache = self.cache()
        self.assertEqual(cache.cached(self.url), "")
        self.wait_stored(cache)
        self.assertEqual(cache.cached(self.url), self.url)  # QML loads it directly, as before
        self.assertEqual([p for p in self.folder.iterdir()], [])

    def test_a_damaged_copy_is_forgotten(self):
        cache = self.cache()
        cache.cached(self.url)
        self.wait_stored(cache)
        cache.forget(self.url)
        self.assertEqual(cache.cached(self.url), self.url)
        self.assertEqual(list(self.folder.iterdir()), [])

    def wait_for(self, signal):
        loop = QEventLoop()
        got = []
        signal.connect(lambda *args: (got.append(args), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        return got

    def test_clear_deletes_the_saved_covers_and_says_how_much(self):
        cache = self.cache()
        cache.cached(self.url)
        self.wait_stored(cache)
        cache.measure()
        self.wait_for(cache.sizeChanged)
        self.assertNotEqual(cache.property("sizeText"), "0 B")
        toasts, cleared = [], []
        cache.toast.connect(toasts.append)
        cache.cleared.connect(lambda: cleared.append(True))
        cache.clear()
        self.assertTrue(cache.property("busy"))
        self.wait_for(cache.cleared)
        self.assertFalse(cache.property("busy"))
        self.assertEqual(list(self.folder.iterdir()), [])
        self.assertEqual(cleared, [True])
        self.assertEqual(len(toasts), 1)
        self.assertIn(f"{len(PNG)} B", toasts[0])
        self.wait_for(cache.sizeChanged)
        self.assertEqual(cache.property("sizeText"), "0 B")

    def test_a_cover_shown_before_clearing_downloads_again(self):
        cache = self.cache()
        cache.cached(self.url)
        self.wait_stored(cache)
        cache.clear()
        self.wait_for(cache.cleared)
        cache.forget(self.url)  # Cover could not read the deleted file
        self.assertEqual(cache.cached(self.url), "")  # fetched again, not given up on
        self.wait_stored(cache)
        self.assertTrue(cache.cached(self.url).startswith("file://"))
        self.assertEqual(len(self.requests), 2)

    def test_other_addresses_pass_through(self):
        cache = self.cache()
        for url in ("https://example.com/a.jpg", "file:///music/cover.jpg", "image://x/1", ""):
            self.assertEqual(cache.cached(url), url)
        self.assertEqual(self.requests, [])


COVER = r'''
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from senada import imagecache

imagecache.IMAGE_HOSTS = imagecache.IMAGE_HOSTS + ("127.0.0.1",)
app = QGuiApplication([])
images = imagecache.ImageCache(Path(sys.argv[1]))
engine = QQmlApplicationEngine()
engine.warnings.connect(lambda ws: [print("QML:", w.toString(), file=sys.stderr) for w in ws])
engine.rootContext().setContextProperty("images", images)
engine.rootContext().setContextProperty("coverUrl", sys.argv[2])
engine.loadData(b"""
import QtQuick
import QtQuick.Window
Window {
    width: 200; height: 200; visible: true
    property alias ready: cover.ready
    property alias shown: cover.shown
    Cover { id: cover; width: 100; height: 100; source: coverUrl }
}""", QUrl.fromLocalFile(sys.argv[3] + "/Load.qml"))  # beside Cover.qml
window = engine.rootObjects()[0]
tries = [0]

def wait():
    if window.property("ready") or tries[0] > 100:
        print("READY", window.property("ready"), window.property("shown"), flush=True)
        app.quit()
    else:
        tries[0] += 1
        QTimer.singleShot(50, wait)

QTimer.singleShot(0, wait)
app.exec()
'''


class CoverUsesTheCache(DiskCache):
    def show(self, expect="READY True file://"):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-c", COVER, str(self.folder), self.url, str(root / "qml")],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(root),
                 "no_proxy": "*", "NO_PROXY": "*"},
            capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
        )
        self.assertIn(expect, result.stdout, result.stdout + result.stderr)

    def test_cover_shows_the_saved_file_and_a_restart_does_not_download_again(self):
        self.show()
        self.show()
        self.assertEqual(len(self.requests), 1, self.requests)

    def test_a_damaged_saved_copy_is_replaced_by_the_address(self):
        self.cache()._path(self.url).write_bytes(b"\xff\xd8\xff broken jpeg")
        self.show(expect="READY True http://127.0.0.1")
        self.assertEqual(list(self.folder.iterdir()), [])

    # the DiskCache tests are not repeated here
    test_downloaded_once_then_loaded_from_disk_after_a_restart = None
    test_one_download_for_many_covers_of_the_same_image = None
    test_a_non_image_answer_falls_back_to_the_address = None
    test_other_addresses_pass_through = None
    test_a_damaged_copy_is_forgotten = None
    test_clear_deletes_the_saved_covers_and_says_how_much = None
    test_a_cover_shown_before_clearing_downloads_again = None


if __name__ == "__main__":
    unittest.main()
