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
SPLIT = ("appearance", "player", "miniplayer", "profile", "library", "storage", "backup", "updates")


class SectionList(unittest.TestCase):
    def test_every_section_icon_exists(self):
        icons = re.findall(r'key: "[a-z]+", icon: "([a-z-]+)"', DIALOG)
        self.assertGreaterEqual(len(icons), 15)
        for icon in icons:
            self.assertTrue((ROOT / "qml" / "icons" / f"{icon}.svg").is_file(), icon)

    def test_every_group_is_listed(self):
        groups = set(re.findall(r'\{ group: "([^"]+)", key:', DIALOG))
        listed = re.search(r'readonly property var groups: \[([^\]]*)\]', DIALOG).group(1)
        self.assertEqual(groups, set(re.findall(r'"([^"]+)"', listed)))

    def test_each_section_opens_its_own_page(self):
        script = r'''
import time, traceback, uuid
from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine
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
    updater = QQmlEngine.contextForObject(window).contextProperty("updater")

    def find(name):
        return window.findChild(QObject, name)

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
            assert len(keys) == len(set(keys)) >= 15, keys
            assert "updates" in keys and "whatsnew" not in keys, keys
            for key in keys:
                dialog.setProperty("section", key)
                assert dialog.property("section") == key, key
                if key in SPLIT:
                    wait_for(lambda: window.findChild(QObject, "page-" + key) is not None,
                             f"{key} does not open its own page")
                    others = lambda: [k for k in SPLIT if k != key and window.findChild(QObject, "page-" + k)]
                    wait_for(lambda: not others(), f"{key} also shows {others()}")
                QTest.qWait(30)

            shell.navigate("settings", "whatsnew", False)
            assert dialog.property("section") == "updates", "The old What's new link should open Updates"
            wait_for(lambda: find("versionHistoryHeading") is not None, "Updates is missing version history")
            assert find("checkForUpdatesButton").property("enabled")
            assert find("applyUpdateButton").property("text") == "Sync again"
            updater._commits_behind = 1
            updater._changelog = "Test release notes"
            updater.changed.emit()
            assert find("availableUpdateNotes").property("visible")
            assert find("applyUpdateButton").property("text") == "Update & restart"
            updater._updating = True
            updater.changed.emit()
            assert not find("checkForUpdatesButton").property("enabled")
            assert not find("applyUpdateButton").property("enabled")

            search = find("settingsSearch")
            session.language = "id"
            for term in ("What's new", "Check for updates", "Riwayat versi", "versi baru",
                         "versi yang ada di perangkat ini"):
                search.setProperty("text", term)
                matches = dialog.property("shown").toVariant()
                assert [s["key"] for s in matches] == ["updates"], (term, matches)
            search.setProperty("text", "")
            dialog.setProperty("section", "about")
            wait_for(lambda: find("aboutWhatsNewLink") is not None, "About is missing its What's new link")
            QTest.qWait(50)
            link = find("aboutWhatsNewLink")
            pos = link.mapToScene(QPointF(link.width() / 2, link.height() / 2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, pos=pos)
            wait_for(lambda: dialog.property("section") == "updates", "About did not open Updates")

            # opening on a section low in the list scrolls it into view, and back up again
            shell.navigate("settings", "", False)
            wait_for(lambda: window.findChild(QObject, "settingsDialog") is None, "Settings did not close")
            window.showNormal()
            window.resize(1000, 600)  # too short for every section at once
            QTest.qWait(100)
            shell.navigate("settings", "about", False)

            def entry_for(key):  # made by a Repeater: found through the visual tree, not findChild
                flick = window.findChild(QObject, "sectionList")
                todo = [flick] if flick is not None else []
                while todo:
                    item = todo.pop()
                    if item.objectName() == "section-" + key:
                        return item
                    todo.extend(item.childItems())
                return None

            wait_for(lambda: entry_for("about") is not None, "Settings did not reopen")

            def shown(key):
                entry = entry_for(key)
                flick = window.findChild(QObject, "sectionList")
                y = entry.mapToItem(flick, QPointF(0, 0)).y()
                return 0 <= y and y + entry.height() <= flick.height()
            flick = window.findChild(QObject, "sectionList")
            wait_for(lambda: flick.property("contentHeight") > flick.height(), "The list needs no scrolling here")
            wait_for(lambda: shown("about"), "About was not scrolled into view")
            assert flick.property("contentY") > 0
            window.findChild(QObject, "settingsDialog").setProperty("section", "appearance")
            wait_for(lambda: shown("appearance"), "Appearance was not scrolled into view")
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
