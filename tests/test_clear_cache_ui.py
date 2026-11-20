"""Settings → Profile & Library → Cache: the button asks first, then clears the saved covers."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ClearCacheButton(unittest.TestCase):
    def test_button_asks_then_clears(self):
        script = r'''
import time, traceback, uuid
from pathlib import Path
from PySide6.QtCore import QMetaObject, QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from senada import engine, imagecache, instance, main

instance_name = "senada-test-" + uuid.uuid4().hex
instance.server_name = lambda: instance_name
engine.AudioEngine._start_mpv = lambda self: None
main.Player.start = lambda self: None
main.Updater.check = lambda *args: None
imagecache.IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
(imagecache.IMAGE_CACHE / "saved-cover").write_bytes(b"\xff\xd8\xff" + b"x" * 2000)
toasts = []
set_window = main.Session.set_window

def install(session, window):
    set_window(session, window)
    session.toast.connect(toasts.append)
    shell = window.findChild(QObject, "shell")

    def wait_for(condition, message):
        deadline = time.monotonic() + 3
        while not condition():
            assert time.monotonic() < deadline, message
            QTest.qWait(25)

    def find(name):
        return window.findChild(QObject, name)

    def verify():
        try:
            shell.navigate("settings", "profile", False)
            wait_for(lambda: find("clearCacheButton") is not None, "Cache row is missing")
            button = find("clearCacheButton")
            from PySide6.QtQml import QQmlEngine
            images = QQmlEngine.contextForObject(window).contextProperty("images")
            wait_for(lambda: images.property("sizeText") == "2 KB", "Cache size is not shown")
            QMetaObject.invokeMethod(button, "clicked")
            dialog = find("clearCacheDialog")
            wait_for(lambda: dialog.property("opened"), "Clear cache did not ask first")
            assert (imagecache.IMAGE_CACHE / "saved-cover").exists(), "Cleared before confirming"
            QMetaObject.invokeMethod(find("confirmClearCache"), "clicked")
            wait_for(lambda: not (imagecache.IMAGE_CACHE / "saved-cover").exists(), "Cache was not cleared")
            wait_for(lambda: any("2 KB" in t for t in toasts), f"No toast: {toasts}")
            wait_for(lambda: not dialog.property("visible"), "Dialog stayed open")
            wait_for(lambda: images.property("sizeText") == "0 B", "Size was not measured again")
            print("CLEAR_CACHE_OK", toasts[-1], flush=True)
        except Exception:
            traceback.print_exc()
            QGuiApplication.exit(1)
        else:
            session.quit()

    QTimer.singleShot(100, verify)

main.Session.set_window = install
main.main()
'''
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parent.parent,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                     "QT_QUICK_BACKEND": "software", "XDG_CONFIG_HOME": temp,
                     "XDG_CACHE_HOME": temp, "APPDATA": temp, "LOCALAPPDATA": temp},
                capture_output=True, text=True, timeout=25, stdin=subprocess.DEVNULL,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CLEAR_CACHE_OK", result.stdout)
        for message in ("TypeError", "ReferenceError", "Binding loop"):
            self.assertNotIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
