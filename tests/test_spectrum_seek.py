"""The visualizer full view shows the music's spectrum standing on its seek bar."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = r'''
import sys
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401 (the window comes back as a QQuickWindow)

class Player(QObject):
    changed = Signal()
    def __init__(self):
        super().__init__()
        self.seeked = -1
    @Property("QVariantMap", notify=changed)
    def state(self):
        return {"isPlaying": True, "hasTrack": True, "durationMs": 100000, "uri": "yt:track:x"}
    @Property(int, notify=changed)
    def position(self):
        return 40000
    @Slot(int)
    def seek(self, ms):
        self.seeked = ms

class Session(QObject):
    changed = Signal()
    @Property(str, notify=changed)
    def visualizerStyle(self):
        return "bars"
    @Property(str, notify=changed)
    def seekStyle(self):
        return "bars"  # the full view still draws a plain line under its spectrum

class Visualizer(QObject):  # no cava: the spectrum dances by itself
    changed = Signal()
    @Property(bool, notify=changed)
    def active(self):
        return False
    @Property("QVariantList", notify=changed)
    def bars(self):
        return []

app = QGuiApplication([])
engine = QQmlApplicationEngine()
player, session, visualizer = Player(), Session(), Visualizer()
for name, obj in (("player", player), ("session", session), ("visualizer", visualizer)):
    engine.rootContext().setContextProperty(name, obj)
engine.load(sys.argv[1])
assert engine.rootObjects(), "SpectrumSeek failed to load"
window = engine.rootObjects()[0]

def check():
    try:
        image = window.grabWindow()
        base = 10 + 44 - 2  # a row just above where the bars stand
        px = image.pixelColor
        lit = lambda c: c.red() > 200 and c.green() < 190         # white tinted with the red accent
        dim = lambda c: 20 < c.red() < 120 and abs(c.red() - c.green()) < 8
        def runs(x0, x1, kind):  # separate bars along the row
            n, inside = 0, False
            for x in range(x0, x1):
                hit = kind(px(x, base))
                n += hit and not inside
                inside = hit
            return n
        assert runs(12, 160, lit) >= 10, "the played part is not a row of lit bars"
        assert runs(180, 408, lit) == 0, "the part still to come is lit"
        assert runs(180, 408, dim) >= 10, "the part still to come is not a row of bars"
        def height(x):
            y = base
            while y > 10 and px(x, y).red() > 20:
                y -= 1
            return base - y
        assert max(height(x) for x in range(12, 408)) > 10, "the bars do not move while the song plays"
        app.exit(0)
    except Exception:
        import traceback; traceback.print_exc(); app.exit(1)

QTimer.singleShot(1200, check)
sys.exit(app.exec())
'''


class SpectrumSeek(unittest.TestCase):
    def test_spectrum_is_lit_up_to_where_the_song_is(self):
        fixture = Path(__file__).parent / "qml" / "spectrum_smoke.qml"
        res = subprocess.run([sys.executable, "-c", SCRIPT, str(fixture)], capture_output=True, text=True,
                             timeout=60, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
