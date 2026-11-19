"""Exercise the real app's view lifetimes in a separate Qt GUI process."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LazyViews(unittest.TestCase):
    def test_secondary_views_load_on_demand_and_release_after_closing(self):
        script = r'''
import time
import traceback
import uuid

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from senada import engine, instance, main, ytmusic

instance_name = "senada-test-" + uuid.uuid4().hex
instance.server_name = lambda: instance_name
engine.AudioEngine._start_mpv = lambda self: None
main.Player.start = lambda self: None
main.Updater.check = lambda *args: None
ytmusic.home = lambda: [
    {"title": f"Shelf {shelf}", "tracks": [
        {"uri": f"yt:track:{shelf}-{row}", "name": f"Song {row}", "artists": "Test"}
        for row in range(8)
    ], "cards": [
        {"kind": "album", "id": f"test-{row}", "name": f"Album {row}"}
        for row in range(12)
    ] if shelf == 0 else []}
    for shelf in range(16)
]
set_window = main.Session.set_window

def install_smoke(session, window):
    set_window(session, window)
    shell = window.findChild(QObject, "shell")

    def view(name):
        return window.findChild(QObject, name)

    def mini():
        return next((w for w in QGuiApplication.allWindows()
                     if w.title() == "Senada mini player"), None)

    def visual_items(item, prefix):
        if item.metaObject().className().startswith(prefix):
            yield item
        for child in item.childItems():
            yield from visual_items(child, prefix)

    def wait_for(condition, message):
        deadline = time.monotonic() + 2.5
        while not condition():
            assert time.monotonic() < deadline, message
            QTest.qWait(25)

    def verify():
        try:
            assert view("settingsDialog") is None, "Settings was instantiated at startup"
            assert view("immersive") is None, "Immersive view was instantiated at startup"
            assert mini() is None, "Mini Player was instantiated at startup"

            home = next(visual_items(shell, "HomePage_QML"))
            feed = home.childItems()[0]
            def shelves():
                return list(visual_items(home, "TrackSection_QML"))

            wait_for(lambda: feed.property("count") == 16, "Home feed did not load")
            assert len(shelves()) < 16, "Every Home shelf was instantiated at startup"
            feed.positionViewAtIndex(0, 0)  # ListView.Beginning
            wait_for(lambda: any(shelf.property("title") == "Shelf 0" for shelf in shelves()),
                     "First shelf did not load")
            first = next(shelf for shelf in shelves() if shelf.property("title") == "Shelf 0")
            first.setProperty("expanded", True)
            carousel = next(visual_items(first.parentItem(), "Carousel_QML"))
            carousel.setProperty("scrollOffset", 380)
            feed.setProperty("contentY", feed.property("originY")
                             + feed.property("contentHeight") - feed.height())
            wait_for(lambda: any(shelf.property("title") == "Shelf 15" for shelf in shelves()),
                     "Last shelf did not load")
            wait_for(lambda: all(shelf.property("title") != "Shelf 0" for shelf in shelves()),
                     "Offscreen shelf stayed in memory")
            feed.positionViewAtIndex(0, 0)
            wait_for(lambda: any(shelf.property("title") == "Shelf 0" for shelf in shelves()),
                     "First shelf did not reload")
            first = next(shelf for shelf in shelves() if shelf.property("title") == "Shelf 0")
            assert first.property("expanded"), "Shelf expansion was lost after scrolling"
            carousel = next(visual_items(first.parentItem(), "Carousel_QML"))
            assert carousel.property("scrollOffset") == 380, "Carousel position was lost after scrolling"

            shell.navigate("settings", "audio", False)
            settings = view("settingsDialog")
            assert settings is not None
            wait_for(lambda: settings.property("opened"), "Settings did not finish opening")
            assert settings.property("section") == "audio"
            shell.navigate("settings", "", False)
            wait_for(lambda: view("settingsDialog") is None, "Closed Settings stayed in memory")
            shell.navigate("settings", "", False)
            assert view("settingsDialog").property("section") == "audio"
            shell.navigate("home", "", False)

            shell.setProperty("immersive", True)
            immersive = view("immersive")
            assert immersive is not None
            wait_for(lambda: immersive.property("y") == 0, "Immersive view did not finish opening")
            immersive.setProperty("panel", "queue")
            shell.setProperty("immersive", False)
            assert view("immersive") is not None, "Exit animation was skipped"
            wait_for(lambda: view("immersive") is None, "Closed immersive view stayed in memory")
            shell.setProperty("immersive", True)
            assert view("immersive").property("panel") == "queue"
            shell.setProperty("immersive", False)

            window.setProperty("miniMode", True)
            wait_for(lambda: mini() is not None and mini().isVisible(), "Mini Player did not open")
            mini().close()
            wait_for(lambda: mini() is None, "Closed Mini Player stayed in memory")
            assert window.isVisible() and not window.property("miniMode")
        except Exception:
            traceback.print_exc()
            QGuiApplication.exit(1)
        else:
            session.quit()

    QTimer.singleShot(100, verify)

main.Session.set_window = install_smoke
main.main()
'''
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parent.parent,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                     "QT_QUICK_BACKEND": "software", "XDG_CONFIG_HOME": temp,
                     "XDG_CACHE_HOME": temp, "APPDATA": temp, "LOCALAPPDATA": temp},
                capture_output=True, text=True, timeout=25,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for message in ("TypeError", "ReferenceError", "Binding loop"):
            self.assertNotIn(message, result.stderr)
