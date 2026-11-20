"""Settings is split into small sections: each one opens its own page, with an icon that exists."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIALOG = (ROOT / "qml" / "SettingsDialog.qml").read_text(encoding="utf-8")
SPLIT = ("appearance", "player", "miniplayer", "profile", "library", "storage", "backup")


class SectionList(unittest.TestCase):
    def test_every_section_icon_exists(self):
        icons = re.findall(r'key: "[a-z]+", icon: "([a-z-]+)"', DIALOG)
        self.assertGreaterEqual(len(icons), 16)
        for icon in icons:
            self.assertTrue((ROOT / "qml" / "icons" / f"{icon}.svg").is_file(), icon)

    def test_every_group_is_listed(self):
        groups = set(re.findall(r'\{ group: "([^"]+)", key:', DIALOG))
        listed = re.search(r'readonly property var groups: \[([^\]]*)\]', DIALOG).group(1)
        self.assertEqual(groups, set(re.findall(r'"([^"]+)"', listed)))

    def test_each_section_opens_its_own_page(self):
        script = r'''
import time, traceback, uuid
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from senada import engine, instance, main

instance.server_name = lambda: "senada-test-" + uuid.uuid4().hex
engine.AudioEngine._start_mpv = lambda self: None
main.Player.start = lambda self: None
main.Updater.check = lambda *args: None
SPLIT = %r
set_window = main.Session.set_window

def install(session, window):
    set_window(session, window)
    shell = window.findChild(QObject, "shell")

    def wait_for(condition, message):
        deadline = time.monotonic() + 3
        while not condition():
            assert time.monotonic() < deadline, message
            QTest.qWait(25)

    def verify():
        try:
            shell.navigate("settings", "", False)
            wait_for(lambda: window.findChild(QObject, "settingsDialog") is not None, "Settings did not open")
            dialog = window.findChild(QObject, "settingsDialog")
            keys = [s["key"] for s in dialog.property("sections").toVariant()]
            assert len(keys) == len(set(keys)) >= 16, keys
            for key in keys:
                dialog.setProperty("section", key)
                assert dialog.property("section") == key, key
                if key in SPLIT:
                    wait_for(lambda: window.findChild(QObject, "page-" + key) is not None,
                             f"{key} does not open its own page")
                    others = lambda: [k for k in SPLIT if k != key and window.findChild(QObject, "page-" + k)]
                    wait_for(lambda: not others(), f"{key} also shows {others()}")
                QTest.qWait(30)
            print("SECTIONS_OK", len(keys), flush=True)
        except Exception:
            traceback.print_exc()
            QGuiApplication.exit(1)
        else:
            session.quit()

    QTimer.singleShot(100, verify)

main.Session.set_window = install
main.main()
''' % (SPLIT,)
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                     "XDG_CONFIG_HOME": temp, "XDG_CACHE_HOME": temp, "APPDATA": temp, "LOCALAPPDATA": temp},
                capture_output=True, text=True, timeout=40, stdin=subprocess.DEVNULL,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SECTIONS_OK", result.stdout)
        for message in ("TypeError", "ReferenceError", "Binding loop", "is not defined", "Cannot assign"):
            self.assertNotIn(message, result.stderr)


if __name__ == "__main__":
    unittest.main()
